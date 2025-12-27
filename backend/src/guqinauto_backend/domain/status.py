"""
项目状态与就绪性检查（面向前端 UI）。

定位：
- GuqinAuto 的推荐/优化链路（stage1/stage2）有明确的就绪条件：pitch-resolved（staff1 绝对 pitch 已落地）。
- 前端需要一个轻量端点判断“当前项目能否跑 stage1/stage2”，并给出不可用原因（正确地失败）。
- 同时，编辑器允许“简谱（staff1 pitch）”与“减字谱（staff2 指法真值）”在编辑过程中暂时不一致；
  我们持续做一致性检查，对不一致点给出提示（不阻塞编辑，但不允许静默忽略）。

约束：
- 该模块只做诊断，不修改真源。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .musicxml_profile_v0_2 import ProjectScoreView
from ..infra.workspace import ProjectTuning
from .guqin_fingering_pitch import derive_expected_pitches, staff1_pitch_dict_to_midi


@dataclass(frozen=True)
class PitchIssue:
    eid: str
    slot: str | None
    reason: str


@dataclass(frozen=True)
class ConsistencyWarning:
    """不阻塞编辑，但需要在 UI 中提示的“一致性问题”。

    约束：
    - 能检查：输出 expected/actual（并给出 reason）
    - 不能检查：reason 明确说明“为什么不能检查”（例如缺少 v0.3 真值）
    """

    eid: str
    slot: str | None
    reason: str
    expected_pitch_midi: int | None = None
    actual_pitch_midi: int | None = None


@dataclass(frozen=True)
class ProjectStatus:
    pitch_resolved: bool
    pitch_issues: list[PitchIssue]
    has_chords: bool
    consistency_warnings: list[ConsistencyWarning]


def compute_status(view: ProjectScoreView, *, tuning: ProjectTuning | None = None) -> ProjectStatus:
    issues: list[PitchIssue] = []
    warnings: list[ConsistencyWarning] = []
    has_chords = False
    for m in view.measures:
        for e in m.events:
            if len(e.staff1_notes) > 1:
                has_chords = True
            if not e.staff1_notes:
                issues.append(PitchIssue(eid=e.eid, slot=None, reason="staff1_missing_notes"))
                continue
            for n in e.staff1_notes:
                slot = n.get("slot") if isinstance(n, dict) else None
                pitch = n.get("pitch") if isinstance(n, dict) else None
                is_rest = bool(n.get("is_rest")) if isinstance(n, dict) else False
                if is_rest:
                    continue
                if not isinstance(pitch, dict) or "step" not in pitch or "octave" not in pitch:
                    issues.append(PitchIssue(eid=e.eid, slot=str(slot) if slot is not None else None, reason="pitch_unresolved"))

            if tuning is None:
                continue

            derived, notes = derive_expected_pitches(e.staff2_kv, tuning=tuning)

            if not derived:
                # 避免 v0.2 阶段“全曲 warning”：只有当事件已带 v0.3 字段时，才提示不可检查。
                if any(k in e.staff2_kv for k in ("sound", "pos_ratio", "l_sound", "l_pos_ratio", "r_sound", "r_pos_ratio")):
                    warnings.append(ConsistencyWarning(eid=e.eid, slot=None, reason="guqin_pitch_uncheckable:" + ",".join(notes or ["unknown"])))
                continue

            # staff1: slot -> midi
            actual_by_slot: dict[str | None, int | None] = {}
            for n in e.staff1_notes:
                slot = n.get("slot") if isinstance(n, dict) else None
                pitch = n.get("pitch") if isinstance(n, dict) else None
                actual_by_slot[str(slot) if slot is not None else None] = staff1_pitch_dict_to_midi(pitch)  # type: ignore[arg-type]

            for dp in derived:
                act = actual_by_slot.get(dp.slot)
                if act is None:
                    warnings.append(
                        ConsistencyWarning(
                            eid=e.eid,
                            slot=dp.slot,
                            reason="staff1_pitch_missing_cannot_check",
                            expected_pitch_midi=dp.expected_midi,
                            actual_pitch_midi=None,
                        )
                    )
                elif act != dp.expected_midi:
                    warnings.append(
                        ConsistencyWarning(
                            eid=e.eid,
                            slot=dp.slot,
                            reason=f"pitch_mismatch:{dp.method}",
                            expected_pitch_midi=dp.expected_midi,
                            actual_pitch_midi=act,
                        )
                    )

    return ProjectStatus(pitch_resolved=(len(issues) == 0), pitch_issues=issues, has_chords=has_chords, consistency_warnings=warnings)


def status_to_dict(status: ProjectStatus) -> dict[str, Any]:
    return {
        "pitch_resolved": status.pitch_resolved,
        "has_chords": status.has_chords,
        "pitch_issues": [{"eid": i.eid, "slot": i.slot, "reason": i.reason} for i in status.pitch_issues],
        "consistency_warnings": [
            {
                "eid": w.eid,
                "slot": w.slot,
                "reason": w.reason,
                "expected_pitch_midi": w.expected_pitch_midi,
                "actual_pitch_midi": w.actual_pitch_midi,
            }
            for w in status.consistency_warnings
        ],
    }
