"""
验证 GuqinJZP-MusicXML Profile v0.2/v0.3 的示例文件。

定位：
- 这是一个“样例级”校验脚本，用于快速检查 docs/data/examples 下的 v0.2/v0.3 MusicXML：
  - KV 串可解析
  - 必填字段齐全
  - token/数字取值在约束范围内
  - 能从结构化字段生成 jzp_text，并与 lyric below 对齐（若存在）
  - 生成出的 jzp_text 能被本仓库内置的“减字谱读法解析器”接受

注意：
- 项目明令禁止运行期依赖 `references`；因此本脚本只能引用仓库内的实现。
- 该脚本放在 temp/ 下，作为开发期的“主动测试/检查样本”工具，不作为正式库代码发布。
"""

from __future__ import annotations
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "docs" / "data" / "examples"

# 允许以 `python temp/xxx.py` 的方式运行时也能 import 后端代码（backend/src）。
BACKEND_SRC = ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))


def _strip_text(text: str | None) -> str:
    return (text or "").strip()


def parse_kv(text: str) -> tuple[str, str, dict[str, str]]:
    text = _strip_text(text)
    parts = [p for p in text.split(";") if p != ""]
    if not parts:
        raise ValueError("空 KV 文本")

    head = parts[0]
    if "@" not in head:
        raise ValueError(f"KV head 缺少版本：{head!r}")
    prefix, version = head.split("@", 1)
    if prefix == "" or version == "":
        raise ValueError(f"KV head 非法：{head!r}")

    kv: dict[str, str] = {}
    for seg in parts[1:]:
        if "=" not in seg:
            raise ValueError(f"KV 段缺少 '='：{seg!r}")
        k, v = seg.split("=", 1)
        if k == "":
            raise ValueError(f"KV key 为空：{seg!r}")
        if "\n" in v or ";" in v:
            raise ValueError(f"KV value 非法（含换行/分号）：{k}={v!r}")
        if k in kv:
            raise ValueError(f"KV key 重复：{k!r}")
        if v == "":
            raise ValueError(f"KV value 为空（建议省略该 key）：{k!r}")
        kv[k] = v

    return prefix, version, kv


def cn_num_1_to_13(n: int) -> str:
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


def parse_int_csv(value: str, *, min_v: int, max_v: int) -> list[int]:
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


@dataclass(frozen=True)
class TokenSets:
    hui_finger: set[str]
    xian_finger: set[str]
    move_finger: set[str]
    special_finger: set[str]
    modifier: set[str]
    both_finger: set[str]
    complex_finger: set[str]
    marker: set[str]


def load_token_sets() -> TokenSets:
    from guqinjzp.jianzipu_text import JianzipuTokenSets

    token_sets = JianzipuTokenSets.load_from_repo(ROOT)
    return TokenSets(
        hui_finger=set(token_sets.hui_finger),
        xian_finger=set(token_sets.xian_finger),
        move_finger=set(token_sets.move_finger),
        special_finger=set(token_sets.special_finger),
        modifier=set(token_sets.modifier),
        both_finger=set(token_sets.both_finger),
        complex_finger=set(token_sets.complex_finger),
        marker=set(token_sets.marker),
    )


def normalize_hui_finger(token: str, lex: str) -> str:
    if lex == "abbr":
        return HUI_FINGER_ABBR.get(token, token)
    if lex == "ortho":
        return HUI_FINGER_ORTHO.get(token, token)
    raise ValueError(f"未知 lex：{lex!r}")


def render_hui(hui: str | None, fen: str | None, *, lex: str) -> str:
    if hui is None:
        if fen is not None:
            raise ValueError("存在 fen 但缺少 hui")
        return ""

    if hui == "OUT":
        if fen is not None:
            raise ValueError("hui=OUT 时不允许 fen")
        return "外" if lex == "abbr" else "徽外"

    hui_n = int(hui)
    hui_cn = cn_num_1_to_13(hui_n)
    if lex == "abbr":
        if fen is None:
            return hui_cn
        if fen == "HALF":
            return hui_cn + "半"
        fen_cn = cn_num_1_to_13(int(fen))
        return hui_cn + fen_cn

    if lex == "ortho":
        base = hui_cn + "徽"
        if fen is None:
            return base
        if fen == "HALF":
            return base + "半"
        fen_cn = cn_num_1_to_13(int(fen))
        return base + fen_cn + "分"

    raise ValueError(f"未知 lex：{lex!r}")


def render_xian_list(xian_list: list[int], *, lex: str) -> str:
    if lex == "abbr":
        return "".join(cn_num_1_to_13(n) for n in xian_list)
    if lex == "ortho":
        return "".join(cn_num_1_to_13(n) + "弦" for n in xian_list)
    raise ValueError(f"未知 lex：{lex!r}")


def render_jzp_text(kv: dict[str, str], token_sets: TokenSets) -> str:
    form = kv["form"]
    lex = kv.get("lex", "abbr")

    if form == "simple":
        xian_finger = kv["xian_finger"]
        if xian_finger not in token_sets.xian_finger:
            raise ValueError(f"xian_finger 不在集合内：{xian_finger!r}")
        xian_list = parse_int_csv(kv["xian"], min_v=1, max_v=7)
        if len(xian_list) not in (1, 2):
            raise ValueError(f"xian 列表长度仅支持 1 或 2（对齐 jianzipu 渲染能力）：{xian_list!r}")

        hui_finger = kv.get("hui_finger")
        hui = kv.get("hui")
        fen = kv.get("fen")
        special = kv.get("special")

        out = ""
        if hui_finger is not None:
            if hui_finger not in token_sets.hui_finger:
                raise ValueError(f"hui_finger 不在集合内：{hui_finger!r}")
            out += normalize_hui_finger(hui_finger, lex)
        out += render_hui(hui, fen, lex=lex)
        if special is not None:
            if special not in token_sets.special_finger:
                raise ValueError(f"special 不在集合内：{special!r}")
            out += special
        out += xian_finger
        out += render_xian_list(xian_list, lex=lex)
        return out

    if form == "complex":
        complex_finger = kv["complex_finger"]
        if complex_finger not in token_sets.complex_finger:
            raise ValueError(f"complex_finger 不在集合内：{complex_finger!r}")

        def render_sub(prefix: str) -> str:
            hf = kv.get(f"{prefix}_hui_finger")
            hui = kv.get(f"{prefix}_hui")
            fen = kv.get(f"{prefix}_fen")
            special = kv.get(f"{prefix}_special")
            xian = kv[f"{prefix}_xian"]
            xian_list = [int(xian)]
            if not (1 <= xian_list[0] <= 7):
                raise ValueError(f"{prefix}_xian 超界：{xian_list[0]}")

            out = ""
            if hf is not None:
                if hf not in token_sets.hui_finger:
                    raise ValueError(f"{prefix}_hui_finger 不在集合内：{hf!r}")
                out += normalize_hui_finger(hf, lex)
            out += render_hui(hui, fen, lex=lex)
            if special is not None:
                if special not in token_sets.special_finger:
                    raise ValueError(f"{prefix}_special 不在集合内：{special!r}")
                out += special
            out += render_xian_list(xian_list, lex=lex)
            return out

        return complex_finger + render_sub("l") + render_sub("r")

    if form == "aside":
        lex = kv.get("lex", "abbr")
        modifier = kv.get("modifier")
        special = kv.get("special")
        move_finger = kv["move_finger"]
        hui = kv.get("hui")
        fen = kv.get("fen")

        out = ""
        if modifier is not None:
            if modifier not in token_sets.modifier:
                raise ValueError(f"modifier 不在集合内：{modifier!r}")
            out += modifier
        if special is not None:
            if special not in token_sets.special_finger:
                raise ValueError(f"special 不在集合内：{special!r}")
            out += special
        if move_finger not in token_sets.move_finger:
            raise ValueError(f"move_finger 不在集合内：{move_finger!r}")
        out += move_finger
        out += render_hui(hui, fen, lex=lex)
        return out

    if form == "marker":
        marker = kv["marker"]
        if marker not in token_sets.marker:
            raise ValueError(f"marker 不在集合内：{marker!r}")
        return marker

    if form == "both":
        bf = kv["both_finger"]
        if bf not in token_sets.both_finger:
            raise ValueError(f"both_finger 不在集合内：{bf!r}")
        return bf

    raise ValueError(f"未知 form：{form!r}")


def validate_jzp_text_parseable(text: str, *, lex: str, token_sets: TokenSets) -> None:
    from guqinjzp.jianzipu_text import JianzipuTokenSets, parse_puzi_text

    if lex not in ("abbr", "ortho"):
        raise ValueError(f"lex 非法：{lex!r}")
    # 复用同一份 token 规范（将 TokenSets 转回 JianzipuTokenSets）
    jt = JianzipuTokenSets(
        hui_finger=frozenset(token_sets.hui_finger),
        xian_finger=frozenset(token_sets.xian_finger),
        move_finger=frozenset(token_sets.move_finger),
        special_finger=frozenset(token_sets.special_finger),
        modifier=frozenset(token_sets.modifier),
        both_finger=frozenset(token_sets.both_finger),
        complex_finger=frozenset(token_sets.complex_finger),
        marker=frozenset(token_sets.marker),
    )
    _ = parse_puzi_text(text, lex=lex, token_sets=jt)


def iter_notes_with_staff(part: ET.Element, staff_number: str) -> list[ET.Element]:
    notes: list[ET.Element] = []
    for note in part.findall(".//note"):
        staff = note.findtext("staff")
        if staff == staff_number:
            notes.append(note)
    return notes


def get_other_technical_text(note: ET.Element) -> str | None:
    for other in note.findall(".//other-technical"):
        return _strip_text(other.text)
    return None


def get_lyric_below_text(note: ET.Element) -> str | None:
    for lyric in note.findall("./lyric"):
        placement = lyric.get("placement")
        if placement == "below":
            return _strip_text(lyric.findtext("text"))
    return None


def validate_example(path: Path, token_sets: TokenSets) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    part = root.find("./part")
    if part is None:
        raise ValueError("缺少 part")

    staff1_notes = iter_notes_with_staff(part, "1")
    staff2_notes = iter_notes_with_staff(part, "2")

    staff1_links: dict[str, list[dict[str, str]]] = {}
    for n in staff1_notes:
        t = get_other_technical_text(n)
        if not t:
            continue
        prefix, version, kv = parse_kv(t)
        if prefix != "GuqinLink" or version != "0.2":
            continue
        eid = kv.get("eid")
        if eid is None:
            raise ValueError("GuqinLink 缺少 eid")
        staff1_links.setdefault(eid, []).append(kv)

    staff2_events: dict[str, dict[str, str]] = {}
    for n in staff2_notes:
        t = get_other_technical_text(n)
        if not t:
            continue
        prefix, version, kv = parse_kv(t)
        if prefix != "GuqinJZP" or version not in ("0.2", "0.3"):
            continue
        eid = kv.get("eid")
        if eid is None:
            raise ValueError("GuqinJZP 缺少 eid")
        if eid in staff2_events:
            raise ValueError(f"重复 eid（staff2）：{eid}")
        staff2_events[eid] = kv

        rendered = render_jzp_text(kv, token_sets)
        lyric = get_lyric_below_text(n)
        if lyric is not None and lyric != rendered:
            raise ValueError(f"lyric below 与生成 jzp_text 不一致：eid={eid} lyric={lyric!r} rendered={rendered!r}")

        lex = kv.get("lex", "abbr")
        validate_jzp_text_parseable(rendered, lex=lex, token_sets=token_sets)

    # 基本绑定一致性：每个 staff2 eid 在 staff1 里至少出现一次
    for eid in staff2_events.keys():
        if eid not in staff1_links:
            raise ValueError(f"staff2 有 eid 但 staff1 缺少绑定：{eid}")


def main() -> None:
    token_sets = load_token_sets()

    examples = sorted(EXAMPLES_DIR.glob("*.musicxml"))
    if not examples:
        raise FileNotFoundError(str(EXAMPLES_DIR))

    for p in examples:
        validate_example(p, token_sets)
        print(f"[OK] {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
