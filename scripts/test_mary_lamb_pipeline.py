"""
用一个手写的“玛丽有只小小羊”MusicXML 示例做端到端回归测试（不依赖后端服务进程）。

覆盖的链路（当前仓库已实现的最小可用子集）：
1) MusicXML(Profile v0.2/0.3 兼容) 解析为 score view
2) 项目状态检查：
   - pitch_resolved（staff1 是否有绝对 pitch）
   - staff1 pitch 与 staff2 指法推导 pitch 的一致性 warning（允许不一致，但必须显式提示）
3) stage1：绝对音高 → 候选音位枚举（PositionEngine）
4) stage2：在候选图上做序列优化，输出 Top-1 推荐
5) 把 Top-1 推荐“显式写回”到 staff2（edit_source=auto），再跑一次状态检查，确保 warning 收敛

输出文件：
- temp/out_mary_lamb/after_stage2_autodraft.musicxml

运行：
  python scripts/test_mary_lamb_pipeline.py
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "docs/data/examples/guqin_jzp_profile_v0.3_mary_had_a_little_lamb_input.musicxml"
OUT_DIR = REPO_ROOT / "temp/out_mary_lamb"


def _ensure_backend_src_on_path(repo_root: Path) -> None:
    src_dir = repo_root / "backend" / "src"
    if not src_dir.exists():
        raise RuntimeError(f"找不到 backend/src：{src_dir}")
    sys.path.insert(0, str(src_dir))


def _pitch_dict_to_midi(pitch: dict[str, Any] | None) -> int:
    if not isinstance(pitch, dict):
        raise ValueError("staff1 pitch 缺失/非 dict")
    step = pitch.get("step")
    octave = pitch.get("octave")
    alter = pitch.get("alter", 0)
    if not isinstance(step, str) or not isinstance(octave, int):
        raise ValueError(f"staff1 pitch 不完整：{pitch!r}")
    if not isinstance(alter, int):
        alter = 0
    from guqinauto_backend.domain.pitch import MusicXmlPitch

    return MusicXmlPitch(step=step, alter=alter, octave=octave).to_midi()


def _candidate_to_api_dict(c: Any) -> dict[str, Any]:
    # 对齐 backend/server.py:_stage1_candidate_to_dict 的最小结构，便于复用 stage2 优化器
    technique = c.technique
    if technique == "open":
        pos_source = None
    elif technique == "press":
        pos_source = "pos_ratio=12tet; hui_real=table"
    else:
        pos_source = "pos_ratio=k/n; hui_real=interp_from_press_table"

    return {
        "string": c.string,
        "technique": technique,
        "pitch_midi": c.pitch_midi,
        "d_semitones_from_open": c.d_semitones_from_open,
        "pos": {"pos_ratio": c.pos_ratio, "hui_real": c.hui_real, "source": pos_source},
        "temperament": c.temperament,
        "harmonic_n": c.harmonic_n,
        "harmonic_k": c.harmonic_k,
        "cents_error": c.cents_error,
        "source": {"method": "stage1_position_engine"},
    }


def _hui_for_display(choice: dict[str, Any]) -> str | None:
    pos = choice.get("pos") or {}
    hr = pos.get("hui_real")
    if not isinstance(hr, (int, float)):
        return None
    if hr <= 0:
        return None
    hui_int = int(round(float(hr)))
    if 1 <= hui_int <= 13:
        return str(hui_int)
    return "OUT"


def _choice_to_staff2_changes(choice: dict[str, Any]) -> dict[str, str]:
    technique = choice.get("technique")
    string = int(choice["string"])
    changes: dict[str, str] = {
        "form": "simple",
        "lex": "abbr",
        "xian_finger": "勾",
        "xian": str(string),
    }

    hui_display = _hui_for_display(choice)
    if hui_display is not None:
        changes["hui"] = hui_display

    if technique == "open":
        changes["hui_finger"] = "散音"
        changes["sound"] = "open"
        # open 不需要 pos_ratio
        return changes

    if technique == "press":
        changes["hui_finger"] = "大指"
        changes["sound"] = "pressed"
        pos = choice.get("pos") or {}
        pr = pos.get("pos_ratio")
        if not isinstance(pr, (int, float)):
            raise ValueError(f"press 候选缺少 pos_ratio：{choice!r}")
        changes["pos_ratio"] = str(float(pr))
        return changes

    if technique == "harmonic":
        changes["hui_finger"] = "大指"
        changes["sound"] = "harmonic"
        hn = choice.get("harmonic_n")
        if not isinstance(hn, int):
            raise ValueError(f"harmonic 候选缺少 harmonic_n：{choice!r}")
        changes["harmonic_n"] = str(hn)
        hk = choice.get("harmonic_k")
        if isinstance(hk, int):
            changes["harmonic_k"] = str(hk)
        pos = choice.get("pos") or {}
        pr = pos.get("pos_ratio")
        if isinstance(pr, (int, float)):
            changes["pos_ratio"] = str(float(pr))
        return changes

    raise ValueError(f"未知 technique：{technique!r}")


def main() -> None:
    _ensure_backend_src_on_path(REPO_ROOT)

    from guqinauto_backend.domain.musicxml_profile_v0_2 import EditOp, apply_edit_ops, build_score_view
    from guqinauto_backend.engines.position_engine import PositionEngine, PositionEngineOptions
    from guqinauto_backend.engines.stage2_optimizer import Weights, optimize_topk
    from guqinauto_backend.domain.status import compute_status
    from guqinauto_backend.infra.workspace import ProjectTuning

    if not EXAMPLE.exists():
        raise FileNotFoundError(str(EXAMPLE))

    xml0 = EXAMPLE.read_bytes()

    tuning = ProjectTuning(
        name="demo_g_a_c_d_e_g_a",
        open_pitches_midi=[55, 57, 60, 62, 64, 67, 69],
        transpose_semitones=0,
    )

    view0 = build_score_view(project_id="LOCAL", revision="R0", musicxml_bytes=xml0)
    st0 = compute_status(view0, tuning=tuning)

    print("== BEFORE ==")
    print(f"pitch_resolved={st0.pitch_resolved} pitch_issues={len(st0.pitch_issues)}")
    print(f"consistency_warnings={len(st0.consistency_warnings)} (期望：>0，因为 staff2 统一占位)")

    # stage1: enumerate candidates
    engine = PositionEngine(open_pitches_midi=tuning.open_pitches_midi, transpose_semitones=tuning.transpose_semitones)
    opt = PositionEngineOptions(temperament="equal", max_d_semitones=36, include_harmonics=False, max_harmonic_n=12, max_harmonic_cents_error=25.0)

    stage1_events: list[dict[str, Any]] = []
    for m in view0.measures:
        for e in m.events:
            if len(e.staff1_notes) != 1:
                raise ValueError(f"本测试脚本暂不支持 chord：eid={e.eid} staff1_notes={len(e.staff1_notes)}")
            n0 = e.staff1_notes[0]
            if bool(n0.get("is_rest")):
                continue
            pitch_midi = _pitch_dict_to_midi(n0.get("pitch"))  # type: ignore[arg-type]
            cands = engine.enumerate_candidates(pitch_midi=pitch_midi, options=opt)
            stage1_events.append(
                {
                    "eid": e.eid,
                    "targets": [
                        {
                            "slot": None,
                            "pitch_midi": pitch_midi,
                            "candidates": [_candidate_to_api_dict(c) for c in cands],
                        }
                    ],
                }
            )

    # stage2: top-1
    sols = optimize_topk(events=stage1_events, k=1, locks=[], weights=Weights())
    sol0 = sols[0]
    print("== STAGE2 TOP-1 ==")
    print(f"solution_id={sol0.solution_id} total_cost={sol0.total_cost:.4f}")

    # 显式写回（auto draft）
    ops: list[EditOp] = []
    for a in sol0.assignments:
        eid = a["eid"]
        choice = a["choice"]
        changes = _choice_to_staff2_changes(choice)
        ops.append(EditOp(op="update_guqin_event", eid=eid, changes=changes))

    xml1 = apply_edit_ops(musicxml_bytes=xml0, ops=ops, edit_source="auto")
    view1 = build_score_view(project_id="LOCAL", revision="R1", musicxml_bytes=xml1)
    st1 = compute_status(view1, tuning=tuning)

    print("== AFTER (autodraft written back) ==")
    print(f"pitch_resolved={st1.pitch_resolved} pitch_issues={len(st1.pitch_issues)}")
    print(f"consistency_warnings={len(st1.consistency_warnings)} (期望：显著下降，最好为 0)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "after_stage2_autodraft.musicxml").write_bytes(xml1)
    (OUT_DIR / "before_status.json").write_text(json.dumps(asdict(st0), ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "after_status.json").write_text(json.dumps(asdict(st1), ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "stage2_solution.json").write_text(json.dumps(sol0.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
