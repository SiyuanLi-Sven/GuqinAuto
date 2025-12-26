"""
减字谱读法（jianzipu text）解析与 token 集合加载。

定位：
- 为配合 `docs/data/GuqinJZP-MusicXML Profile v0.2.md` 的 v0.2 规则，提供：
  1) token 集合（从本仓库 `docs/data/GuqinJZP-JianzipuTokens v0.1.yaml` 加载）
  2) 最小解析器：对生成出的 `jzp_text` 做“语法可接受性”校验

约束：
- 明令禁止运行期依赖 `references` 目录；因此 token 与语法实现必须在本仓库内自洽。
- 解析器是“语法验证器”，不承担字形渲染（kage/ids）职责。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml


Lex = Literal["abbr", "ortho"]


@dataclass(frozen=True)
class JianzipuTokenSets:
    """减字谱读法解析所需 token 集合。"""

    hui_finger: frozenset[str]
    xian_finger: frozenset[str]
    move_finger: frozenset[str]
    special_finger: frozenset[str]
    modifier: frozenset[str]
    both_finger: frozenset[str]
    complex_finger: frozenset[str]
    marker: frozenset[str]

    @classmethod
    def load_from_repo(cls, repo_root: Path) -> "JianzipuTokenSets":
        """从仓库内置 YAML 加载 token 集合。"""

        p = repo_root / "docs" / "data" / "GuqinJZP-JianzipuTokens v0.1.yaml"
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        t = d["tokens"]
        return cls(
            hui_finger=frozenset(t["hui_finger"]),
            xian_finger=frozenset(t["xian_finger"]),
            move_finger=frozenset(t["move_finger"]),
            special_finger=frozenset(t["special_finger"]),
            modifier=frozenset(t["modifier"]),
            both_finger=frozenset(t["both_finger"]),
            complex_finger=frozenset(t["complex_finger"]),
            marker=frozenset(t["marker"]),
        )


ABBR_NUM = ["十一", "十二", "十三", "十", "一", "二", "三", "四", "五", "六", "七", "八", "九", "外", "半"]
ORTHO_HUI = [
    "十一徽",
    "十二徽",
    "十三徽",
    "十徽",
    "一徽",
    "二徽",
    "三徽",
    "四徽",
    "五徽",
    "六徽",
    "七徽",
    "八徽",
    "九徽",
    "徽外",
]
ORTHO_FEN = ["一分", "二分", "三分", "四分", "五分", "六分", "七分", "八分", "九分", "半"]
ORTHO_XIAN = ["一弦", "二弦", "三弦", "四弦", "五弦", "六弦", "七弦"]


@dataclass(frozen=True)
class ParsedPuzi:
    """解析结果（只用于验证与调试）。"""

    kind: Literal["simple", "complex", "aside", "marker", "both"]
    tokens: tuple[str, ...]


def _longest_match_tokenize(s: str, candidates: list[str]) -> list[str]:
    """按最长优先的贪心匹配进行分词。"""

    s = s.strip()
    if s == "":
        raise ValueError("空字符串不可解析为谱字")

    out: list[str] = []
    i = 0
    while i < len(s):
        matched = None
        for tok in candidates:
            if s.startswith(tok, i):
                matched = tok
                break
        if matched is None:
            raise ValueError(f"无法分词：pos={i} 附近={s[i:i+8]!r} 原串={s!r}")
        out.append(matched)
        i += len(matched)
    return out


def _build_candidates(token_sets: JianzipuTokenSets, lex: Lex) -> list[str]:
    """构造用于最长匹配的 token 列表（必须按长度降序）。"""

    base: set[str] = set()
    base |= set(token_sets.hui_finger)
    base |= set(token_sets.xian_finger)
    base |= set(token_sets.move_finger)
    base |= set(token_sets.special_finger)
    base |= set(token_sets.modifier)
    base |= set(token_sets.both_finger)
    base |= set(token_sets.complex_finger)
    base |= set(token_sets.marker)

    if lex == "abbr":
        base |= set(ABBR_NUM)
    else:
        base |= set(ORTHO_HUI) | set(ORTHO_FEN) | set(ORTHO_XIAN)

    return sorted(base, key=len, reverse=True)


def parse_puzi_text(s: str, *, lex: Lex, token_sets: JianzipuTokenSets) -> ParsedPuzi:
    """解析单个谱字读法（abbr/ortho），主要用于“可接受性校验”。

    语法与优先级（与常见实现一致）：
    - complex_form | marker | both_finger | aside_form | simple_form
    """

    candidates = _build_candidates(token_sets, lex)
    tokens = _longest_match_tokenize(s, candidates)

    def try_marker() -> ParsedPuzi | None:
        if len(tokens) == 1 and tokens[0] in token_sets.marker:
            return ParsedPuzi(kind="marker", tokens=tuple(tokens))
        return None

    def try_both() -> ParsedPuzi | None:
        if len(tokens) == 1 and tokens[0] in token_sets.both_finger:
            return ParsedPuzi(kind="both", tokens=tuple(tokens))
        return None

    def parse_hui_number_seq(start: int) -> int:
        if lex == "abbr":
            # 0..2 个数字 token，或 '外'
            if start >= len(tokens):
                return start
            if tokens[start] == "外":
                return start + 1
            i = start
            for _ in range(2):
                if i < len(tokens) and tokens[i] in ABBR_NUM and tokens[i] not in ("外",):
                    i += 1
                else:
                    break
            return i
        # ortho：0..1 个 HUI + 0..1 个 FEN，或 '徽外'
        if start >= len(tokens):
            return start
        if tokens[start] == "徽外":
            return start + 1
        i = start
        if i < len(tokens) and tokens[i] in ORTHO_HUI:
            i += 1
            if i < len(tokens) and tokens[i] in ORTHO_FEN:
                i += 1
        return i

    def parse_xian_number_seq(start: int) -> int:
        if lex == "abbr":
            # 1..2 个弦数字
            i = start
            for _ in range(2):
                if i < len(tokens) and tokens[i] in ABBR_NUM and tokens[i] not in ("外", "半"):
                    i += 1
                else:
                    break
            if i == start:
                raise ValueError("缺少弦序数字")
            return i
        # ortho：1..2 个 'n弦'
        i = start
        for _ in range(2):
            if i < len(tokens) and tokens[i] in ORTHO_XIAN:
                i += 1
            else:
                break
        if i == start:
            raise ValueError("缺少弦序 token（如 三弦）")
        return i

    def try_aside() -> ParsedPuzi | None:
        # aside_form = modifier? + special? + move_finger + hui_number_seq
        i = 0
        if i < len(tokens) and tokens[i] in token_sets.modifier:
            i += 1
        if i < len(tokens) and tokens[i] in token_sets.special_finger:
            i += 1
        if i >= len(tokens) or tokens[i] not in token_sets.move_finger:
            return None
        i += 1
        i = parse_hui_number_seq(i)
        if i != len(tokens):
            return None
        return ParsedPuzi(kind="aside", tokens=tuple(tokens))

    def try_simple() -> ParsedPuzi | None:
        # simple_form = (hui_finger + hui_number_seq)? + special? + xian_finger + xian_number_seq
        i = 0
        # 可选的 hui_finger_phrase
        if i < len(tokens) and tokens[i] in token_sets.hui_finger:
            i += 1
            i = parse_hui_number_seq(i)
        # 可选 special
        if i < len(tokens) and tokens[i] in token_sets.special_finger:
            i += 1
        # 必须 xian_finger_phrase
        if i >= len(tokens) or tokens[i] not in token_sets.xian_finger:
            return None
        i += 1
        i = parse_xian_number_seq(i)
        if i != len(tokens):
            return None
        return ParsedPuzi(kind="simple", tokens=tuple(tokens))

    def try_complex() -> ParsedPuzi | None:
        # complex_form = complex_finger + sub + sub
        # sub = (hui_finger + hui_number_seq) + special? + (xian_number)
        if len(tokens) < 3 or tokens[0] not in token_sets.complex_finger:
            return None

        def parse_sub(start: int) -> int:
            i = start
            if i >= len(tokens) or tokens[i] not in token_sets.hui_finger:
                raise ValueError("complex 子式缺少 hui_finger")
            i += 1
            # complex 子式的“徽位数字短语”必须给末尾的弦序 token 留位置；
            # 否则像 “散四” 会被贪心吞成 “散 + 徽位四” 而缺失弦序。
            def parse_hui_number_seq_complex(start2: int) -> int:
                if start2 >= len(tokens):
                    return start2

                # 至少要给弦序留 1 个 token
                last_allowed = len(tokens) - 1
                if start2 > last_allowed:
                    return start2

                if lex == "abbr":
                    # 候选消费长度：0/1/2 或 OUT(外)
                    candidates: list[int] = [start2]
                    if tokens[start2] == "外" and start2 + 1 <= last_allowed:
                        candidates.append(start2 + 1)
                    for n in (1, 2):
                        end = start2 + n
                        if end <= last_allowed and all(
                            (start2 + k) < len(tokens)
                            and tokens[start2 + k] in ABBR_NUM
                            and tokens[start2 + k] not in ("外",)
                            for k in range(n)
                        ):
                            candidates.append(end)
                    # 选择“最长且可行”的（保持与常见读法习惯一致）
                    return max(candidates)

                # ortho：0..1 个 HUI + 0..1 个 FEN，或 '徽外'
                candidates = [start2]
                if tokens[start2] == "徽外" and start2 + 1 <= last_allowed:
                    candidates.append(start2 + 1)
                if tokens[start2] in ORTHO_HUI and start2 + 1 <= last_allowed:
                    candidates.append(start2 + 1)
                    if (
                        start2 + 2 <= last_allowed
                        and start2 + 1 < len(tokens)
                        and tokens[start2 + 1] in ORTHO_FEN
                    ):
                        candidates.append(start2 + 2)
                return max(candidates)

            i = parse_hui_number_seq_complex(i)
            if i < len(tokens) and tokens[i] in token_sets.special_finger:
                i += 1
            # reduced_xian_phrase：只允许 1 个弦序
            if lex == "abbr":
                if i >= len(tokens) or tokens[i] not in ABBR_NUM or tokens[i] in ("外", "半"):
                    raise ValueError("complex 子式缺少弦序数字")
                i += 1
            else:
                if i >= len(tokens) or tokens[i] not in ORTHO_XIAN:
                    raise ValueError("complex 子式缺少弦序 token（如 三弦）")
                i += 1
            return i

        i = 1
        try:
            i = parse_sub(i)
            i = parse_sub(i)
        except ValueError:
            return None
        if i != len(tokens):
            return None
        return ParsedPuzi(kind="complex", tokens=tuple(tokens))

    for fn in (try_complex, try_marker, try_both, try_aside, try_simple):
        r = fn()
        if r is not None:
            return r
    raise ValueError(f"无法按 v0.1 token+语法解析谱字：{s!r} tokens={tokens!r}")
