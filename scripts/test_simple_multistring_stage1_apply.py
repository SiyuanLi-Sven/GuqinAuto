"""
simple 多弦（历）: stage1 候选 → 手工写回 pressed(pos_ratio_1..N) → 一致性检查（最小回归）。

用法：
  python scripts/test_simple_multistring_stage1_apply.py
"""

from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "docs" / "data" / "examples" / "guqin_jzp_profile_v0.3_simple_multistring_li.musicxml"


def _ensure_backend_src_on_path(repo_root: Path) -> None:
    src_dir = repo_root / "backend" / "src"
    if not src_dir.exists():
        raise RuntimeError(f"找不到 backend/src：{src_dir}")
    sys.path.insert(0, str(src_dir))


def main() -> None:
    _ensure_backend_src_on_path(REPO_ROOT)

    from guqinauto_backend.domain.musicxml_profile_v0_2 import EditOp, apply_edit_ops, build_score_view
    from guqinauto_backend.domain.pitch import MusicXmlPitch
    from guqinauto_backend.domain.status import compute_status
    from guqinauto_backend.engines.position_engine import PositionEngine, PositionEngineOptions
    from guqinauto_backend.infra.workspace import ProjectTuning

    xml0 = EXAMPLE.read_bytes()
    view0 = build_score_view(project_id="TEST", revision="R000001", musicxml_bytes=xml0)
    tuning = ProjectTuning.default_demo()

    ev0 = view0.measures[0].events[0]
    assert ev0.staff2_kv.get("form") == "simple"
    assert ev0.staff2_kv.get("xian_finger") == "历"
    assert len(ev0.staff1_notes) == 2

    st0 = compute_status(view0, tuning=tuning)
    assert st0.pitch_resolved

    engine = PositionEngine(open_pitches_midi=list(tuning.open_pitches_midi), transpose_semitones=tuning.transpose_semitones)
    opt = PositionEngineOptions()

    pressed_choices = []
    used_strings: set[int] = set()
    for note in sorted(ev0.staff1_notes, key=lambda n: int(str(n.get("slot") or "0") or "0")):
        slot = str(note.get("slot") or "")
        pitch = note.get("pitch")
        assert isinstance(pitch, dict) and "step" in pitch and "octave" in pitch
        midi = MusicXmlPitch(step=str(pitch["step"]), alter=int(pitch.get("alter", 0)), octave=int(pitch["octave"])).to_midi()
        cands = engine.enumerate_candidates(pitch_midi=midi, options=opt)
        press = next((c for c in cands if c.technique == "press" and int(c.string) not in used_strings), None)
        assert press is not None, f"slot={slot} 未找到可用 press 候选（需要弦号不重复）"
        used_strings.add(int(press.string))
        pressed_choices.append((slot, press))

    # 写回：sound=pressed + pos_ratio_1..2
    pressed_choices.sort(key=lambda x: int(x[0]))
    strings = [str(int(c.string)) for _, c in pressed_choices]
    changes: dict[str, str | None] = {"sound": "pressed", "xian": ",".join(strings)}
    for k in ("pos_ratio", "harmonic_n", "harmonic_k"):
        changes[k] = None
    for i in range(1, 8):
        changes[f"pos_ratio_{i}"] = None
    for i, (_, c) in enumerate(pressed_choices, start=1):
        assert c.pos_ratio is not None
        changes[f"pos_ratio_{i}"] = str(float(c.pos_ratio))

    xml1 = apply_edit_ops(
        musicxml_bytes=xml0,
        ops=[EditOp(op="update_guqin_event", eid=ev0.eid, changes=changes)],
        edit_source="auto",
    )
    view1 = build_score_view(project_id="TEST", revision="R000002", musicxml_bytes=xml1)
    st1 = compute_status(view1, tuning=tuning)
    assert st1.pitch_resolved

    # 该事件应当可校验且无 mismatch（我们选的候选就是按 staff1 pitch 枚举出来的）
    related = [w for w in st1.consistency_warnings if w.eid == ev0.eid]
    assert not related, f"预期该事件无一致性 warnings，实际={related!r}"

    print(f"[OK] simple multistring apply: eid={ev0.eid} xian={','.join(strings)}")


if __name__ == "__main__":
    main()
