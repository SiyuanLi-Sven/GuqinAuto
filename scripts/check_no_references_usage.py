"""
检查：项目代码禁止运行期依赖 `references/`。

定位：
- 扫描仓库内的代码文件（py/ts/tsx/js/mjs/cjs/sh 等）；
- 发现以下模式则返回非 0：
  - Python: `import references` / `from references ...` / `sys.path.*references`
  - 任意代码：显式字符串路径 `references/`（在代码文件中出现）

注意：
- 该检查是“保守”的：宁可误报，也不允许悄悄引入 references 依赖。
- 文档（md）不在扫描范围内。

运行：
  python scripts/check_no_references_usage.py
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

CODE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".cjs",
    ".sh",
}

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    ".next",
    ".turbo",
    "references",  # 自己不扫描
    "old",
    "backend/workspaces",
    "backend/data",
    "temp",  # 开发输出区通常被忽略
}

PY_BAD_PATTERNS = [
    "import references",
    "from references",
    "sys.path.append('references",
    'sys.path.append("references',
    "sys.path.insert(0,'references",
    'sys.path.insert(0,"references',
    "sys.path.insert(0, 'references",
    'sys.path.insert(0, "references',
]


def is_skipped_dir(path: Path) -> bool:
    parts = path.parts
    if not parts:
        return False
    for name in SKIP_DIR_NAMES:
        # 支持像 "backend/workspaces" 这样的子路径
        if "/" in name:
            if str(path).find(name) != -1:
                return True
        else:
            if name in parts:
                return True
    return False


def iter_code_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if is_skipped_dir(p):
            continue
        if p.suffix in CODE_SUFFIXES:
            out.append(p)
    return out


def main() -> int:
    offenders: list[tuple[Path, str]] = []
    self_path = Path(__file__).resolve()
    for p in iter_code_files(REPO_ROOT):
        if p.resolve() == self_path:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if "references/" in text or "references\\" in text:
            offenders.append((p, "包含 references/ 路径字面量"))
            continue

        if p.suffix == ".py":
            for pat in PY_BAD_PATTERNS:
                if pat in text:
                    offenders.append((p, f"命中模式：{pat!r}"))
                    break

    if offenders:
        for path, reason in offenders:
            rel = path.relative_to(REPO_ROOT)
            print(f"[FAIL] {rel} - {reason}")
        print(f"\n共发现 {len(offenders)} 处违规；请移除 references 运行期依赖。")
        return 1

    print("[OK] 未发现 references 运行期依赖")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
