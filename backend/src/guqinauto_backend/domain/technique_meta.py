"""
GuqinJZP 技法元数据（TechniqueMeta）。

定位：
- 把“某些减字谱 token 天然要求多个同时音/多个弦位数字”的语义约束写成可执行规则。
- 该规则是 Profile 校验、编辑器 UI 结构、以及 chord-aware stage1/stage2 的共同依赖。

设计原则（学术级）：
- 约束必须严格执行：违反即失败，不做静默降级或“尽量凑一个”。
- 运行期禁止依赖“参考目录”：我们只读取本仓库内 `docs/data/` 的规范文件。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..utils.paths import find_repo_root


@dataclass(frozen=True)
class SimpleXianFingerRule:
    xian_count_allowed: tuple[int, ...]
    slot_schema_by_xian_count: dict[int, tuple[str | None, ...]]


@dataclass(frozen=True)
class ComplexFingerRule:
    valence: int
    slot_schema: tuple[str, ...]


@dataclass(frozen=True)
class TechniqueMeta:
    simple_default: SimpleXianFingerRule
    simple_overrides: dict[str, SimpleXianFingerRule]
    complex_fingers: dict[str, ComplexFingerRule]

    def allowed_xian_counts_for_simple(self, xian_finger: str) -> tuple[int, ...]:
        rule = self.simple_overrides.get(xian_finger) or self.simple_default
        return rule.xian_count_allowed

    def slot_schema_for_simple(self, xian_finger: str, xian_count: int) -> tuple[str | None, ...] | None:
        rule = self.simple_overrides.get(xian_finger) or self.simple_default
        return rule.slot_schema_by_xian_count.get(int(xian_count))

    def complex_rule(self, complex_finger: str) -> ComplexFingerRule | None:
        return self.complex_fingers.get(complex_finger)


def _as_int_tuple(xs: Any, *, where: str) -> tuple[int, ...]:
    if not isinstance(xs, list) or not xs:
        raise ValueError(f"TechniqueMeta: {where} 必须是非空 list[int]")
    out: list[int] = []
    for x in xs:
        if not isinstance(x, int):
            raise ValueError(f"TechniqueMeta: {where} 含非 int：{x!r}")
        out.append(int(x))
    return tuple(out)


def _as_slot_schema_map(m: Any, *, where: str) -> dict[int, tuple[str | None, ...]]:
    if not isinstance(m, dict):
        raise ValueError(f"TechniqueMeta: {where} 必须是 dict")
    out: dict[int, tuple[str | None, ...]] = {}
    for k, v in m.items():
        try:
            n = int(k)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"TechniqueMeta: {where} 的 key 必须可转成 int：{k!r}") from e
        if not isinstance(v, list) or not v:
            raise ValueError(f"TechniqueMeta: {where}[{k!r}] 必须是非空 list[slot]")
        slots: list[str | None] = []
        for s in v:
            if s is None:
                slots.append(None)
                continue
            if not isinstance(s, str) or not s:
                raise ValueError(f"TechniqueMeta: {where}[{k!r}] 含非法 slot：{s!r}")
            slots.append(s)
        out[n] = tuple(slots)
    return out


def _load_technique_meta(path: Path) -> TechniqueMeta:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("TechniqueMeta: 顶层必须是 dict")
    rules = raw.get("rules")
    if not isinstance(rules, dict):
        raise ValueError("TechniqueMeta: 缺少 rules dict")

    # simple
    simple = rules.get("simple")
    if not isinstance(simple, dict):
        raise ValueError("TechniqueMeta: 缺少 rules.simple dict")
    xf = simple.get("xian_finger")
    if not isinstance(xf, dict):
        raise ValueError("TechniqueMeta: 缺少 rules.simple.xian_finger dict")
    default = xf.get("default")
    if not isinstance(default, dict):
        raise ValueError("TechniqueMeta: 缺少 rules.simple.xian_finger.default dict")
    default_allowed = _as_int_tuple(default.get("xian_count_allowed"), where="rules.simple.xian_finger.default.xian_count_allowed")
    default_schema = _as_slot_schema_map(
        default.get("slot_schema_by_xian_count"), where="rules.simple.xian_finger.default.slot_schema_by_xian_count"
    )
    simple_default = SimpleXianFingerRule(xian_count_allowed=default_allowed, slot_schema_by_xian_count=default_schema)

    overrides_raw = xf.get("overrides") or {}
    if not isinstance(overrides_raw, dict):
        raise ValueError("TechniqueMeta: rules.simple.xian_finger.overrides 必须是 dict")
    overrides: dict[str, SimpleXianFingerRule] = {}
    for token, rule in overrides_raw.items():
        if not isinstance(token, str) or not token:
            raise ValueError(f"TechniqueMeta: overrides token 非法：{token!r}")
        if not isinstance(rule, dict):
            raise ValueError(f"TechniqueMeta: overrides[{token!r}] 必须是 dict")
        allowed = _as_int_tuple(rule.get("xian_count_allowed"), where=f"rules.simple.xian_finger.overrides.{token}.xian_count_allowed")
        overrides[token] = SimpleXianFingerRule(xian_count_allowed=allowed, slot_schema_by_xian_count=default_schema)

    # complex
    complex_ = rules.get("complex")
    if not isinstance(complex_, dict):
        raise ValueError("TechniqueMeta: 缺少 rules.complex dict")
    cf = complex_.get("complex_finger")
    if not isinstance(cf, dict):
        raise ValueError("TechniqueMeta: 缺少 rules.complex.complex_finger dict")
    complex_fingers: dict[str, ComplexFingerRule] = {}
    for token, rule in cf.items():
        if not isinstance(token, str) or not token:
            raise ValueError(f"TechniqueMeta: complex_finger token 非法：{token!r}")
        if not isinstance(rule, dict):
            raise ValueError(f"TechniqueMeta: complex_finger[{token!r}] 必须是 dict")
        valence = rule.get("valence")
        if not isinstance(valence, int) or valence <= 0:
            raise ValueError(f"TechniqueMeta: complex_finger[{token!r}].valence 必须为正整数")
        slots = rule.get("slot_schema")
        if not isinstance(slots, list) or not slots or any((not isinstance(s, str) or not s) for s in slots):
            raise ValueError(f"TechniqueMeta: complex_finger[{token!r}].slot_schema 必须为非空 list[str]")
        complex_fingers[token] = ComplexFingerRule(valence=int(valence), slot_schema=tuple(str(s) for s in slots))

    return TechniqueMeta(simple_default=simple_default, simple_overrides=overrides, complex_fingers=complex_fingers)


@lru_cache(maxsize=1)
def load_technique_meta_from_repo() -> TechniqueMeta:
    repo_root = find_repo_root()
    path = repo_root / "docs" / "data" / "GuqinJZP-TechniqueMeta v0.1.yaml"
    if not path.exists():
        raise FileNotFoundError(f"缺少 TechniqueMeta 文件：{path}")
    return _load_technique_meta(path)
