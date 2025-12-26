```bash
cd frontend && npm install && npm run dev
```

# GuqinAuto

GuqinAuto 是一个面向“古琴谱（减字谱）+简谱”编辑与数据治理的系统。核心目标是把古琴谱的**可编辑真值**落在一份 MusicXML 里（Single Source of Truth），并在前端提供“每行上简谱、下减字谱”的综合编辑视图；后续可从同一真源派生导出 MusicXML/MIDI 等格式。

## 核心定位

- **真源**：单个 MusicXML 文件（score-partwise 4.1），其中包含双 staff：staff1=简谱层（节奏锚点）、staff2=减字谱层（动作/指法锚点）。
- **交互**：综合双谱视图不可拆分（每行 system 上简谱下减字谱），导出入口在编辑器内部（不暴露 `/export` 页面）。
- **学术级要求**：倾向“正确地失败”，不做降级安慰剂；校验不通过必须明确报错。

## 目录结构

- `frontend/`：Next.js 前端（编辑器 UI）
- `backend/`：后端（领域逻辑、校验、读写 MusicXML 等；当前主要放置 GuqinJZP 相关逻辑）
- `docs/`：文档与规范
- `temp/`：测试与一次性工具（开发期脚本、输出等）

## 关键文档入口

- GuqinJZP MusicXML Profile：`docs/data/GuqinJZP-MusicXML Profile v0.2.md`
- 减字谱读法 token 规范（内置，不依赖外部目录）：`docs/data/GuqinJZP-JianzipuTokens v0.1.yaml`
- v0.2 示例：`docs/data/examples/`
- 前端架构说明：`docs/前端-架构.md`

## 开发运行（快速参考）

### 前端

```bash
cd frontend
npm install
npm run dev
```

- 前端服务：`http://localhost:7137`
- 后端服务（预留）：`http://localhost:7130`
- 前端代理（开发期）：`/api/backend/*` → `http://127.0.0.1:7130/*`

### 后端

```bash
python backend/run_server.py --reload
```

- 后端服务：`http://127.0.0.1:7130`
- 后端编辑协议：`docs/后端-编辑协议.md`

### 开发期检查工具

- 禁止运行期依赖 `references`：`python temp/check_no_references_usage.py`
- Profile v0.2 示例校验：`python temp/validate_profile_v0_2.py`
- 后端编辑尝试（创建 workspace 项目 + 应用一次指法编辑）：`python temp/backend_edit_try_v0_2.py`

## 参考与复用说明（alephpi/jianzipu）

本项目在“减字谱读法语法/符号集合/撮式结构”等方面，参考并部分复用了以下项目的设计思想与资料：

- `jianzipu`：`https://github.com/alephpi/jianzipu`
- `guqincomposer`: `https://github.com/neuralfirings/guqincomposer`
- `JianZiPu`: `https://github.com/neuralfirings/JianZiPu`

本项目还在开发中. 未来我们会在本仓库内持续补齐来源与许可证说明，确保合规。
