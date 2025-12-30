"""
stage2（Top-K 推荐，不写回）开发期尝试脚本。

目标：
- 用 v0.2 的 stage2 序列示例创建项目
- 调用 /stage2 等价逻辑（直接调用 api_stage2）拿到 top-K 推荐

运行：
  python scripts/backend_stage2_try.py
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

    from guqinauto_backend.infra.workspace import create_project_from_example
    from guqinauto_backend.api.server import Stage2Request, Stage2Preferences, api_stage2

    meta = create_project_from_example(name="temp-stage2-try", example_filename="guqin_jzp_profile_v0.2_stage2_sequence.musicxml")

    req = Stage2Request(
        base_revision=meta.current_revision,
        k=3,
        tuning=None,  # 使用项目 tuning
        apply_mode="none",
        preferences=Stage2Preferences(shift=1.0, string_change=0.6, technique_change=0.2, harmonic_penalty=0.2, cents_error=0.01),
    )
    out = api_stage2(meta.project_id, req)

    # 打印第一条方案的前 5 个 eid 的选择摘要（string/technique/pos_ratio）
    sol0 = out["stage2"]["solutions"][0]
    summary = []
    for a in sol0["assignments"][:5]:
        c = a["choice"]
        summary.append(
            {
                "eid": a["eid"],
                "string": c["string"],
                "technique": c["technique"],
                "pos_ratio": c["pos"]["pos_ratio"],
            }
        )

    print(json.dumps({"total_cost": sol0["total_cost"], "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
