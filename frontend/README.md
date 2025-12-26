# GuqinAuto 前端（Next.js）

## 快速开始

```bash
cd frontend
npm install
npm run dev
```

- 前端默认端口：`7137`
- 后端默认端口：`7130`
- 开发期推荐走前端代理：`/api/backend/*`（同源）→ `BACKEND_BASE_URL`（默认 `http://127.0.0.1:7130`）

## 环境变量

- `frontend/.env`：`BACKEND_BASE_URL`

## 约定

- 路由骨架：
  - `/` 项目列表（占位）
  - `/import` 导入与参数（占位）
  - `/editor` 编辑器（布局骨架：结构栏/双谱面/Inspector/事件条）
  - `/settings` 设置（占位）

- 导出不单独做页面：统一在编辑器顶部工具栏触发（后续可做导出对话框/抽屉）。

## Node 版本

- 推荐使用 Node.js LTS（`frontend/.nvmrc`：`22`），并且 `frontend/package.json` 已通过 `engines` 约束为 `>=22 <23`。
- 若你使用较新的非LTS版本（例如 Node 23），可能会遇到 dev/构建阶段的奇怪报错；建议先切回 LTS 再排查。

## 常见问题

- 若出现 `Error: Cannot find module './xxx.js'` 且路径在 `frontend/.next/server/*`：
  - 这通常是 dev 增量构建缓存损坏/不一致导致
  - 处理：停止 dev → `npm run dev:clean`（等价于删掉 `.next` 后重启）

## 升级后的约定（工具链）

- Next.js 新版本不再提供 `next lint` 子命令：统一用 `eslint` 执行（配置见 `frontend/eslint.config.mjs`）。
- 为了更稳（尤其是多人协作/CI），开发与构建默认走 webpack：
  - `npm run dev`：`next dev --webpack`
  - `npm run build`：`next build --webpack`
