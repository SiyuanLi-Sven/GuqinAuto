"""
complex chord（撮/和弦）: stage1 候选 → 手工选择 → 写回（最小回归测试）。

定位：
- 编辑器现在支持：当 staff2 事件为 form=complex 且 staff1 slot=L/R 时，
  从 stage1 候选中分别选择 L/R 两个音的候选，并写回为 v0.3 真值字段（l_*/r_*）。
- 本脚本不依赖后端服务进程，直接在 domain 层验证“写回后的 Profile 仍可解析/校验”。

用法：
  python scripts/test_complex_chord_stage1_manual_apply.py
"""

from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "docs" / "data" / "old" / "guqin_jzp_profile_v0.2_complex_chord.musicxml"


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

    xml = EXAMPLE.read_bytes()
    view0 = build_score_view(project_id="TEST", revision="R000001", musicxml_bytes=xml)
    tuning = ProjectTuning.default_demo()
    st0 = compute_status(view0, tuning=tuning)
    if not st0.pitch_resolved:
        raise AssertionError(f"示例应 pitch_resolved=True（否则 stage1 无法运行），issues={len(st0.pitch_issues)}")

    # 找到一个 complex chord 事件
    ev = None
    for m in view0.measures:
        for e in m.events:
            if e.staff2_kv.get("form") == "complex" and len(e.staff1_notes) == 2:
                slots = sorted({str(n.get("slot") or "") for n in e.staff1_notes})
                if slots == ["L", "R"]:
                    ev = e
                    break
        if ev:
            break
    if ev is None:
        raise AssertionError("未在示例中找到 form=complex 且 staff1 slot=L/R 的 2-note chord 事件")

    # stage1：分别对 L/R 枚举候选
    engine = PositionEngine(open_pitches_midi=list(tuning.open_pitches_midi), transpose_semitones=tuning.transpose_semitones)
    opt = PositionEngineOptions()

    def pick_candidate(slot: str):
        note = next(n for n in ev.staff1_notes if n.get("slot") == slot)
        pitch = note.get("pitch")
        if not isinstance(pitch, dict) or "step" not in pitch or "octave" not in pitch:
            raise AssertionError(f"slot={slot} 缺少 pitch dict")
        midi = MusicXmlPitch(step=str(pitch["step"]), alter=int(pitch.get("alter", 0)), octave=int(pitch["octave"])).to_midi()
        cands = engine.enumerate_candidates(pitch_midi=midi, options=opt)
        if not cands:
            raise AssertionError(f"slot={slot} 无候选（检查调弦/示例 pitch）")
        return cands[0]

    l = pick_candidate("L")
    # 物理约束：同一时刻一根弦不能发两个音；因此右手 slot 选择必须避开 l.string
    r0 = pick_candidate("R")
    if int(r0.string) == int(l.string):
        # 尝试找一个不同弦的候选（优先 press）
        note_r = next(n for n in ev.staff1_notes if n.get("slot") == "R")
        pitch_r = note_r.get("pitch")
        if not isinstance(pitch_r, dict) or "step" not in pitch_r or "octave" not in pitch_r:
            raise AssertionError("slot=R 缺少 pitch dict")
        midi_r = MusicXmlPitch(step=str(pitch_r["step"]), alter=int(pitch_r.get("alter", 0)), octave=int(pitch_r["octave"])).to_midi()
        cands_r = engine.enumerate_candidates(pitch_midi=midi_r, options=opt)
        r_alt = next((c for c in cands_r if c.technique == "press" and int(c.string) != int(l.string)), None)
        if r_alt is None:
            r_alt = next((c for c in cands_r if int(c.string) != int(l.string)), None)
        if r_alt is None:
            raise AssertionError("slot=R 未找到与 L 不冲突的候选（弦号必须不同）")
        r = r_alt
    else:
        r = r0

    # 写回 v0.3（l_*/r_*）
    changes: dict[str, str] = {
        "l_xian": str(int(l.string)),
        "r_xian": str(int(r.string)),
    }

    def write(prefix: str, c) -> None:
        if c.technique == "open":
            changes[f"{prefix}sound"] = "open"
            return
        if c.technique == "press":
            if c.pos_ratio is None:
                raise AssertionError(f"{prefix} press 缺少 pos_ratio")
            changes[f"{prefix}sound"] = "pressed"
            changes[f"{prefix}pos_ratio"] = str(float(c.pos_ratio))
            return
        if c.technique == "harmonic":
            if c.harmonic_n is None:
                raise AssertionError(f"{prefix} harmonic 缺少 harmonic_n")
            changes[f"{prefix}sound"] = "harmonic"
            changes[f"{prefix}harmonic_n"] = str(int(c.harmonic_n))
            if c.harmonic_k is not None:
                changes[f"{prefix}harmonic_k"] = str(int(c.harmonic_k))
            if c.pos_ratio is not None:
                changes[f"{prefix}pos_ratio"] = str(float(c.pos_ratio))
            return
        raise AssertionError(f"未知 technique：{c.technique!r}")

    write("l_", l)
    write("r_", r)

    xml2 = apply_edit_ops(
        musicxml_bytes=xml,
        ops=[EditOp(op="update_guqin_event", eid=ev.eid, changes=changes)],
        edit_source="user",
    )

    view1 = build_score_view(project_id="TEST", revision="R000002", musicxml_bytes=xml2)
    st1 = compute_status(view1, tuning=tuning)
    if not st1.pitch_resolved:
        raise AssertionError("写回不应破坏 pitch_resolved")

    # 只要能解析就算通过；warnings 变化不强制（示例可能含多个占位事件）
    ev1 = next(e for m in view1.measures for e in m.events if e.eid == ev.eid)
    if not (ev1.staff2_kv.get("l_sound") and ev1.staff2_kv.get("r_sound")):
        raise AssertionError("写回后应包含 l_sound/r_sound")

    print(f"[OK] complex chord stage1 manual apply: eid={ev.eid} l={l.technique}:{l.string} r={r.technique}:{r.string}")


if __name__ == "__main__":
    main()
