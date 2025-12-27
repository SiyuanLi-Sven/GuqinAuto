"""
MusicXML pitch 解析与绝对音高（MIDI note number）转换。

定位：
- stage1(PositionEngine) 的输入必须是绝对音高；本模块提供 MusicXML <pitch> → MIDI 的最小实现。
- 本仓库坚持 MusicXML 为唯一真源；绝对 pitch 必须在 staff1 中“编译落地”。

约束：
- 解析失败必须显式抛错，不允许猜测或静默降级（学术级：正确地失败）。
"""

from __future__ import annotations

from dataclasses import dataclass


STEP_TO_SEMITONE = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}


@dataclass(frozen=True)
class MusicXmlPitch:
    """MusicXML pitch 三元组（step/alter/octave）。"""

    step: str
    octave: int
    alter: int = 0

    def to_midi(self) -> int:
        """转换为 MIDI note number（C4=60）。"""

        step = self.step.strip().upper()
        if step not in STEP_TO_SEMITONE:
            raise ValueError(f"未知 step：{self.step!r}")
        if not (-2 <= self.alter <= 2):
            raise ValueError(f"alter 超出常见范围（-2..2）：{self.alter}")
        if not (-1 <= self.octave <= 9):
            raise ValueError(f"octave 超出常见范围（-1..9）：{self.octave}")

        # MusicXML octave 定义：C4 为中央 C；MIDI 以 C-1=0，因此 midi = (octave+1)*12 + pc
        pc = STEP_TO_SEMITONE[step] + int(self.alter)
        return int((self.octave + 1) * 12 + pc)


