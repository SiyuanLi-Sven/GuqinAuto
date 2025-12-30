"""
pitch-unresolved → compile_pitch_from_jianpu 演示脚本（开发期）。

目标：
- 创建示例项目（v0.2 showcase）
- 人为删除一个事件的 staff1 pitch，使其变为 pitch-unresolved
- 调用编译器（从 jianpu_text=lyric@above + 给定 tonic/mode）写回 pitch

运行：
  python scripts/backend_compile_pitch_from_jianpu_try.py
"""

from __future__ import annotations

from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def _ensure_backend_src_on_path(repo_root: Path) -> None:
    src_dir = repo_root / "backend" / "src"
    if not src_dir.exists():
        raise RuntimeError(f"找不到 backend/src：{src_dir}")
    sys.path.insert(0, str(src_dir))


def _strip(text: str | None) -> str:
    return (text or "").strip()


def _find_first_other_technical(note: ET.Element) -> ET.Element | None:
    return note.find(".//other-technical")


def _get_staff(note: ET.Element) -> str | None:
    return note.findtext("staff")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    _ensure_backend_src_on_path(repo_root)

    from guqinauto_backend.utils.kv import parse_kv_block
    from guqinauto_backend.domain.musicxml_profile_v0_2 import build_score_view
    from guqinauto_backend.domain.status import compute_status
    from guqinauto_backend.infra.workspace import create_project_from_example, load_revision_bytes, save_new_revision
    from guqinauto_backend.domain.jianpu_pitch_compiler import parse_degree, compile_degree_to_pitch
    from guqinauto_backend.domain.musicxml_staff1_pitch import PitchValue, Staff1PitchAssignment, apply_staff1_pitch_assignments
    from guqinauto_backend.domain.pitch import MusicXmlPitch

    meta = create_project_from_example(name="temp-compile-pitch", example_filename="guqin_jzp_profile_v0.2_showcase.musicxml")
    xml_bytes = load_revision_bytes(meta.project_id, meta.current_revision)

    # 1) 删除第一个 staff1 note 的 pitch，使其 unresolved
    root = ET.fromstring(xml_bytes)
    part = root.find("./part")
    assert part is not None
    target_eid = None
    removed = False
    for m in part.findall("./measure"):
        for note in m.findall("./note"):
            if _get_staff(note) != "1":
                continue
            other = _find_first_other_technical(note)
            if other is None:
                continue
            kvb = parse_kv_block(_strip(other.text))
            if kvb.prefix != "GuqinLink":
                continue
            eid = kvb.kv.get("eid")
            if not eid:
                continue
            p = note.find("./pitch")
            if p is not None:
                note.remove(p)
                target_eid = eid
                removed = True
                break
        if removed:
            break

    if not removed or target_eid is None:
        raise RuntimeError("未找到可删除 pitch 的 staff1 note")

    xml_bytes_unresolved = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    meta2 = save_new_revision(
        project_id=meta.project_id,
        base_revision=meta.current_revision,
        musicxml_bytes=xml_bytes_unresolved,
        delta_ops=[{"op": "temp_remove_pitch", "eid": target_eid}],
        message="temp: remove staff1 pitch",
    )
    view_un = build_score_view(project_id=meta2.project_id, revision=meta2.current_revision, musicxml_bytes=xml_bytes_unresolved)
    st0 = compute_status(view_un)
    print("[unresolved] pitch_resolved=", st0.pitch_resolved, "issues=", len(st0.pitch_issues), "sample=", st0.pitch_issues[0].eid if st0.pitch_issues else None)

    # 2) 仅编译并写回这个 eid（演示）；规则：从 jianpu_text 读 degree（必须是 '1'..'7'）
    # tonic 设为 C4 major（仅用于示例）
    tonic = MusicXmlPitch(step="C", alter=0, octave=4)
    mode = "major"
    # 找到对应事件的 jianpu_text
    jtext = None
    for m in view_un.measures:
        for e in m.events:
            if e.eid == target_eid:
                jtext = e.jianpu_text
                break
    if jtext is None:
        raise RuntimeError("找不到 target eid 的 jianpu_text")
    degree = parse_degree(jtext)
    cp = compile_degree_to_pitch(degree=degree, tonic=tonic, mode=mode, octave_shift=0)

    xml_fixed = apply_staff1_pitch_assignments(
        musicxml_bytes=xml_bytes_unresolved,
        assignments=[Staff1PitchAssignment(eid=target_eid, slot=None, pitch=PitchValue(step=cp.step, alter=cp.alter, octave=cp.octave))],
    )
    meta3 = save_new_revision(
        project_id=meta.project_id,
        base_revision=meta2.current_revision,
        musicxml_bytes=xml_fixed,
        delta_ops=[{"op": "temp_compile_pitch_from_jianpu", "eid": target_eid, "tonic": {"step": "C", "alter": 0, "octave": 4}, "mode": "major"}],
        message="temp: compile pitch from jianpu",
    )
    view_fixed = build_score_view(project_id=meta3.project_id, revision=meta3.current_revision, musicxml_bytes=xml_fixed)
    st1 = compute_status(view_fixed)
    print("[fixed]     pitch_resolved=", st1.pitch_resolved, "issues=", len(st1.pitch_issues))


if __name__ == "__main__":
    main()
