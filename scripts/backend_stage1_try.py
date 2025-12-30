"""
stage1（PositionEngine + /stage1 等价逻辑）开发期尝试脚本。

目标：
- 基于 workspace 项目（由 v0.2 showcase 示例创建）
- 从 MusicXML staff1 读取绝对 pitch（pitch-resolved）
- 使用指定 tuning 枚举每个事件的候选音位（open/press）

运行：
  python scripts/backend_stage1_try.py
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

    from guqinauto_backend.domain.musicxml_profile_v0_2 import build_score_view
    from guqinauto_backend.domain.pitch import MusicXmlPitch
    from guqinauto_backend.engines.position_engine import PositionEngine, PositionEngineOptions
    from guqinauto_backend.infra.workspace import create_project_from_example, load_revision_bytes

    def cand_to_dict(c):
        return {
            "string": c.string,
            "technique": c.technique,
            "pitch_midi": c.pitch_midi,
            "d_semitones_from_open": c.d_semitones_from_open,
            "pos": {"pos_ratio": c.pos_ratio, "hui_real": c.hui_real},
            "temperament": c.temperament,
            "harmonic_n": c.harmonic_n,
            "harmonic_k": c.harmonic_k,
            "cents_error": c.cents_error,
        }

    meta = create_project_from_example(name="temp-stage1-try", example_filename="guqin_jzp_profile_v0.2_showcase.musicxml")
    xml_bytes = load_revision_bytes(meta.project_id, meta.current_revision)
    view = build_score_view(project_id=meta.project_id, revision=meta.current_revision, musicxml_bytes=xml_bytes)

    # 使用项目内置 tuning（已持久化在 project.json）
    engine = PositionEngine(open_pitches_midi=list(meta.tuning.open_pitches_midi), transpose_semitones=meta.tuning.transpose_semitones)
    opt = PositionEngineOptions(temperament="equal", max_d_semitones=36, include_harmonics=False)

    out = []
    for m in view.measures:
        for e in m.events:
            targets = []
            for n in e.staff1_notes:
                slot = n.get("slot")
                p = n.get("pitch")
                if not isinstance(p, dict):
                    raise RuntimeError(f"pitch-unresolved：eid={e.eid} slot={slot!r}")
                pitch = MusicXmlPitch(step=str(p["step"]), octave=int(p["octave"]), alter=int(p.get("alter", 0)))
                midi = pitch.to_midi()
                candidates = engine.enumerate_candidates(pitch_midi=midi, options=opt)
                targets.append({"slot": slot, "pitch_midi": midi, "candidates": [cand_to_dict(c) for c in candidates]})
            out.append({"eid": e.eid, "targets": targets})

    print(json.dumps(out[:5], ensure_ascii=False, indent=2))
    print(f"[OK] events={len(out)}  (printed first 5)")


if __name__ == "__main__":
    main()
