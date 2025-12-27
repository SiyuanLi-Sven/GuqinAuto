"""
stage2：在 stage1 候选图上做序列级优化（Top-K 推荐，不写回）。

定位：
- 这是 GuqinAuto 的“自动推荐”核心之一：在每个事件的候选音位集合上选择一条可弹路径。
- 目前实现的是最小可用子集：
  - 仅支持单音事件（每个 eid 只有 1 个 target）
  - 仅使用 stage1 的 open/press/harmonic 候选（是否包含 harmonic 由调用方决定）
  - 只做“推荐结果”返回，不直接写回 MusicXML（写回属于下一步：Profile v0.3 + 写回协议）

学术级要求：
- 锁定导致无解必须失败，不允许“尽量凑一个”。
- 对不支持的情况（chord/缺 pitch/空候选）必须失败。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


Technique = Literal["open", "press", "harmonic"]


@dataclass(frozen=True)
class Candidate:
    """stage2 内部候选表示（从 stage1 输出抽取）。"""

    string: int
    technique: Technique
    pos_ratio: float  # open 视为 0
    cents_error: float
    raw: dict[str, Any]  # 原始 stage1 candidate（便于返回给前端/诊断）


@dataclass(frozen=True)
class Lock:
    eid: str
    fields: dict[str, Any]


@dataclass(frozen=True)
class Weights:
    shift: float = 1.0
    string_change: float = 0.5
    technique_change: float = 0.2
    harmonic_penalty: float = 0.1
    cents_error: float = 0.01  # cents_error 的权重（鼓励更“纯”的匹配）


@dataclass(frozen=True)
class Solution:
    solution_id: str
    total_cost: float
    assignments: list[dict[str, Any]]
    explain: dict[str, Any]


def _cand_to_internal(c: dict[str, Any]) -> Candidate:
    pos = c.get("pos") or {}
    pos_ratio = pos.get("pos_ratio")
    if c.get("technique") == "open":
        pr = 0.0
    else:
        if not isinstance(pos_ratio, (int, float)):
            raise ValueError(f"候选缺少 pos.pos_ratio：{c!r}")
        pr = float(pos_ratio)
    string = int(c["string"])
    technique = c["technique"]
    if technique not in ("open", "press", "harmonic"):
        raise ValueError(f"未知 technique：{technique!r}")
    cents_error = float(c.get("cents_error") or 0.0)
    return Candidate(string=string, technique=technique, pos_ratio=pr, cents_error=cents_error, raw=c)


def _apply_locks(eid: str, candidates: list[Candidate], locks: list[Lock]) -> list[Candidate]:
    out = candidates
    for lk in locks:
        if lk.eid != eid:
            continue
        for k, v in lk.fields.items():
            if k == "string":
                out = [c for c in out if c.string == int(v)]
            elif k == "technique":
                out = [c for c in out if c.technique == str(v)]
            else:
                raise ValueError(f"不支持的 lock 字段：{k!r}")
    return out


def _transition_cost(a: Candidate, b: Candidate, w: Weights) -> tuple[float, dict[str, float]]:
    shift = abs(a.pos_ratio - b.pos_ratio) * w.shift
    sc = (0.0 if a.string == b.string else 1.0) * w.string_change
    tc = (0.0 if a.technique == b.technique else 1.0) * w.technique_change
    hp = (1.0 if b.technique == "harmonic" else 0.0) * w.harmonic_penalty
    ce = abs(b.cents_error) * w.cents_error
    total = shift + sc + tc + hp + ce
    return total, {"shift": shift, "string_change": sc, "technique_change": tc, "harmonic": hp, "cents_error": ce}


def optimize_topk(
    *,
    events: list[dict[str, Any]],
    k: int,
    locks: list[Lock],
    weights: Weights,
) -> list[Solution]:
    """在事件序列上做 Top-K 路径推荐。

    events 结构要求（来自 stage1 输出）：
    - 每个元素形如 {"eid": "...", "targets": [ { "slot": null, "candidates": [...] } ]}
    - 当前仅支持 len(targets)==1，且 slot 为空（单音事件）
    """

    if k <= 0:
        raise ValueError("k 必须为正")
    if not events:
        raise ValueError("空 events")

    seq_eids: list[str] = []
    seq_cands: list[list[Candidate]] = []

    for e in events:
        eid = str(e.get("eid") or "")
        if not eid:
            raise ValueError("事件缺少 eid")
        targets = e.get("targets")
        if not isinstance(targets, list) or len(targets) != 1:
            raise ValueError(f"stage2 暂不支持 chord（targets!=1）：eid={eid}")
        t0 = targets[0]
        if t0.get("slot") not in (None, ""):
            raise ValueError(f"stage2 暂不支持 chord slot：eid={eid} slot={t0.get('slot')!r}")

        raw_cands = t0.get("candidates")
        if not isinstance(raw_cands, list):
            raise ValueError(f"targets[0].candidates 非 list：eid={eid}")
        cands = [_cand_to_internal(c) for c in raw_cands]
        cands = _apply_locks(eid, cands, locks)
        if not cands:
            raise ValueError(f"锁定/约束导致无候选：eid={eid}")

        seq_eids.append(eid)
        seq_cands.append(cands)

    # DP：dp[i][j] = topK partial paths ending at candidate j
    # 用结构：list of (cost, breakdown_sums, back_ptr)
    # back_ptr: (prev_j, prev_k_idx)
    dp: list[list[list[tuple[float, dict[str, float], tuple[int, int] | None]]]] = []

    # init
    dp0: list[list[tuple[float, dict[str, float], tuple[int, int] | None]]] = []
    for _j, c in enumerate(seq_cands[0]):
        base = {
            "shift": 0.0,
            "string_change": 0.0,
            "technique_change": 0.0,
            "harmonic": (1.0 if c.technique == "harmonic" else 0.0) * weights.harmonic_penalty,
            "cents_error": abs(c.cents_error) * weights.cents_error,
        }
        cost = sum(base.values())
        dp0.append([(cost, base, None)])
    dp.append(dp0)

    # transitions
    for i in range(1, len(seq_cands)):
        cur_states: list[list[tuple[float, dict[str, float], tuple[int, int]]]] = []
        for j, cur_c in enumerate(seq_cands[i]):
            candidates_for_state: list[tuple[float, dict[str, float], tuple[int, int]]] = []
            for pj, prev_c in enumerate(seq_cands[i - 1]):
                prev_paths = dp[i - 1][pj]
                for pk, (prev_cost, prev_bd, _prev_ptr) in enumerate(prev_paths):
                    tc, bd = _transition_cost(prev_c, cur_c, weights)
                    new_bd = dict(prev_bd)
                    for kk, vv in bd.items():
                        new_bd[kk] = float(new_bd.get(kk, 0.0) + vv)
                    new_cost = float(prev_cost + tc)
                    candidates_for_state.append((new_cost, new_bd, (pj, pk)))

            # 取最小 k 条（稳定：按 cost，再按来源索引）
            candidates_for_state.sort(key=lambda x: x[0])
            cur_states.append(candidates_for_state[:k])
        dp.append(cur_states)

    # 收集全局 topK 终止路径
    end_candidates: list[tuple[float, dict[str, float], int, int]] = []  # cost, bd, end_j, end_kidx
    last_i = len(seq_cands) - 1
    for j in range(len(seq_cands[last_i])):
        for kk, (cost, bd, _ptr) in enumerate(dp[last_i][j]):
            end_candidates.append((cost, bd, j, kk))
    end_candidates.sort(key=lambda x: x[0])
    end_candidates = end_candidates[:k]

    def reconstruct(end_j: int, end_k: int) -> tuple[list[int], dict[str, float], float]:
        idxs = [0] * len(seq_cands)
        i = last_i
        j = end_j
        kidx = end_k
        cost, bd, ptr = dp[i][j][kidx]
        idxs[i] = j
        while ptr is not None:
            pj, pk = ptr
            i -= 1
            j = pj
            kidx = pk
            cost, bd, ptr = dp[i][j][kidx]
            idxs[i] = j
        final_cost, final_bd, _ = dp[last_i][end_j][end_k]
        return idxs, final_bd, final_cost

    solutions: list[Solution] = []
    for si, (_cost, _bd, end_j, end_k) in enumerate(end_candidates, start=1):
        idxs, bd, total_cost = reconstruct(end_j, end_k)
        assignments: list[dict[str, Any]] = []
        for eid, cand_list, j in zip(seq_eids, seq_cands, idxs):
            assignments.append({"eid": eid, "choice": cand_list[j].raw})

        solutions.append(
            Solution(
                solution_id=f"S{si:04d}",
                total_cost=float(total_cost),
                assignments=assignments,
                explain={"cost_breakdown": bd, "weights": weights.__dict__},
            )
        )

    return solutions
