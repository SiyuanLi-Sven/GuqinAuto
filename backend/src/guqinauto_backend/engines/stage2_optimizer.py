"""
stage2：在 stage1 候选图上做序列级优化（Top-K 推荐，不写回）。

定位：
- 这是 GuqinAuto 的“自动推荐”核心之一：在每个事件的候选音位集合上选择一条可弹路径。
- 目前实现的是最小可用子集：
  - 仅支持单音事件（每个 eid 只有 1 个 target）
  - 仅使用 stage1 的 open/press/harmonic 候选（是否包含 harmonic 由调用方决定）
  - 只做“推荐结果”返回，不直接写回 MusicXML（写回属于下一步：Profile v0.3 + 写回协议）
  - 增量支持：2-note chord（targets=2）可做推荐；chord 锁定要求显式指定 slot（避免语义歧义）

学术级要求：
- 锁定导致无解必须失败，不允许“尽量凑一个”。
- 对不支持的情况（chord/缺 pitch/空候选）必须失败。
  - 3+ 音 chord 仍必须失败（直到有明确的组合剪枝与代价定义）。
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
class ChordCandidate:
    """stage2 chord 内部候选表示：一个事件同时选多个音位（按 slot）。"""

    slot_to_cand: dict[str, Candidate]
    pos_ratio: float  # 代表性位置（用于事件间 shift 代价；当前用均值）
    cents_error_sum: float
    has_harmonic: bool
    raw_by_slot: dict[str, Any]


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
            if k == "slot":
                raise ValueError("单音事件 lock 不支持 slot 字段（请移除 slot）")
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


def _transition_cost_chord(a: Candidate | ChordCandidate, b: Candidate | ChordCandidate, w: Weights) -> tuple[float, dict[str, float]]:
    """允许单音/和弦混合的事件间代价（MVP：可解释、可计算即可）。"""

    a_pos = a.pos_ratio if isinstance(a, ChordCandidate) else a.pos_ratio
    b_pos = b.pos_ratio if isinstance(b, ChordCandidate) else b.pos_ratio
    shift = abs(a_pos - b_pos) * w.shift

    def strings(x: Candidate | ChordCandidate) -> set[int]:
        if isinstance(x, Candidate):
            return {x.string}
        return {c.string for c in x.slot_to_cand.values()}

    def techniques(x: Candidate | ChordCandidate) -> set[str]:
        if isinstance(x, Candidate):
            return {x.technique}
        return {c.technique for c in x.slot_to_cand.values()}

    a_str = strings(a)
    b_str = strings(b)
    sc = (0.0 if (a_str & b_str) else 1.0) * w.string_change

    a_tech = techniques(a)
    b_tech = techniques(b)
    tc = (0.0 if a_tech == b_tech else 1.0) * w.technique_change

    has_harm = False
    if isinstance(b, Candidate):
        has_harm = b.technique == "harmonic"
        ce = abs(b.cents_error) * w.cents_error
    else:
        has_harm = b.has_harmonic
        ce = abs(b.cents_error_sum) * w.cents_error

    hp = (1.0 if has_harm else 0.0) * w.harmonic_penalty
    total = shift + sc + tc + hp + ce
    return total, {"shift": shift, "string_change": sc, "technique_change": tc, "harmonic": hp, "cents_error": ce}


def _top_m_candidates(cands: list[Candidate], m: int) -> list[Candidate]:
    if m <= 0:
        return []
    # 优先更纯的匹配（cents_error 小），其次避免 harmonic（MVP：轻微偏好）
    return sorted(cands, key=lambda c: (abs(c.cents_error), 1 if c.technique == "harmonic" else 0))[:m]


def _build_chord_candidates(
    *,
    targets: list[dict[str, Any]],
    eid: str,
    locks: list[Lock],
    max_per_slot: int = 25,
    max_products: int = 1200,
) -> list[ChordCandidate]:
    """把 stage1 的 targets（2-note chord）组合成 stage2 的 chord 候选列表。"""

    if len(targets) != 2:
        raise ValueError(f"stage2 chord 当前仅支持 2-note：eid={eid} targets={len(targets)}")

    t0, t1 = targets
    slot0 = t0.get("slot")
    slot1 = t1.get("slot")
    if not isinstance(slot0, str) or not slot0:
        raise ValueError(f"stage2 chord 缺少 slot：eid={eid} slot0={slot0!r}")
    if not isinstance(slot1, str) or not slot1:
        raise ValueError(f"stage2 chord 缺少 slot：eid={eid} slot1={slot1!r}")
    if slot0 == slot1:
        raise ValueError(f"stage2 chord slot 重复：eid={eid} slot={slot0!r}")

    raw0 = t0.get("candidates")
    raw1 = t1.get("candidates")
    if not isinstance(raw0, list) or not isinstance(raw1, list):
        raise ValueError(f"stage2 chord targets.candidates 非 list：eid={eid}")

    c0 = _top_m_candidates([_cand_to_internal(c) for c in raw0], max_per_slot)
    c1 = _top_m_candidates([_cand_to_internal(c) for c in raw1], max_per_slot)

    # chord 锁定：必须显式指定 slot（避免语义歧义）
    for lk in locks:
        if lk.eid != eid:
            continue
        lk_slot = lk.fields.get("slot")
        if lk_slot not in (str(slot0), str(slot1)):
            raise ValueError(f"stage2 chord lock 必须指定 slot={slot0!r}/{slot1!r} 之一：eid={eid} got={lk_slot!r}")
        extra = set(lk.fields.keys()) - {"slot", "string", "technique"}
        if extra:
            raise ValueError(f"stage2 chord lock 含不支持字段：eid={eid} extra={sorted(extra)!r}")
        reduced = {k: v for k, v in lk.fields.items() if k != "slot"}
        if str(lk_slot) == str(slot0):
            c0 = _apply_locks(eid, c0, [Lock(eid=eid, fields=reduced)])
        else:
            c1 = _apply_locks(eid, c1, [Lock(eid=eid, fields=reduced)])
    if not c0 or not c1:
        raise ValueError(f"stage2 chord 无候选：eid={eid} (slot0={slot0!r} slot1={slot1!r})")

    out: list[ChordCandidate] = []
    for a in c0:
        for b in c1:
            if len(out) >= max_products:
                raise ValueError(f"stage2 chord 组合候选过多（>{max_products}），需要更强的剪枝策略：eid={eid}")
            # 物理约束：同一时刻一根弦不能发两个音
            if a.string == b.string:
                continue
            pr = (float(a.pos_ratio) + float(b.pos_ratio)) / 2.0
            ce = float(a.cents_error) + float(b.cents_error)
            has_h = (a.technique == "harmonic") or (b.technique == "harmonic")
            out.append(
                ChordCandidate(
                    slot_to_cand={str(slot0): a, str(slot1): b},
                    pos_ratio=float(pr),
                    cents_error_sum=float(ce),
                    has_harmonic=bool(has_h),
                    raw_by_slot={str(slot0): a.raw, str(slot1): b.raw},
                )
            )
    if not out:
        raise ValueError(f"stage2 chord 无可用组合（弦号冲突/锁定过强）：eid={eid} slot0={slot0!r} slot1={slot1!r}")
    return out


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
    # 每个事件可为单音 Candidate 或 chord ChordCandidate（统一存为 object）
    seq_cands: list[list[Candidate | ChordCandidate]] = []
    seq_kind: list[str] = []

    for e in events:
        eid = str(e.get("eid") or "")
        if not eid:
            raise ValueError("事件缺少 eid")
        targets = e.get("targets")
        if not isinstance(targets, list) or not targets:
            raise ValueError(f"事件 targets 非法：eid={eid}")

        if len(targets) == 1:
            t0 = targets[0]
            if t0.get("slot") not in (None, ""):
                raise ValueError(f"stage2 单音事件 slot 非空（当前不支持该形态）：eid={eid} slot={t0.get('slot')!r}")

            raw_cands = t0.get("candidates")
            if not isinstance(raw_cands, list):
                raise ValueError(f"targets[0].candidates 非 list：eid={eid}")
            cands0 = [_cand_to_internal(c) for c in raw_cands]
            cands0 = _apply_locks(eid, cands0, locks)
            if not cands0:
                raise ValueError(f"锁定/约束导致无候选：eid={eid}")
            seq_eids.append(eid)
            seq_cands.append(cands0)
            seq_kind.append("single")
            continue

        if len(targets) == 2:
            cands2 = _build_chord_candidates(targets=targets, eid=eid, locks=locks)
            seq_eids.append(eid)
            seq_cands.append(cands2)
            seq_kind.append("chord2")
            continue

        raise ValueError(f"stage2 暂不支持 3+ 音 chord：eid={eid} targets={len(targets)}")

    # DP：dp[i][j] = topK partial paths ending at candidate j
    # 用结构：list of (cost, breakdown_sums, back_ptr)
    # back_ptr: (prev_j, prev_k_idx)
    dp: list[list[list[tuple[float, dict[str, float], tuple[int, int] | None]]]] = []

    # init
    dp0: list[list[tuple[float, dict[str, float], tuple[int, int] | None]]] = []
    for _j, c in enumerate(seq_cands[0]):
        if isinstance(c, Candidate):
            harmonic = (1.0 if c.technique == "harmonic" else 0.0) * weights.harmonic_penalty
            ce = abs(c.cents_error) * weights.cents_error
        else:
            harmonic = (1.0 if c.has_harmonic else 0.0) * weights.harmonic_penalty
            ce = abs(c.cents_error_sum) * weights.cents_error
        base = {"shift": 0.0, "string_change": 0.0, "technique_change": 0.0, "harmonic": harmonic, "cents_error": ce}
        cost = sum(base.values())
        dp0.append([(float(cost), base, None)])
    dp.append(dp0)

    # transitions
    for i in range(1, len(seq_cands)):
        cur_states: list[list[tuple[float, dict[str, float], tuple[int, int]]]] = []
        for j, cur_c in enumerate(seq_cands[i]):
            candidates_for_state: list[tuple[float, dict[str, float], tuple[int, int]]] = []
            for pj, prev_c in enumerate(seq_cands[i - 1]):
                prev_paths = dp[i - 1][pj]
                for pk, (prev_cost, prev_bd, _prev_ptr) in enumerate(prev_paths):
                    tc, bd = _transition_cost_chord(prev_c, cur_c, weights)
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
        for eid, cand_list, kind, j in zip(seq_eids, seq_cands, seq_kind, idxs):
            chosen = cand_list[j]
            if isinstance(chosen, Candidate):
                assignments.append({"eid": eid, "choice": chosen.raw})
            else:
                by_slot = [{"slot": slot, "choice": raw} for slot, raw in chosen.raw_by_slot.items()]
                assignments.append({"eid": eid, "choices": by_slot})

        solutions.append(
            Solution(
                solution_id=f"S{si:04d}",
                total_cost=float(total_cost),
                assignments=assignments,
                explain={"cost_breakdown": bd, "weights": weights.__dict__},
            )
        )

    return solutions
