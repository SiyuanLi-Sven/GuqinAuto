"""
GuqinAuto 的 KV 串解析（other-technical / words 中使用）。

约定：
- 文本形如：`Prefix@version;key=value;key=value;`
- 用于 MusicXML 的 other-technical / direction words 等槽位。

学术级要求：
- 未识别字段不能静默忽略；解析失败必须抛出明确异常。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KVBlock:
    prefix: str
    version: str
    kv: dict[str, str]


def parse_kv_block(text: str) -> KVBlock:
    text = (text or "").strip()
    parts = [p for p in text.split(";") if p != ""]
    if not parts:
        raise ValueError("空 KV 文本")

    head = parts[0]
    if "@" not in head:
        raise ValueError(f"KV head 缺少版本：{head!r}")
    prefix, version = head.split("@", 1)
    if not prefix or not version:
        raise ValueError(f"KV head 非法：{head!r}")

    kv: dict[str, str] = {}
    for seg in parts[1:]:
        if "=" not in seg:
            raise ValueError(f"KV 段缺少 '='：{seg!r}")
        key, value = seg.split("=", 1)
        if key == "":
            raise ValueError(f"KV key 为空：{seg!r}")
        if value == "":
            raise ValueError(f"KV value 为空（建议省略该 key）：{key!r}")
        if "\n" in value or ";" in value:
            raise ValueError(f"KV value 非法（含换行/分号）：{key}={value!r}")
        if key in kv:
            raise ValueError(f"KV key 重复：{key!r}")
        kv[key] = value

    return KVBlock(prefix=prefix, version=version, kv=kv)


def dump_kv_block(prefix: str, version: str, kv: dict[str, str]) -> str:
    if not prefix or not version:
        raise ValueError("prefix/version 不能为空")
    parts = [f"{prefix}@{version}"]
    for k, v in kv.items():
        if ";" in k or ";" in v or "\n" in v:
            raise ValueError(f"非法 KV：{k}={v!r}")
        parts.append(f"{k}={v}")
    return ";".join(parts) + ";"
