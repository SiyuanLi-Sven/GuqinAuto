"""
路径与仓库定位工具。

定位：
- 后端运行时需要定位仓库根目录（用于读取 docs/data 内的规范/示例）。
- 同时需要定位 workspace 根目录（backend/workspace）。

约束：
- 禁止运行期依赖 references 目录；这里的“定位仓库”仅用于读取本仓库自身文件。
"""

from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """向上搜索仓库根目录（基于目录特征）。"""

    cur = (start or Path(__file__)).resolve()
    if cur.is_file():
        cur = cur.parent

    for _ in range(20):
        if (cur / "frontend").exists() and (cur / "backend").exists() and (cur / "docs").exists():
            return cur
        cur = cur.parent
    raise RuntimeError("无法定位仓库根目录（未找到 frontend/backend/docs 三个目录）")


def backend_dir() -> Path:
    return find_repo_root() / "backend"


def workspace_root() -> Path:
    return backend_dir() / "workspace"


def docs_data_dir() -> Path:
    return find_repo_root() / "docs" / "data"


def examples_dir() -> Path:
    return docs_data_dir() / "examples"
