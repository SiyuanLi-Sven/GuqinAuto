"""
MusicXML staff1 绝对音高（pitch）写回工具。

定位：
- 为满足 stage1/stage2 的 pitch-resolved gate，我们需要能把“绝对 pitch”写回到 MusicXML 真源的 staff1。
- 本模块提供一个**严格**的写回函数：给定 (eid, slot) → pitch(step/alter/octave) 的赋值列表，写回并生成新 MusicXML。

约束（学术级：正确地失败）：
- 不允许猜测 enharmonic（例如 C# vs Db）；调用方必须给出明确 step/alter/octave。
- 找不到目标 note、或出现歧义（同 eid 且 slot 缺失导致多 note），必须失败。
- 若目标 note 是 rest（含 `<rest>`），默认不支持写 pitch（必须失败）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import xml.etree.ElementTree as ET

from ..utils.kv import parse_kv_block


def _strip(text: str | None) -> str:
    return (text or "").strip()


def _find_first_other_technical(note: ET.Element) -> ET.Element | None:
    return note.find(".//other-technical")


def _get_staff(note: ET.Element) -> str | None:
    return note.findtext("staff")


@dataclass(frozen=True)
class PitchValue:
    step: str
    octave: int
    alter: int = 0


@dataclass(frozen=True)
class Staff1PitchAssignment:
    eid: str
    slot: str | None
    pitch: PitchValue


def _set_note_pitch(note: ET.Element, pitch: PitchValue) -> None:
    if note.find("./rest") is not None:
        raise ValueError("staff1 note 为 rest，不支持写入 pitch（请先改为音符）")

    pitch_el = note.find("./pitch")
    if pitch_el is None:
        pitch_el = ET.Element("pitch")
        # MusicXML note 的顺序中 pitch 一般在最前；这里保守插入到开头。
        note.insert(0, pitch_el)

    def set_text(tag: str, value: str) -> None:
        el = pitch_el.find(f"./{tag}")
        if el is None:
            el = ET.SubElement(pitch_el, tag)
        el.text = value

    step = pitch.step.strip().upper()
    if step not in ("A", "B", "C", "D", "E", "F", "G"):
        raise ValueError(f"非法 step：{pitch.step!r}")
    if not (-2 <= int(pitch.alter) <= 2):
        raise ValueError(f"alter 超界（-2..2）：{pitch.alter}")

    set_text("step", step)
    if int(pitch.alter) != 0:
        set_text("alter", str(int(pitch.alter)))
    else:
        # alter=0 时删除该节点，避免误导
        a = pitch_el.find("./alter")
        if a is not None:
            pitch_el.remove(a)
    set_text("octave", str(int(pitch.octave)))


def apply_staff1_pitch_assignments(*, musicxml_bytes: bytes, assignments: list[Staff1PitchAssignment]) -> bytes:
    root = ET.fromstring(musicxml_bytes)
    part = root.find("./part")
    if part is None:
        raise ValueError("缺少 part")

    # 建立 (eid, slot) → note 的索引（全曲范围）
    index: dict[tuple[str, str | None], ET.Element] = {}
    eid_to_notes: dict[str, list[ET.Element]] = {}

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
            slot = kvb.kv.get("slot")
            eid_to_notes.setdefault(eid, []).append(note)
            key = (eid, slot)
            if key in index:
                raise ValueError(f"全曲重复 (eid,slot)：{key}")
            index[key] = note

    for a in assignments:
        if not a.eid:
            raise ValueError("assignment.eid 不能为空")
        if a.slot is None:
            # 若 slot 未提供，则要求该 eid 在 staff1 仅有 1 个 note（非 chord）
            notes = eid_to_notes.get(a.eid) or []
            if len(notes) != 1:
                raise ValueError(f"assignment 未提供 slot，但该 eid 在 staff1 有 {len(notes)} 个 note：eid={a.eid}")
            note = notes[0]
        else:
            key = (a.eid, a.slot)
            if key not in index:
                raise ValueError(f"找不到 staff1 note：eid={a.eid} slot={a.slot!r}")
            note = index[key]

        _set_note_pitch(note, a.pitch)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
