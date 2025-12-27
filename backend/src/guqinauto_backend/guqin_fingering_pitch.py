"""
古琴指法真值 ↔ 音高（pitch）推导模块。

定位：
- 这是 GuqinAuto 的“可复用核心模块”之一：在给定定弦（tuning）下，做两件事：
  1) 从 staff2 的结构化指法真值（GuqinJZP KV）推导“应当发声的 pitch”（用于校验/反向编译/导出）
  2) 为 stage1/stage2 提供明确的“可计算边界”：缺少真值就明确返回不可推导（正确地失败，不猜）

约束与阶段性：
- Profile v0.2：只能对“散音/开弦”做确定推导；按音/泛音等必须提示需要 v0.3 真值。
- Profile v0.3：引入 `sound` + `pos_ratio` +（可选）`harmonic_n/k` 后，推导可覆盖更多事件。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log2
from typing import Any, Literal

from .pitch import MusicXmlPitch
from .workspace import ProjectTuning


Sound = Literal["open", "pressed", "harmonic"]


@dataclass(frozen=True)
class DerivedPitch:
    """指法推导出来的 pitch 信息（供一致性检查与导出链路使用）。"""

    slot: str | None
    expected_midi: int
    expected_midi_float: float | None
    method: str
    cents_deviation_vs_equal_temperament: float | None = None


def derive_expected_pitches(
    staff2_kv: dict[str, str],
    *,
    tuning: ProjectTuning,
) -> tuple[list[DerivedPitch], list[str]]:
    """从 GuqinJZP KV 推导该事件应当发声的 pitch（可能是 chord 多音）。

    返回：
    - derived：可推导出的期望音高列表（按 slot 标注）
    - notes：推导过程中的“不可推导原因/注意事项”（供 UI 做 warning）

    设计原则：
    - 能推导就推导（确定性）
    - 不能推导就明确返回 notes（不猜）
    """

    form = staff2_kv.get("form")
    if form not in ("simple", "complex"):
        return ([], ["uncheckable_form_requires_v0_3_truth"])

    # 优先：v0.3 明确字段
    if _has_any_v0_3_sound_fields(staff2_kv):
        return _derive_v0_3(staff2_kv, tuning=tuning)

    # 兼容：v0.2 只对“散音/开弦”做确定推导
    return _derive_v0_2_open_only(staff2_kv, tuning=tuning)


def _has_any_v0_3_sound_fields(kv: dict[str, str]) -> bool:
    keys = set(kv.keys())
    for k in (
        "sound",
        "pos_ratio",
        "harmonic_n",
        "harmonic_k",
        "pos_ratio_1",
        "pos_ratio_2",
        "l_sound",
        "l_pos_ratio",
        "l_harmonic_n",
        "l_harmonic_k",
        "r_sound",
        "r_pos_ratio",
        "r_harmonic_n",
        "r_harmonic_k",
    ):
        if k in keys:
            return True
    return False


def _open_pitch_midi(string_1_to_7: int, *, tuning: ProjectTuning) -> int:
    if not (1 <= string_1_to_7 <= 7):
        raise ValueError(f"非法弦序：{string_1_to_7}")
    base = int(tuning.open_pitches_midi[string_1_to_7 - 1])
    return base + int(tuning.transpose_semitones)


def _pos_ratio_to_d_semitones_float(pos_ratio: float) -> float:
    # 12-TET 下的弦长比例：freq_ratio = 1/(1-pos_ratio)
    # semitones = 12 * log2(freq_ratio) = -12 * log2(1-pos_ratio)
    if not (0.0 <= pos_ratio < 1.0):
        raise ValueError(f"pos_ratio 超界（期望 0<=x<1）：{pos_ratio}")
    if pos_ratio == 0.0:
        return 0.0
    return -12.0 * log2(1.0 - pos_ratio)


def _parse_float(s: str, *, name: str) -> float:
    try:
        return float(s)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"{name} 不是合法浮点数：{s!r}") from e


def _parse_int(s: str, *, name: str) -> int:
    try:
        return int(s)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"{name} 不是合法整数：{s!r}") from e


def _derive_one_open(*, slot: str | None, string_1_to_7: int, tuning: ProjectTuning) -> DerivedPitch:
    midi = _open_pitch_midi(string_1_to_7, tuning=tuning)
    return DerivedPitch(slot=slot, expected_midi=midi, expected_midi_float=float(midi), method="open_string")


def _derive_one_pressed(
    *,
    slot: str | None,
    string_1_to_7: int,
    pos_ratio: float,
    tuning: ProjectTuning,
) -> DerivedPitch:
    open_midi = _open_pitch_midi(string_1_to_7, tuning=tuning)
    d = _pos_ratio_to_d_semitones_float(pos_ratio)
    midi_f = float(open_midi) + d
    midi_i = int(round(midi_f))
    return DerivedPitch(slot=slot, expected_midi=midi_i, expected_midi_float=midi_f, method="pressed_pos_ratio_12tet")


def _derive_one_harmonic(
    *,
    slot: str | None,
    string_1_to_7: int,
    harmonic_n: int,
    tuning: ProjectTuning,
) -> DerivedPitch:
    # 自然泛音：理论频率比约为 n（相对开弦）。转成等音 12-TET 的 semitone 值是 12*log2(n)（通常非整数）。
    open_midi = _open_pitch_midi(string_1_to_7, tuning=tuning)
    midi_f = float(open_midi) + 12.0 * log2(float(harmonic_n))
    midi_i = int(round(midi_f))
    cents_dev = (float(midi_i) - midi_f) * 100.0
    return DerivedPitch(
        slot=slot,
        expected_midi=midi_i,
        expected_midi_float=midi_f,
        method="natural_harmonic_n",
        cents_deviation_vs_equal_temperament=float(cents_dev),
    )


def _derive_v0_3(kv: dict[str, str], *, tuning: ProjectTuning) -> tuple[list[DerivedPitch], list[str]]:
    form = kv.get("form")
    notes: list[str] = []

    if form == "simple":
        xian = kv.get("xian")
        if not xian:
            return ([], ["missing_xian"])
        xian_list = [int(s) for s in xian.split(",") if s != ""]
        if not xian_list:
            return ([], ["missing_xian"])

        sound: Sound | None = kv.get("sound")  # type: ignore[assignment]
        if sound not in ("open", "pressed", "harmonic"):
            return ([], ["missing_or_invalid_sound"])

        if len(xian_list) == 1:
            s = xian_list[0]
            if sound == "open":
                return ([ _derive_one_open(slot=None, string_1_to_7=s, tuning=tuning) ], [])
            if sound == "pressed":
                pr_s = kv.get("pos_ratio")
                if pr_s is None:
                    return ([], ["missing_pos_ratio_for_pressed"])
                pr = _parse_float(pr_s, name="pos_ratio")
                return ([ _derive_one_pressed(slot=None, string_1_to_7=s, pos_ratio=pr, tuning=tuning) ], [])
            # harmonic
            hn = kv.get("harmonic_n")
            if hn is None:
                return ([], ["missing_harmonic_n_for_harmonic"])
            return ([ _derive_one_harmonic(slot=None, string_1_to_7=s, harmonic_n=_parse_int(hn, name="harmonic_n"), tuning=tuning) ], [])

        if len(xian_list) == 2:
            s1, s2 = xian_list
            if sound == "open":
                return (
                    [
                        _derive_one_open(slot="1", string_1_to_7=s1, tuning=tuning),
                        _derive_one_open(slot="2", string_1_to_7=s2, tuning=tuning),
                    ],
                    [],
                )

            if sound == "pressed":
                pr1_s = kv.get("pos_ratio_1")
                pr2_s = kv.get("pos_ratio_2")
                if pr1_s is None or pr2_s is None:
                    return ([], ["missing_pos_ratio_1_or_2_for_pressed_multistring"])
                return (
                    [
                        _derive_one_pressed(slot="1", string_1_to_7=s1, pos_ratio=_parse_float(pr1_s, name="pos_ratio_1"), tuning=tuning),
                        _derive_one_pressed(slot="2", string_1_to_7=s2, pos_ratio=_parse_float(pr2_s, name="pos_ratio_2"), tuning=tuning),
                    ],
                    [],
                )

            # harmonic
            hn = kv.get("harmonic_n")
            if hn is None:
                return ([], ["missing_harmonic_n_for_harmonic"])
            harmonic_n = _parse_int(hn, name="harmonic_n")
            return (
                [
                    _derive_one_harmonic(slot="1", string_1_to_7=s1, harmonic_n=harmonic_n, tuning=tuning),
                    _derive_one_harmonic(slot="2", string_1_to_7=s2, harmonic_n=harmonic_n, tuning=tuning),
                ],
                ["harmonic_multistring_assumes_same_n"],
            )

        return ([], [f"unsupported_xian_list_length:{len(xian_list)}"])

    if form == "complex":
        l_xian = kv.get("l_xian")
        r_xian = kv.get("r_xian")
        if l_xian is None or r_xian is None:
            return ([], ["missing_l_xian_or_r_xian"])
        l_s = _parse_int(l_xian, name="l_xian")
        r_s = _parse_int(r_xian, name="r_xian")

        l_sound: Sound | None = kv.get("l_sound")  # type: ignore[assignment]
        r_sound: Sound | None = kv.get("r_sound")  # type: ignore[assignment]
        if l_sound not in ("open", "pressed", "harmonic") or r_sound not in ("open", "pressed", "harmonic"):
            return ([], ["missing_or_invalid_l_sound_or_r_sound"])

        derived: list[DerivedPitch] = []

        if l_sound == "open":
            derived.append(_derive_one_open(slot="L", string_1_to_7=l_s, tuning=tuning))
        elif l_sound == "pressed":
            pr = kv.get("l_pos_ratio")
            if pr is None:
                return ([], ["missing_l_pos_ratio_for_pressed"])
            derived.append(_derive_one_pressed(slot="L", string_1_to_7=l_s, pos_ratio=_parse_float(pr, name="l_pos_ratio"), tuning=tuning))
        else:
            hn = kv.get("l_harmonic_n")
            if hn is None:
                return ([], ["missing_l_harmonic_n_for_harmonic"])
            derived.append(_derive_one_harmonic(slot="L", string_1_to_7=l_s, harmonic_n=_parse_int(hn, name="l_harmonic_n"), tuning=tuning))

        if r_sound == "open":
            derived.append(_derive_one_open(slot="R", string_1_to_7=r_s, tuning=tuning))
        elif r_sound == "pressed":
            pr = kv.get("r_pos_ratio")
            if pr is None:
                return ([], ["missing_r_pos_ratio_for_pressed"])
            derived.append(_derive_one_pressed(slot="R", string_1_to_7=r_s, pos_ratio=_parse_float(pr, name="r_pos_ratio"), tuning=tuning))
        else:
            hn = kv.get("r_harmonic_n")
            if hn is None:
                return ([], ["missing_r_harmonic_n_for_harmonic"])
            derived.append(_derive_one_harmonic(slot="R", string_1_to_7=r_s, harmonic_n=_parse_int(hn, name="r_harmonic_n"), tuning=tuning))

        return (derived, notes)

    return ([], ["uncheckable_form_requires_v0_3_truth"])


def _derive_v0_2_open_only(kv: dict[str, str], *, tuning: ProjectTuning) -> tuple[list[DerivedPitch], list[str]]:
    form = kv.get("form")
    if form not in ("simple", "complex"):
        return ([], ["uncheckable_form"])

    def is_open(hui_finger: str | None, hui: str | None, fen: str | None) -> bool:
        if hui is not None or fen is not None:
            return False
        if hui_finger is None:
            return False
        return hui_finger in ("散音", "散")

    if form == "simple":
        xian = kv.get("xian")
        if not xian:
            return ([], ["missing_xian"])
        xian_list = [int(s) for s in xian.split(",") if s != ""]
        if not xian_list:
            return ([], ["missing_xian"])
        if not is_open(kv.get("hui_finger"), kv.get("hui"), kv.get("fen")):
            return ([], ["uncheckable_v0_2_requires_v0_3_truth"])
        if len(xian_list) == 1:
            return ([_derive_one_open(slot=None, string_1_to_7=xian_list[0], tuning=tuning)], [])
        if len(xian_list) == 2:
            return (
                [
                    _derive_one_open(slot="1", string_1_to_7=xian_list[0], tuning=tuning),
                    _derive_one_open(slot="2", string_1_to_7=xian_list[1], tuning=tuning),
                ],
                [],
            )
        return ([], ["unsupported_xian_list_length"])

    # complex
    l_xian = kv.get("l_xian")
    r_xian = kv.get("r_xian")
    if l_xian is None or r_xian is None:
        return ([], ["missing_l_xian_or_r_xian"])
    if not is_open(kv.get("l_hui_finger"), kv.get("l_hui"), kv.get("l_fen")):
        return ([], ["uncheckable_v0_2_requires_v0_3_truth"])
    if not is_open(kv.get("r_hui_finger"), kv.get("r_hui"), kv.get("r_fen")):
        return ([], ["uncheckable_v0_2_requires_v0_3_truth"])
    return (
        [
            _derive_one_open(slot="L", string_1_to_7=int(l_xian), tuning=tuning),
            _derive_one_open(slot="R", string_1_to_7=int(r_xian), tuning=tuning),
        ],
        [],
    )


def staff1_pitch_dict_to_midi(pitch: dict[str, Any] | None) -> int | None:
    """把 score view 的 staff1 pitch dict 转成 MIDI（用于一致性比较）。"""

    if not isinstance(pitch, dict):
        return None
    step = pitch.get("step")
    octave = pitch.get("octave")
    if not isinstance(step, str) or not isinstance(octave, int):
        return None
    alter = pitch.get("alter")
    alter_i = int(alter) if isinstance(alter, int) else 0
    return MusicXmlPitch(step=step, alter=alter_i, octave=octave).to_midi()

