# 开发规范：禁止依赖 `references/`

`references/` 目录仅用于**给人类/agent 参考**（外部仓库、规范、素材的镜像），不属于 GuqinAuto 的可发布/可运行工程的一部分。

因此：

- 明令禁止在运行期通过任何方式依赖 `references/`（包括但不限于 `sys.path` 注入、读取 `references/` 下的数据文件、前端/后端直接 import、打包时把 `references/` 当资源目录等）。
- 如果需要复用其中的设计/数据/资产，必须在本仓库内**重新实现**，或把需要的内容**复制到本仓库的正式目录**（并在文档里写清楚来源与许可证）。

## 允许的例外

- 文档中为了说明来历/背景，提到外部项目或曾参考的路径（不影响运行期）。

## 推荐做法

- 需要复用 token/枚举：放到 `docs/data/` 或 `src/`（例如 `docs/data/GuqinJZP-JianzipuTokens v0.1.yaml`）
- 需要复用解析/校验：在本仓库内实现（例如 `guqinjzp/`）
- 需要复用第三方代码：在本仓库 `third_party/` 或 `vendor/` 里 vendoring，并补齐 LICENSE/NOTICE

## 快速检查

运行：

`python scripts/check_no_references_usage.py`
