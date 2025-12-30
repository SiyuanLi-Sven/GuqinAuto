"""
apply_edit_ops 支持显式删除 KV 字段（value=null）回归测试。

定位：
- 为了支持“重复推荐覆盖 auto 结果”以及“用户在已有 v0.3 真值字段上改技法”，我们需要能删除互斥字段。
- 约定：EditOp.changes 中 value=None 表示删除该 key（写回时 key 从 KV 中移除）。

用法：
  python scripts/test_apply_edit_ops_delete_fields.py
"""

from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "docs" / "data" / "examples" / "guqin_jzp_profile_v0.3_mary_had_a_little_lamb_input.musicxml"


def _ensure_backend_src_on_path(repo_root: Path) -> None:
    src_dir = repo_root / "backend" / "src"
    if not src_dir.exists():
        raise RuntimeError(f"找不到 backend/src：{src_dir}")
    sys.path.insert(0, str(src_dir))


def main() -> None:
    _ensure_backend_src_on_path(REPO_ROOT)

    from guqinauto_backend.domain.musicxml_profile_v0_2 import EditOp, apply_edit_ops, build_score_view

    xml0 = EXAMPLE.read_bytes()
    view0 = build_score_view(project_id="TEST", revision="R000001", musicxml_bytes=xml0)
    eid = view0.measures[0].events[0].eid

    # 先写一个 pressed（带 pos_ratio）
    xml1 = apply_edit_ops(
        musicxml_bytes=xml0,
        ops=[
            EditOp(
                op="update_guqin_event",
                eid=eid,
                changes={
                    "sound": "pressed",
                    "pos_ratio": "0.123",
                },
            )
        ],
        edit_source="auto",
    )
    view1 = build_score_view(project_id="TEST", revision="R000002", musicxml_bytes=xml1)
    ev1 = next(e for m in view1.measures for e in m.events if e.eid == eid)
    assert ev1.staff2_kv.get("sound") == "pressed"
    assert "pos_ratio" in ev1.staff2_kv

    # 再改成 open：必须显式删除 pos_ratio，否则 Profile 校验会失败
    xml2 = apply_edit_ops(
        musicxml_bytes=xml1,
        ops=[
            EditOp(
                op="update_guqin_event",
                eid=eid,
                changes={
                    "sound": "open",
                    "pos_ratio": None,
                    "harmonic_n": None,
                    "harmonic_k": None,
                    "pos_ratio_1": None,
                    "pos_ratio_2": None,
                    "pos_ratio_3": None,
                    "pos_ratio_4": None,
                    "pos_ratio_5": None,
                    "pos_ratio_6": None,
                    "pos_ratio_7": None,
                },
            )
        ],
        edit_source="user",
    )

    view2 = build_score_view(project_id="TEST", revision="R000003", musicxml_bytes=xml2)
    ev2 = next(e for m in view2.measures for e in m.events if e.eid == eid)
    assert ev2.staff2_kv.get("sound") == "open"
    assert "pos_ratio" not in ev2.staff2_kv

    print(f"[OK] delete kv fields works: eid={eid}")


if __name__ == "__main__":
    main()
