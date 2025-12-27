"""
后端编辑链路最小演示（Profile v0.2）。

目标：
- 使用 `docs/data/examples/guqin_jzp_profile_v0.2_showcase.musicxml` 创建一个 workspace 项目
- 读取事件级 score view（measures/events）
- 对一个事件做一次结构化指法编辑（update_guqin_event）
- 生成新 revision + delta，并把新 MusicXML 写到 temp 输出，便于肉眼检查

注意：
- 本脚本属于开发期/测试脚本，放在 temp/ 下。
- 本仓库运行期禁止依赖 references/；本脚本也不读取 references/。

运行：
  python temp/backend_edit_try_v0_2.py
"""

from __future__ import annotations

import json
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

    from guqinauto_backend.domain.musicxml_profile_v0_2 import EditOp, apply_edit_ops, build_score_view
    from guqinauto_backend.infra.workspace import create_project_from_example, load_project_meta, load_revision_bytes, save_new_revision

    meta = create_project_from_example(name="temp-edit-try", example_filename="guqin_jzp_profile_v0.2_showcase.musicxml")
    print("[create] project_id=", meta.project_id, "revision=", meta.current_revision)

    xml_bytes = load_revision_bytes(meta.project_id, meta.current_revision)
    score0 = build_score_view(project_id=meta.project_id, revision=meta.current_revision, musicxml_bytes=xml_bytes)
    first_event = score0.measures[0].events[0]
    print("[before] eid=", first_event.eid, "jzp_text=", first_event.jzp_text, "kv=", json.dumps(first_event.staff2_kv, ensure_ascii=False))

    # 例：把第一个事件改成“抹三”（右手：抹；弦：3）
    op = EditOp(op="update_guqin_event", eid=first_event.eid, changes={"form": "simple", "xian_finger": "抹", "xian": "3"})
    xml_bytes2 = apply_edit_ops(musicxml_bytes=xml_bytes, ops=[op])

    meta2 = save_new_revision(
        project_id=meta.project_id,
        base_revision=meta.current_revision,
        musicxml_bytes=xml_bytes2,
        delta_ops=[{"op": op.op, "eid": op.eid, "changes": op.changes}],
        message="temp: change first event to 抹三",
    )

    score1 = build_score_view(project_id=meta2.project_id, revision=meta2.current_revision, musicxml_bytes=xml_bytes2)
    first_event_after = score1.measures[0].events[0]
    print("[after]  eid=", first_event_after.eid, "jzp_text=", first_event_after.jzp_text, "kv=", json.dumps(first_event_after.staff2_kv, ensure_ascii=False))

    out_dir = repo_root / "temp" / "out_backend_edit_try"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{meta2.project_id}_{meta.current_revision}_to_{meta2.current_revision}.musicxml"
    out_path.write_bytes(xml_bytes2)
    print("[write]  ", out_path)

    meta_loaded = load_project_meta(meta.project_id)
    print("[meta]   current_revision=", meta_loaded.current_revision)


if __name__ == "__main__":
    main()
