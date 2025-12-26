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

    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7130)
    parser.add_argument("--reload", action="store_true", default=False)
    parser.add_argument("--log-level", default="info")
    args, unknown = parser.parse_known_args(sys.argv[1:])
    if unknown:
        raise SystemExit(f"不支持的参数：{unknown!r}")

    uvicorn.run(
        "guqinauto_backend.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
