"""
stage1：绝对音高 → 古琴候选音位（散/按/泛）枚举（PositionEngine）。

定位：
- 这是 GuqinAuto 的 stage1 核心：给定目标绝对音高（MIDI）与调弦方案，枚举所有可行音位候选。
- 该模块只做“候选枚举”，不做序列级最优选择（stage2 的职责）。

设计选择（写死）：
- 连续位置真值使用 `pos_ratio`（物理/可优化/可回归）
- `hui_real` 仅作为派生显示/缓存层（可选），不作为底层真值

实现说明：
- pressed/open 的 `pos_ratio` 采用 12-TET 下的弦长比例：freq_ratio = 2^(d/12) = 1/(1-pos_ratio)
  因此 pos_ratio = 1 - 2^(-d/12)。
- `hui_real` 当前提供“等音/纯律”两套 d→hui_real 的离散表，仅用于显示与回归对齐。
  该表来源于公开参考实现的数值结果；它不作为真值，缺失或不一致不影响 `pos_ratio` 的正确性。

约束：
- 必须显式失败，不允许猜测（学术级：正确地失败）。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log2, pow
from typing import Literal


Temperament = Literal["equal", "just"]
Technique = Literal["open", "press", "harmonic"]


# d=0..36 对应的 hui_real（连续徽位坐标），用于显示/对齐。
# 注意：这些值不是底层真值；真值为 pos_ratio。
HUI_REAL_EQUAL: tuple[float, ...] = (
    0.0,
    13.6,
    13.1,
    12.2,
    10.9,
    10.0,
    9.5,
    9.0,
    8.4,
    7.9,
    7.6,
    7.3,
    7.0,
    6.7,
    6.5,
    6.2,
    6.0,
    5.6,
    5.3,
    5.0,
    4.8,
    4.6,
    4.4,
    4.2,
    4.0,
    3.7,
    3.5,
    3.2,
    3.0,
    2.6,
    2.3,
    2.0,
    1.8,
    1.6,
    1.4,
    1.2,
    1.0,
)

HUI_REAL_JUST: tuple[float, ...] = (
    0.0,
    13.6,
    13.1,
    12.2,
    11.0,
    10.0,
    9.5,
    9.0,
    8.5,
    8.0,
    7.7,
    7.3,
    7.0,
    6.7,
    6.4,
    6.2,
    6.0,
    5.6,
    5.3,
    5.0,
    4.8,
    4.6,
    4.4,
    4.2,
    4.0,
    3.7,
    3.4,
    3.2,
    3.0,
    2.6,
    2.3,
    2.0,
    1.8,
    1.6,
    1.4,
    1.2,
    1.0,
)


def pos_ratio_for_semitones(d_semitones: int) -> float:
    """按音/按弦的连续位置真值（pos_ratio）。"""

    if d_semitones < 0:
        raise ValueError("d_semitones 不能为负")
    if d_semitones == 0:
        return 0.0
    # pos_ratio = 1 - 2^(-d/12)
    return 1.0 - float(pow(2.0, -float(d_semitones) / 12.0))


def hui_real_for_semitones(d_semitones: int, *, temperament: Temperament) -> float | None:
    """派生显示：d→hui_real（连续徽位坐标）。"""

    if d_semitones <= 0:
        return None
    table = HUI_REAL_EQUAL if temperament == "equal" else HUI_REAL_JUST
    if d_semitones >= len(table):
        return None
    return float(table[d_semitones])


def hui_real_from_pos_ratio(pos_ratio: float, *, temperament: Temperament) -> float | None:
    """派生显示：pos_ratio → hui_real（线性插值，近似）。"""

    if not (0.0 < pos_ratio < 1.0):
        return None

    # 用 pressed 的 d→(pos_ratio, hui_real) 点集做插值（单调、可复现）。
    table = HUI_REAL_EQUAL if temperament == "equal" else HUI_REAL_JUST
    pts: list[tuple[float, float]] = []
    for d in range(1, min(len(table), 37)):
        pr = pos_ratio_for_semitones(d)
        hr = float(table[d])
        pts.append((pr, hr))
    pts.sort(key=lambda x: x[0])

    if pos_ratio <= pts[0][0]:
        return pts[0][1]
    if pos_ratio >= pts[-1][0]:
        return pts[-1][1]

    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= pos_ratio <= x1:
            t = (pos_ratio - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return None


@dataclass(frozen=True)
class PositionCandidate:
    string: int  # 1..7
    technique: Technique
    pitch_midi: int
    d_semitones_from_open: int
    pos_ratio: float | None
    hui_real: float | None
    temperament: Temperament
    # harmonic 专用字段（open/press 为 None）
    harmonic_n: int | None = None
    harmonic_k: int | None = None
    cents_error: float | None = None


@dataclass(frozen=True)
class PositionEngineOptions:
    temperament: Temperament = "equal"
    max_d_semitones: int = 36
    include_harmonics: bool = False
    max_harmonic_n: int = 12
    max_harmonic_cents_error: float = 25.0


class PositionEngine:
    """根据目标音高与调弦，枚举古琴候选音位。"""

    def __init__(self, *, open_pitches_midi: list[int], transpose_semitones: int = 0):
        if len(open_pitches_midi) != 7:
            raise ValueError("open_pitches_midi 必须长度为 7（对应弦序 1..7）")
        self._open = [int(x) for x in open_pitches_midi]
        self._transpose = int(transpose_semitones)

    def enumerate_candidates(self, *, pitch_midi: int, options: PositionEngineOptions) -> list[PositionCandidate]:
        pitch_midi = int(pitch_midi) + self._transpose
        out: list[PositionCandidate] = []

        for s in range(1, 8):
            open_midi = self._open[s - 1]
            d = int(pitch_midi - open_midi)
            if d < 0 or d > int(options.max_d_semitones):
                continue

            if d == 0:
                out.append(
                    PositionCandidate(
                        string=s,
                        technique="open",
                        pitch_midi=pitch_midi,
                        d_semitones_from_open=0,
                        pos_ratio=None,
                        hui_real=None,
                        temperament=options.temperament,
                        cents_error=0.0,
                    )
                )
                continue

            pr = pos_ratio_for_semitones(d)
            hr = hui_real_for_semitones(d, temperament=options.temperament)
            out.append(
                PositionCandidate(
                    string=s,
                    technique="press",
                    pitch_midi=pitch_midi,
                    d_semitones_from_open=d,
                    pos_ratio=pr,
                    hui_real=hr,
                    temperament=options.temperament,
                    cents_error=0.0,
                )
            )

        if options.include_harmonics:
            # 仅提供“自然泛音近似候选”：匹配 harmonic number n（2..N）并输出其节点位置 k/n（gcd(k,n)=1）。
            # 这不会宣称“覆盖全部泛音/流派记谱差异”，仅作为 stage1 候选图的一部分输入。
            import math

            for s in range(1, 8):
                open_midi = self._open[s - 1]
                interval = float(pitch_midi - open_midi)
                if interval <= 0:
                    continue

                for n in range(2, int(options.max_harmonic_n) + 1):
                    expected = 12.0 * log2(float(n))
                    cents_error = (interval - expected) * 100.0
                    if abs(cents_error) > float(options.max_harmonic_cents_error):
                        continue

                    for k in range(1, n):
                        if math.gcd(k, n) != 1:
                            continue
                        pr = float(k) / float(n)
                        hr = hui_real_from_pos_ratio(pr, temperament=options.temperament)
                        out.append(
                            PositionCandidate(
                                string=s,
                                technique="harmonic",
                                pitch_midi=pitch_midi,
                                d_semitones_from_open=int(interval),
                                pos_ratio=pr,
                                hui_real=hr,
                                temperament=options.temperament,
                                harmonic_n=n,
                                harmonic_k=k,
                                cents_error=float(cents_error),
                            )
                        )

        return out
