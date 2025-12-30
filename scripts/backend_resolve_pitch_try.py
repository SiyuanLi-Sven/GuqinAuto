"""
后端 pitch-resolved 写回链路演示（/resolve_pitch 等价逻辑）。

目标：
- 创建一个示例项目
- 对某个 (eid, slot) 写回 staff1 pitch
- 生成新 revision，并确保仍能 build_score_view

运行：
  python scripts/backend_resolve_pitch_try.py
"""

from __future__ import annotations

from pathlib import Path
import sys


def _ensure_backend_src_on_path(repo_root: Path) -> None:
    src_dir = repo_root / "backend" / "src"
    if not src_dir.exists():
        raise RuntimeError(f"找不到 backend/src：{src_dir}")
    sys.path.insert(0, str(src_dir))


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    _ensure_backend_src_on_path(repo_root)

    from guqinauto_backend.domain.musicxml_profile_v0_2 import build_score_view
    from guqinauto_backend.domain.musicxml_staff1_pitch import PitchValue, Staff1PitchAssignment, apply_staff1_pitch_assignments
    from guqinauto_backend.infra.workspace import create_project_from_example, load_revision_bytes, save_new_revision

    meta = create_project_from_example(name="temp-resolve-pitch", example_filename="guqin_jzp_profile_v0.2_showcase.musicxml")
    xml_bytes = load_revision_bytes(meta.project_id, meta.current_revision)

    view0 = build_score_view(project_id=meta.project_id, revision=meta.current_revision, musicxml_bytes=xml_bytes)
    e = view0.measures[0].events[0]
    before = e.staff1_notes[0].get("pitch")
    print("[before] eid=", e.eid, "pitch=", before)

    # 示例：把该音强行设为 C#4（仅为验证写回链路）
    slot = e.staff1_notes[0].get("slot")
    new_xml = apply_staff1_pitch_assignments(
        musicxml_bytes=xml_bytes,
        assignments=[Staff1PitchAssignment(eid=e.eid, slot=slot, pitch=PitchValue(step="C", alter=1, octave=4))],
    )

    meta2 = save_new_revision(
        project_id=meta.project_id,
        base_revision=meta.current_revision,
        musicxml_bytes=new_xml,
        delta_ops=[{"op": "resolve_pitch_demo", "eid": e.eid, "slot": slot, "pitch": {"step": "C", "alter": 1, "octave": 4}}],
        message="temp: resolve pitch demo",
    )

    view1 = build_score_view(project_id=meta2.project_id, revision=meta2.current_revision, musicxml_bytes=new_xml)
    after = view1.measures[0].events[0].staff1_notes[0].get("pitch")
    print("[after]  eid=", e.eid, "pitch=", after)
    print("[meta]   revision=", meta.current_revision, "->", meta2.current_revision)


if __name__ == "__main__":
    main()
