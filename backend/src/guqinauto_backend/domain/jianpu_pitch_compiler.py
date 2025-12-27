"""
简谱（jianpu）→ staff1 绝对 pitch 编译器（写回真源）。

定位：
- 本项目允许导入“只含简谱度数”的数据形态，但 stage1/stage2 的硬前提是 pitch-resolved。
- 本模块提供一种严格、可解释、不会猜测 enharmonic 的编译方式：
  - 输入：主音（明确的 step/alter/octave），调式（major/minor），以及每个事件的简谱度数（目前仅支持 1..7）
  - 输出：对每个事件（eid, slot=None 的单音事件）生成一个明确的 MusicXML pitch(step/alter/octave)

约束（学术级：正确地失败）：
- 不支持从 MIDI 反推 step（会引入 enharmonic 猜测）；主音必须以 step/alter/octave 明确给出。
- 当前只支持度数为单个字符 '1'..'7' 的简谱文本；出现升降号/八度点/连音等必须失败。
- 当前只支持单音事件（staff1 对应 eid 仅 1 个 note）；chord 必须失败，避免错误传播。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .pitch import MusicXmlPitch, STEP_TO_SEMITONE


Mode = Literal["major", "minor"]


MAJOR_OFFSETS = (0, 2, 4, 5, 7, 9, 11)
NATURAL_MINOR_OFFSETS = (0, 2, 3, 5, 7, 8, 10)

DIATONIC_STEPS = ("C", "D", "E", "F", "G", "A", "B")


@dataclass(frozen=True)
class CompiledPitch:
    step: str
    alter: int
    octave: int


def parse_degree(jianpu_text: str) -> int:
    s = (jianpu_text or "").strip()
    if s == "":
        raise ValueError("简谱文本为空，无法编译绝对 pitch")
    if len(s) != 1 or s not in "1234567":
        raise ValueError(f"当前仅支持度数为单个字符 '1'..'7'：收到 {s!r}")
    return int(s)


def _offsets_for_mode(mode: Mode) -> tuple[int, ...]:
    if mode == "major":
        return MAJOR_OFFSETS
    if mode == "minor":
        return NATURAL_MINOR_OFFSETS
    raise ValueError(f"未知 mode：{mode!r}")


def compile_degree_to_pitch(*, degree: int, tonic: MusicXmlPitch, mode: Mode, octave_shift: int = 0) -> CompiledPitch:
    """把简谱度数编译为 MusicXML pitch（step/alter/octave）。

    约定：
    - tonic 表示“度数 1”的明确 pitch（含 step/alter/octave）
    - octave_shift 为整八度移位（当前不从简谱文本推断点位；由调用方显式给出）
    """

    if not (1 <= degree <= 7):
        raise ValueError(f"degree 超界：{degree}")

    tonic_step = tonic.step.strip().upper()
    if tonic_step not in STEP_TO_SEMITONE:
        raise ValueError(f"非法 tonic.step：{tonic.step!r}")

    offsets = _offsets_for_mode(mode)
    semitone_offset = offsets[degree - 1] + 12 * int(octave_shift)
    target_midi = tonic.to_midi() + int(semitone_offset)

    # 目标音符字母 = 在字母序列中平移 degree-1（按 diatonic 语义保持记谱一致性，不做 enharmonic 猜测）
    tonic_idx = DIATONIC_STEPS.index(tonic_step)
    diatonic_shift = degree - 1
    target_idx = tonic_idx + diatonic_shift
    octave_carry = target_idx // 7
    target_step = DIATONIC_STEPS[target_idx % 7]
    target_octave = int(tonic.octave) + int(octave_carry) + int(octave_shift)

    natural_midi = MusicXmlPitch(step=target_step, octave=target_octave, alter=0).to_midi()
    alter = int(target_midi - natural_midi)
    if not (-2 <= alter <= 2):
        raise ValueError(
            f"无法用常见 alter(-2..2) 表达该度数：degree={degree} mode={mode} tonic={tonic} -> step={target_step} octave={target_octave} target_midi={target_midi} natural_midi={natural_midi} alter={alter}"
        )

    return CompiledPitch(step=target_step, alter=alter, octave=target_octave)
