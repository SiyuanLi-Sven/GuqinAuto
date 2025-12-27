"""
GuqinAuto 后端开发服务器启动脚本。

定位：
- 本仓库暂未把后端打包成可安装的 Python package，因此需要在启动时把 `backend/src`
  加到 `PYTHONPATH`。
- 约定后端端口为 7130（与前端 7137 配套）。

用法：
  python backend/run_server.py

可选参数（透传给 uvicorn）：
  python backend/run_server.py --reload
  python backend/run_server.py --host 0.0.0.0 --port 7130
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn


def main() -> None:
    backend_dir = Path(__file__).resolve().parent
    src_dir = backend_dir / "src"
    if not src_dir.exists():
        raise RuntimeError(f"找不到后端源码目录：{src_dir}")

    sys.path.insert(0, str(src_dir))
    repo_root = backend_dir.parent

    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7130)
    parser.add_argument("--reload", action="store_true", default=False)
    parser.add_argument("--log-level", default="info")
    args, unknown = parser.parse_known_args(sys.argv[1:])
    if unknown:
        raise SystemExit(f"不支持的参数：{unknown!r}")

    # --reload 默认会 watch 当前工作目录（通常是 repo root），这会导致前端 node_modules
    # 之类的噪声文件频繁触发重载。这里把 watch 范围显式限定到后端源码目录。
    reload_dirs = [str(src_dir), str(backend_dir)] if args.reload else None
    # 如果用户从 repo 外部启动（极少见），补一个兜底，避免 watchfiles 报错。
    if args.reload and not repo_root.exists():
        reload_dirs = [str(src_dir)]

    uvicorn.run(
        "guqinauto_backend.api.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=reload_dirs,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
