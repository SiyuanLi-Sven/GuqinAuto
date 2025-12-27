"""
GuqinJZP-MusicXML Profile v0.2：读取、校验、渲染 jzp_text、应用编辑 delta。

定位：
- 这是后端领域逻辑：把 MusicXML 真源解析成事件级结构；对 GuqinJZP@0.2 做严格校验；
  支持对事件进行“字段级编辑”，并写回 MusicXML（生成新 revision）。

边界：
- 本模块只覆盖 Profile v0.2 约定的槽位（GuqinLink@0.2 / GuqinJZP@0.2 / GuqinTok@0.2）。
- 不尝试“猜测/降级”；遇到不一致必须抛错。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
import xml.etree.ElementTree as ET

from guqinjzp.jianzipu_text import JianzipuTokenSets, parse_puzi_text

from ..utils.kv import KVBlock, dump_kv_block, parse_kv_block
from ..utils.paths import find_repo_root


Lex = Literal["abbr", "ortho"]
EditSource = Literal["auto", "user"]


def _strip(text: str | None) -> str:
    return (text or "").strip()


def _find_first_other_technical(note: ET.Element) -> ET.Element | None:
    return note.find(".//other-technical")


def _get_staff(note: ET.Element) -> str | None:
    return note.findtext("staff")


def _get_note_duration(note: ET.Element) -> int:
    t = note.findtext("duration")
    if t is None:
        raise ValueError("note 缺少 duration")
    return int(t)


def _pitch_to_dict(note: ET.Element) -> dict[str, Any] | None:
    pitch = note.find("./pitch")
    if pitch is None:
        return None
    step = pitch.findtext("./step")
    octave = pitch.findtext("./octave")
    alter = pitch.findtext("./alter")
    if step is None or octave is None:
        return None
    out: dict[str, Any] = {"step": step, "octave": int(octave)}
    if alter is not None:
        out["alter"] = int(alter)
    return out


def _ensure_lyric_below(note: ET.Element) -> ET.Element:
    for lyric in note.findall("./lyric"):
        if lyric.get("placement") == "below":
            t = lyric.find("text")
            if t is None:
                t = ET.SubElement(lyric, "text")
            return t
    lyric = ET.SubElement(note, "lyric", {"number": "1", "placement": "below"})
    t = ET.SubElement(lyric, "text")
    return t


def _cn_num_1_to_13(n: int) -> str:
    if not (1 <= n <= 13):
        raise ValueError(f"数字超界（期望 1..13）：{n}")
    ones = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
    if n < 10:
        return ones[n]
    if n == 10:
        return "十"
    if n == 11:
        return "十一"
    if n == 12:
        return "十二"
    if n == 13:
        return "十三"
    raise AssertionError("unreachable")


def _parse_int_csv(value: str, *, min_v: int, max_v: int) -> list[int]:
    items = [s for s in value.split(",") if s != ""]
    if not items:
        raise ValueError("空列表")
    out: list[int] = []
    for s in items:
        n = int(s)
        if not (min_v <= n <= max_v):
            raise ValueError(f"数值超界：{n} not in [{min_v},{max_v}]")
        out.append(n)
    return out


HUI_FINGER_ABBR = {
    "散音": "散",
    "散": "散",
    "大指": "大",
    "大": "大",
    "食指": "食",
    "食": "食",
    "中指": "中",
    "中": "中",
    "名指": "名",
    "名": "名",
    "跪指": "跪",
    "跪": "跪",
}

HUI_FINGER_ORTHO = {
    "散音": "散音",
    "散": "散音",
    "大指": "大指",
    "大": "大指",
    "食指": "食指",
    "食": "食指",
    "中指": "中指",
    "中": "中指",
    "名指": "名指",
    "名": "名指",
    "跪指": "跪指",
    "跪": "跪指",
}


def _normalize_hui_finger(token: str, lex: Lex) -> str:
    if lex == "abbr":
        return HUI_FINGER_ABBR.get(token, token)
    if lex == "ortho":
        return HUI_FINGER_ORTHO.get(token, token)
    raise ValueError(f"未知 lex：{lex!r}")


def _render_hui(hui: str | None, fen: str | None, *, lex: Lex) -> str:
    if hui is None:
        if fen is not None:
            raise ValueError("存在 fen 但缺少 hui")
        return ""

    if hui == "OUT":
        if fen is not None:
            raise ValueError("hui=OUT 时不允许 fen")
        return "外" if lex == "abbr" else "徽外"

    hui_n = int(hui)
    hui_cn = _cn_num_1_to_13(hui_n)
    if lex == "abbr":
        if fen is None:
            return hui_cn
        if fen == "HALF":
            return hui_cn + "半"
        fen_cn = _cn_num_1_to_13(int(fen))
        return hui_cn + fen_cn

    if lex == "ortho":
        base = hui_cn + "徽"
        if fen is None:
            return base
        if fen == "HALF":
            return base + "半"
        fen_cn = _cn_num_1_to_13(int(fen))
        return base + fen_cn + "分"

    raise ValueError(f"未知 lex：{lex!r}")


def _render_xian_list(xian_list: list[int], *, lex: Lex) -> str:
    if lex == "abbr":
        return "".join(_cn_num_1_to_13(n) for n in xian_list)
    if lex == "ortho":
        return "".join(_cn_num_1_to_13(n) + "弦" for n in xian_list)
    raise ValueError(f"未知 lex：{lex!r}")


def render_jzp_text_from_kv(kv: dict[str, str], token_sets: JianzipuTokenSets) -> str:
    form = kv["form"]
    lex: Lex = kv.get("lex", "abbr")  # type: ignore[assignment]
    if lex not in ("abbr", "ortho"):
        raise ValueError(f"lex 非法：{lex!r}")

    # 元数据字段（不参与 jzp_text 的生成，但必须合法；用于区分“用户改过/没改过”与“当前真值来源”）。
    truth_src = kv.get("truth_src")
    if truth_src is not None and truth_src not in ("auto", "user"):
        raise ValueError(f"truth_src 非法（期望 auto/user）：{truth_src!r}")
    user_touched = kv.get("user_touched")
    if user_touched is not None and user_touched not in ("0", "1"):
        raise ValueError(f"user_touched 非法（期望 '0'/'1'）：{user_touched!r}")

    def ensure_in(token: str, allowed: frozenset[str], name: str) -> None:
        if token not in allowed:
            raise ValueError(f"{name} 不在 token 规范内：{token!r}")

    if form == "simple":
        xian_finger = kv["xian_finger"]
        ensure_in(xian_finger, token_sets.xian_finger, "xian_finger")
        xian_list = _parse_int_csv(kv["xian"], min_v=1, max_v=7)
        if len(xian_list) not in (1, 2):
            raise ValueError(f"xian 列表长度仅支持 1 或 2：{xian_list!r}")

        hui_finger = kv.get("hui_finger")
        hui = kv.get("hui")
        fen = kv.get("fen")
        special = kv.get("special")

        if (hui is not None or fen is not None) and hui_finger is None:
            raise ValueError("simple：存在 hui/fen 但缺少 hui_finger（不符合读法语法）")

        out = ""
        if hui_finger is not None:
            ensure_in(hui_finger, token_sets.hui_finger, "hui_finger")
            out += _normalize_hui_finger(hui_finger, lex)
        out += _render_hui(hui, fen, lex=lex)
        if special is not None:
            ensure_in(special, token_sets.special_finger, "special")
            out += special
        out += xian_finger
        out += _render_xian_list(xian_list, lex=lex)
        return out

    if form == "complex":
        complex_finger = kv["complex_finger"]
        ensure_in(complex_finger, token_sets.complex_finger, "complex_finger")

        def render_sub(prefix: str) -> str:
            hf = kv.get(f"{prefix}_hui_finger")
            hui = kv.get(f"{prefix}_hui")
            fen = kv.get(f"{prefix}_fen")
            special = kv.get(f"{prefix}_special")
            xian = kv[f"{prefix}_xian"]
            xian_i = int(xian)
            if not (1 <= xian_i <= 7):
                raise ValueError(f"{prefix}_xian 超界：{xian_i}")

            out = ""
            if hf is not None:
                ensure_in(hf, token_sets.hui_finger, f"{prefix}_hui_finger")
                out += _normalize_hui_finger(hf, lex)
            out += _render_hui(hui, fen, lex=lex)
            if special is not None:
                ensure_in(special, token_sets.special_finger, f"{prefix}_special")
                out += special
            out += _render_xian_list([xian_i], lex=lex)
            return out

        return complex_finger + render_sub("l") + render_sub("r")

    if form == "aside":
        modifier = kv.get("modifier")
        special = kv.get("special")
        move_finger = kv["move_finger"]
        hui = kv.get("hui")
        fen = kv.get("fen")

        out = ""
        if modifier is not None:
            ensure_in(modifier, token_sets.modifier, "modifier")
            out += modifier
        if special is not None:
            ensure_in(special, token_sets.special_finger, "special")
            out += special
        ensure_in(move_finger, token_sets.move_finger, "move_finger")
        out += move_finger
        out += _render_hui(hui, fen, lex=lex)
        return out

    if form == "marker":
        marker = kv["marker"]
        ensure_in(marker, token_sets.marker, "marker")
        return marker

    if form == "both":
        bf = kv["both_finger"]
        ensure_in(bf, token_sets.both_finger, "both_finger")
        return bf

    raise ValueError(f"未知 form：{form!r}")


def validate_jzp_text_parseable(text: str, *, lex: Lex, token_sets: JianzipuTokenSets) -> None:
    _ = parse_puzi_text(text, lex=lex, token_sets=token_sets)


@dataclass(frozen=True)
class ProjectScoreEvent:
    eid: str
    duration: int
    staff1_notes: list[dict[str, Any]]
    staff2_kv: dict[str, str]
    jzp_text: str
    jianpu_text: str | None


@dataclass(frozen=True)
class ProjectScoreTime:
    """小节拍号（time signature）。"""

    beats: int
    beat_type: int


@dataclass(frozen=True)
class ProjectScoreMeasure:
    number: str
    divisions: int | None
    time: ProjectScoreTime | None
    events: list[ProjectScoreEvent]


@dataclass(frozen=True)
class ProjectScoreView:
    project_id: str
    revision: str
    measures: list[ProjectScoreMeasure]


def load_token_sets_from_repo() -> JianzipuTokenSets:
    repo_root = find_repo_root()
    return JianzipuTokenSets.load_from_repo(repo_root)


def _collect_staff1_events(measure: ET.Element) -> list[tuple[str, list[ET.Element]]]:
    out: list[tuple[str, list[ET.Element]]] = []
    current_eid: str | None = None
    current_notes: list[ET.Element] = []

    for note in measure.findall("./note"):
        if _get_staff(note) != "1":
            continue
        other = _find_first_other_technical(note)
        if other is None:
            raise ValueError("staff1 note 缺少 other-technical（GuqinLink@0.2）")
        kvb = parse_kv_block(_strip(other.text))
        if kvb.prefix != "GuqinLink" or kvb.version != "0.2":
            raise ValueError(f"staff1 other-technical 不是 GuqinLink@0.2：{_strip(other.text)!r}")
        eid = kvb.kv.get("eid")
        if eid is None:
            raise ValueError("GuqinLink@0.2 缺少 eid")

        if current_eid is None:
            current_eid = eid
            current_notes = [note]
            continue

        if eid == current_eid:
            current_notes.append(note)
        else:
            out.append((current_eid, current_notes))
            current_eid = eid
            current_notes = [note]

    if current_eid is not None:
        out.append((current_eid, current_notes))
    return out


def _collect_staff2_by_eid(measure: ET.Element) -> dict[str, ET.Element]:
    out: dict[str, ET.Element] = {}
    for note in measure.findall("./note"):
        if _get_staff(note) != "2":
            continue
        other = _find_first_other_technical(note)
        if other is None:
            raise ValueError("staff2 note 缺少 other-technical（GuqinJZP@0.2）")
        kvb = parse_kv_block(_strip(other.text))
        if kvb.prefix != "GuqinJZP" or kvb.version not in ("0.2", "0.3"):
            raise ValueError(f"staff2 other-technical 不是 GuqinJZP@0.2/@0.3：{_strip(other.text)!r}")
        eid = kvb.kv.get("eid")
        if eid is None:
            raise ValueError("GuqinJZP@0.2 缺少 eid")
        if eid in out:
            raise ValueError(f"measure 内重复 eid（staff2）：{eid}")
        out[eid] = note
    return out


def build_score_view(*, project_id: str, revision: str, musicxml_bytes: bytes) -> ProjectScoreView:
    token_sets = load_token_sets_from_repo()
    root = ET.fromstring(musicxml_bytes)
    part = root.find("./part")
    if part is None:
        raise ValueError("缺少 part")

    measures: list[ProjectScoreMeasure] = []
    cur_divisions: int | None = None
    cur_time: ProjectScoreTime | None = None
    for m in part.findall("./measure"):
        m_no = m.get("number") or ""

        # MusicXML 的 attributes 可以出现在任意小节；缺省时沿用上一小节的配置。
        attr = m.find("./attributes")
        if attr is not None:
            div_t = _strip(attr.findtext("./divisions"))
            if div_t:
                cur_divisions = int(div_t)
            beats_t = _strip(attr.findtext("./time/beats"))
            beat_type_t = _strip(attr.findtext("./time/beat-type"))
            if beats_t and beat_type_t:
                cur_time = ProjectScoreTime(beats=int(beats_t), beat_type=int(beat_type_t))

        staff1_events = _collect_staff1_events(m)
        staff2_map = _collect_staff2_by_eid(m)

        events: list[ProjectScoreEvent] = []
        for eid, staff1_notes in staff1_events:
            if eid not in staff2_map:
                raise ValueError(f"staff1 有 eid 但 staff2 缺少对应事件：measure={m_no} eid={eid}")
            staff2_note = staff2_map[eid]
            staff2_other = _find_first_other_technical(staff2_note)
            assert staff2_other is not None
            jzp_kv = parse_kv_block(_strip(staff2_other.text)).kv
            duration = _get_note_duration(staff2_note)
            if any(_get_note_duration(n) != duration for n in staff1_notes):
                raise ValueError(f"staff1/staff2 duration 不一致：measure={m_no} eid={eid}")

            jzp_text = render_jzp_text_from_kv(jzp_kv, token_sets)
            validate_jzp_text_parseable(jzp_text, lex=jzp_kv.get("lex", "abbr"), token_sets=token_sets)  # type: ignore[arg-type]

            jianpu_text = None
            first_staff1 = staff1_notes[0]
            for lyric in first_staff1.findall("./lyric"):
                if lyric.get("placement") == "above":
                    jianpu_text = _strip(lyric.findtext("text"))
                    break

            s1_notes: list[dict[str, Any]] = []
            for n in staff1_notes:
                other = _find_first_other_technical(n)
                assert other is not None
                link_kv = parse_kv_block(_strip(other.text)).kv
                slot = link_kv.get("slot")
                string = n.findtext(".//string")
                is_rest = n.find("./rest") is not None
                s1_notes.append(
                    {
                        "slot": slot,
                        "string": int(string) if string is not None else None,
                        "pitch": _pitch_to_dict(n),
                        "is_rest": bool(is_rest),
                    }
                )

            events.append(
                ProjectScoreEvent(
                    eid=eid,
                    duration=duration,
                    staff1_notes=s1_notes,
                    staff2_kv=jzp_kv,
                    jzp_text=jzp_text,
                    jianpu_text=jianpu_text,
                )
            )

        measures.append(ProjectScoreMeasure(number=m_no, divisions=cur_divisions, time=cur_time, events=events))

    return ProjectScoreView(project_id=project_id, revision=revision, measures=measures)


EditOpType = Literal["update_guqin_event"]


@dataclass(frozen=True)
class EditOp:
    op: EditOpType
    eid: str
    changes: dict[str, str]


def apply_edit_ops(*, musicxml_bytes: bytes, ops: list[EditOp], edit_source: EditSource = "user") -> bytes:
    token_sets = load_token_sets_from_repo()
    root = ET.fromstring(musicxml_bytes)
    part = root.find("./part")
    if part is None:
        raise ValueError("缺少 part")

    # 建立 eid → staff2 note 的索引（全曲范围）
    staff2_notes: dict[str, tuple[ET.Element, ET.Element, str]] = {}
    for m in part.findall("./measure"):
        for note in m.findall("./note"):
            if _get_staff(note) != "2":
                continue
            other = _find_first_other_technical(note)
            if other is None:
                continue
            kvb = parse_kv_block(_strip(other.text))
            if kvb.prefix != "GuqinJZP" or kvb.version not in ("0.2", "0.3"):
                continue
            eid = kvb.kv.get("eid")
            if eid is None:
                continue
            if eid in staff2_notes:
                raise ValueError(f"全曲重复 eid（staff2）：{eid}")
            staff2_notes[eid] = (note, other, kvb.version)

    for op in ops:
        if op.op != "update_guqin_event":
            raise ValueError(f"未知 op：{op.op!r}")
        if op.eid not in staff2_notes:
            raise ValueError(f"找不到 eid 对应的 staff2 事件：{op.eid}")
        note, other, version = staff2_notes[op.eid]
        kvb = parse_kv_block(_strip(other.text))
        kv = dict(kvb.kv)

        # 强约束：不允许修改 eid/prefix/version
        if "eid" in op.changes and op.changes["eid"] != op.eid:
            raise ValueError("不允许修改 eid（事件身份必须稳定）")

        for k, v in op.changes.items():
            if k == "eid":
                continue
            kv[k] = v

        # 补齐/更新元数据（不影响谱字读法生成）：
        # - truth_src：当前真值来源（auto/user）
        # - user_touched：是否“曾被用户改过”（单调：一旦为 1，就不允许回到 0）
        kv["truth_src"] = edit_source
        if edit_source == "user":
            kv["user_touched"] = "1"
        else:
            if kv.get("user_touched") not in ("0", "1"):
                kv["user_touched"] = "0"
            # 若已为 1，则保持 1（单调）

        # 必填检查
        if kv.get("eid") != op.eid:
            raise ValueError("GuqinJZP@0.2: eid 不一致")
        if "form" not in kv:
            raise ValueError("GuqinJZP@0.2: 缺少 form")

        # 渲染 + 可解析性校验（学术级：不通过即失败）
        jzp_text = render_jzp_text_from_kv(kv, token_sets)
        lex: Lex = kv.get("lex", "abbr")  # type: ignore[assignment]
        validate_jzp_text_parseable(jzp_text, lex=lex, token_sets=token_sets)

        # 写回 other-technical 与 lyric below（显示缓存）
        other.text = dump_kv_block("GuqinJZP", version, kv)
        lyric_text_el = _ensure_lyric_below(note)
        lyric_text_el.text = jzp_text

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
