"""
单事件 stage1 候选 → 写回 → 一致性 warning 下降（最小回归测试）。

定位：
- 编辑器 MVP 允许用户点选某个事件（eid），从 stage1 候选中手工挑一个写回（edit_source=user）。
- 本脚本在不启动后端服务的情况下，直接复用 domain/确认这一闭环至少在数据层面可行：
  - 读入 Mary 示例（staff1 pitch+节奏 + staff2 统一占位）
  - 对第一个事件跑 stage1，取一个候选写回为 v0.3 真值字段
  - 断言：一致性 warnings 至少下降 1（不会“虚假成功”）

用法：
  python scripts/test_single_event_stage1_apply.py
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]


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

    xml_path = REPO_ROOT / "docs" / "data" / "examples" / "guqin_jzp_profile_v0.3_mary_had_a_little_lamb_input.musicxml"
    xml = xml_path.read_bytes()

    view0 = build_score_view(project_id="TEST", revision="R000001", musicxml_bytes=xml)
    tuning = ProjectTuning.default_demo()
    st0 = compute_status(view0, tuning=tuning)
    assert st0.pitch_resolved, f"预期 pitch_resolved=True，实际={st0.pitch_resolved}"
    assert len(st0.consistency_warnings) > 0, "基准示例应存在一致性 warnings（staff2 占位）"

    first_event = None
    for m in view0.measures:
        if m.events:
            first_event = m.events[0]
            break
    assert first_event is not None, "示例应至少包含一个事件"

    n0 = first_event.staff1_notes[0]
    pitch = n0.get("pitch")
    assert isinstance(pitch, dict) and "step" in pitch and "octave" in pitch, "示例 staff1 pitch 应已是绝对值"

    # stage1：枚举候选（只要存在一个即可）
    opt = PositionEngineOptions()
    engine = PositionEngine(open_pitches_midi=list(tuning.open_pitches_midi), transpose_semitones=tuning.transpose_semitones)
    target_midi = MusicXmlPitch(step=str(pitch["step"]), alter=int(pitch.get("alter", 0)), octave=int(pitch["octave"])).to_midi()
    candidates = engine.enumerate_candidates(pitch_midi=target_midi, options=opt)
    assert candidates, "stage1 应该能给出至少一个候选（检查调弦/示例 pitch）"
    c = candidates[0]

    # 写回：尽量与前端编辑器一致（MVP：只写结构化真值字段；读法层字段可后续再编辑）
    changes: dict[str, str] = {"xian": str(int(c.string))}
    if c.technique == "open":
        changes["sound"] = "open"
    elif c.technique == "press":
        changes["sound"] = "pressed"
        assert c.pos_ratio is not None
        changes["pos_ratio"] = str(float(c.pos_ratio))
    elif c.technique == "harmonic":
        changes["sound"] = "harmonic"
        assert c.harmonic_n is not None
        changes["harmonic_n"] = str(int(c.harmonic_n))
        if c.harmonic_k is not None:
            changes["harmonic_k"] = str(int(c.harmonic_k))
        if c.pos_ratio is not None:
            changes["pos_ratio"] = str(float(c.pos_ratio))
    else:
        raise AssertionError(f"未知 technique：{c.technique!r}")

    xml2 = apply_edit_ops(
        musicxml_bytes=xml,
        ops=[EditOp(op="update_guqin_event", eid=first_event.eid, changes=changes)],
        edit_source="user",
    )

    view1 = build_score_view(project_id="TEST", revision="R000002", musicxml_bytes=xml2)
    st1 = compute_status(view1, tuning=tuning)
    assert st1.pitch_resolved, "写回不应破坏 pitch_resolved"
    assert len(st1.consistency_warnings) <= len(st0.consistency_warnings) - 1, (
        f"预期 warnings 至少下降 1，实际 before={len(st0.consistency_warnings)} after={len(st1.consistency_warnings)}"
    )

    print(
        f"[OK] single-event stage1 apply: warnings {len(st0.consistency_warnings)} -> {len(st1.consistency_warnings)}"
    )


if __name__ == "__main__":
    main()
