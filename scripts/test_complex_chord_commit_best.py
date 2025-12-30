"""
端到端回归测试：2-note complex chord 的 stage1+stage2 推荐与“写回 v0.3 真值字段”。

覆盖目标：
- stage2 已支持 targets=2 的 chord 推荐（输出 assignments[].choices[]）。
- 对于 staff2 已是 form=complex 且 slot=L/R 的事件，我们应当能把 stage2 的选择写回为：
  - l_sound/r_sound
  - l_pos_ratio/r_pos_ratio 或 l_harmonic_n/r_harmonic_n
  - 并自动升级 GuqinJZP@0.2 -> GuqinJZP@0.3（由 apply_edit_ops 执行）

注意：
- 本脚本不依赖后端服务进程，只复用后端模块。
- 输出写到 temp/out_chord_commit_best/，便于人工检查。
"""

from __future__ import annotations

import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "docs/data/old/guqin_jzp_profile_v0.2_complex_chord.musicxml"
OUT_DIR = REPO_ROOT / "temp/out_chord_commit_best"


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
    return {
        "string": c.string,
        "technique": c.technique,
        "pos": {"pos_ratio": c.pos_ratio, "hui_real": c.hui_real},
        "cents_error": c.cents_error,
        "harmonic_n": c.harmonic_n,
        "harmonic_k": c.harmonic_k,
    }


def _sound_fields_from_choice(choice: dict[str, Any], *, prefix: str) -> dict[str, str]:
    technique = str(choice.get("technique") or "")
    if technique == "open":
        return {f"{prefix}sound": "open"}
    if technique == "press":
        pos = choice.get("pos") or {}
        pr = pos.get("pos_ratio")
        if not isinstance(pr, (int, float)):
            raise ValueError(f"press 候选缺少 pos_ratio：{choice!r}")
        return {f"{prefix}sound": "pressed", f"{prefix}pos_ratio": str(float(pr))}
    if technique == "harmonic":
        hn = choice.get("harmonic_n")
        if not isinstance(hn, int):
            raise ValueError(f"harmonic 候选缺少 harmonic_n：{choice!r}")
        out: dict[str, str] = {f"{prefix}sound": "harmonic", f"{prefix}harmonic_n": str(int(hn))}
        hk = choice.get("harmonic_k")
        if isinstance(hk, int):
            out[f"{prefix}harmonic_k"] = str(int(hk))
        return out
    raise ValueError(f"未知 technique：{technique!r}")


def main() -> None:
    _ensure_backend_src_on_path(REPO_ROOT)

    from guqinauto_backend.domain.musicxml_profile_v0_2 import EditOp, apply_edit_ops, build_score_view
    from guqinauto_backend.domain.status import compute_status
    from guqinauto_backend.engines.position_engine import PositionEngine, PositionEngineOptions
    from guqinauto_backend.engines.stage2_optimizer import Weights, optimize_topk
    from guqinauto_backend.infra.workspace import ProjectTuning

    if not EXAMPLE.exists():
        raise FileNotFoundError(str(EXAMPLE))

    xml0 = EXAMPLE.read_bytes()
    view0 = build_score_view(project_id="LOCAL", revision="R0", musicxml_bytes=xml0)
    tuning = ProjectTuning.default_demo()

    if sum(1 for m in view0.measures for e in m.events if len(e.staff1_notes) > 1) != 1:
        raise ValueError("示例预期只有 1 个 chord 事件")

    # stage1
    engine = PositionEngine(open_pitches_midi=list(tuning.open_pitches_midi), transpose_semitones=tuning.transpose_semitones)
    opt = PositionEngineOptions(temperament="equal", max_d_semitones=36, include_harmonics=False)

    stage1_events: list[dict[str, Any]] = []
    for m in view0.measures:
        for e in m.events:
            if len(e.staff1_notes) != 2:
                raise ValueError(f"本示例要求 staff1_notes=2：eid={e.eid}")
            targets: list[dict[str, Any]] = []
            for n in e.staff1_notes:
                slot = n.get("slot")
                if slot not in ("L", "R"):
                    raise ValueError(f"本示例要求 slot=L/R：eid={e.eid} slot={slot!r}")
                if bool(n.get("is_rest")):
                    raise ValueError("本示例不应含 rest")
                midi = _pitch_dict_to_midi(n.get("pitch"))  # type: ignore[arg-type]
                cands = engine.enumerate_candidates(pitch_midi=midi, options=opt)
                targets.append({"slot": slot, "candidates": [_candidate_to_api_dict(c) for c in cands]})
            stage1_events.append({"eid": e.eid, "targets": targets})

    # chord locks：显式指定 slot（避免歧义）
    locks = [{"eid": stage1_events[0]["eid"], "fields": {"slot": "L", "technique": "press"}}]
    from guqinauto_backend.engines.stage2_optimizer import Lock as Stage2Lock

    sols = optimize_topk(
        events=stage1_events,
        k=1,
        locks=[Stage2Lock(eid=lk["eid"], fields=lk["fields"]) for lk in locks],
        weights=Weights(),
    )
    sol0 = sols[0]
    a0 = sol0.assignments[0]
    if "choices" not in a0:
        raise ValueError(f"期望 chord assignment 使用 choices：{a0!r}")
    by_slot = {it["slot"]: it["choice"] for it in a0["choices"]}
    if set(by_slot.keys()) != {"L", "R"}:
        raise ValueError(f"期望 slot=L/R：{by_slot.keys()!r}")

    # 写回：仅写 v0.3 真值字段（并更新 l_xian/r_xian），不动 complex_finger/读法层字段。
    eid = a0["eid"]
    changes: dict[str, str] = {
        "form": "complex",
        "l_xian": str(int(by_slot["L"]["string"])),
        "r_xian": str(int(by_slot["R"]["string"])),
    }
    changes.update(_sound_fields_from_choice(by_slot["L"], prefix="l_"))
    changes.update(_sound_fields_from_choice(by_slot["R"], prefix="r_"))

    xml1 = apply_edit_ops(musicxml_bytes=xml0, ops=[EditOp(op="update_guqin_event", eid=eid, changes=changes)], edit_source="auto")

    # 断言：已自动升级到 GuqinJZP@0.3 且包含 l_sound/r_sound
    s = xml1.decode("utf-8", errors="replace")
    if "GuqinJZP@0.3" not in s:
        raise ValueError("写回后未升级到 GuqinJZP@0.3（期望 apply_edit_ops 自动升级）")
    if "l_sound=" not in s or "r_sound=" not in s:
        raise ValueError("写回后缺少 l_sound/r_sound")
    if not re.search(r"l_(sound|pos_ratio|harmonic_n)=", s):
        raise ValueError("写回后缺少任何 l_* v0.3 字段")

    view1 = build_score_view(project_id="LOCAL", revision="R1", musicxml_bytes=xml1)
    st1 = compute_status(view1, tuning=tuning)
    if not st1.pitch_resolved:
        raise ValueError(f"pitch_resolved=False：{asdict(st1)!r}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "after_commit_best_complex_chord.musicxml").write_bytes(xml1)
    (OUT_DIR / "stage2_solution.json").write_text(str(sol0.__dict__), encoding="utf-8")
    (OUT_DIR / "status_after.json").write_text(str(asdict(st1)), encoding="utf-8")


if __name__ == "__main__":
    main()
