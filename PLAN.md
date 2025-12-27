# GuqinAuto 开发计划（滚动更新）

本文档是 GuqinAuto 的仓库级开发计划与阶段性里程碑。我们坚持：

- **唯一真源**：MusicXML（`score-partwise 4.1` + `GuqinJZP-MusicXML Profile`），不引入第二真源
- **编辑器本位**：综合双谱视图（每行上简谱下减字谱）不可拆分
- **学术级**：宁可失败也不静默降级；所有校验与不一致必须显式暴露

关键规范入口：

- Profile：`docs/data/GuqinJZP-MusicXML Profile v0.2.md`
- 后端最小编辑协议：`docs/后端-编辑协议.md`
- stage1/stage2 API 草案：`docs/后端-API草案-stage1-stage2.md`

---

## Phase 0（已完成）：真源与最小编辑闭环

目标：保证 MusicXML 真源可被严格解析、校验、并支持最小编辑写回。

- [x] 定义 Profile v0.2（双 staff + `eid` 对齐 + `GuqinJZP@0.2` 结构化字段）
- [x] 后端 workspace/revision/delta 模型与 API 骨架（FastAPI）
- [x] 后端 `update_guqin_event`：结构化字段编辑 → 生成 `jzp_text` → 写回 MusicXML
- [x] examples 与校验脚本（开发期）

---

## Phase 1（近期优先）：把“音高/定弦/音位”建模补齐（stage1）

目标：在 MusicXML 真源内具备足够信息，使得“简谱→绝对音高→候选音位”确定可复现。

1) **明确 pitch 真值来源**
   - 选择方案（必须定一个）：staff1 直接写绝对 pitch；或通过“调性/主音”把简谱度数编译成绝对 pitch（并写入 staff1）
2) **实现 stage1 PositionEngine（后端）**
   - 输入：target pitch + tuning（7 弦 open pitch）+ 选项（泛音候选等）
   - 输出：每个 eid 的候选音位集合（散/按/泛，含连续位置真值）
3) **Profile 演进到 v0.3（最小增量）**
   - 为连续按弦位置与声源类别补齐真值字段（例如 `pos_ratio/hui_real`、`sound=open|pressed|harmonic`、泛音节点）

验收标准：
- 对同一份 MusicXML 与同一套 tuning，stage1 输出候选集合稳定一致（可回归测试）
- 对“无候选”的事件明确失败并给出诊断信息

---

## Phase 2：候选路径优化（stage2）+ top-K + 可解释

目标：把自动推荐落成可解释、可控、可编辑、可回滚的优化模块。

1) stage2 优化器（DP/Viterbi/beam/k-shortest-path 均可，优先确定性）
2) 支持锁定字段（硬约束）与风格偏好（软约束）
3) 输出 top-K 与 cost breakdown（用于“候选与诊断”面板）
4) 与 revision/delta 集成：优化结果可 commit 为新 revision，支持局部窗口再优化

验收标准：
- 锁定冲突时明确失败（指出冲突 eid/字段），不做“尽量凑一个”
- top-K 方案可重复生成，且解释信息可复核

---

## Phase 3：前端编辑器 MVP（精致交互优先，功能逐步填充）

目标：把“综合双谱视图 + Inspector 编辑 + 后端校验写回”打通到可用程度。

1) 项目列表/创建/打开（workspace 项目）
2) 编辑器页：
   - 中央综合视图（先用事件级列表渲染占位，后续接 OSMD）
   - 选中联动（eid 贯穿）
   - Inspector：结构化字段编辑（调用 `/apply`）
3) “再优化”入口（调用 `/stage2` 草案接口，先占位）
4) 导出入口在编辑器内（不暴露 `/export` 路由）

验收标准：
- 前端任何编辑都能回写到 MusicXML 真源，并能立刻重新拉取/渲染验证一致性

---

## Phase 4：渲染与导出精炼（可视化与可回放）

目标：把输出打磨到“可用于分享/教学/回放验证”。

1) OSMD 渲染集成与局部刷新策略
2) 减字谱精致渲染方案选择（字体路线 vs 自绘路线，二选一为主）
3) MIDI 派生与音频渲染缓存（明确是有损派生物，不回写真源）

---

## 当前下一步（建议你拍板的两个决定）

这两点我们已经决策如下（写死，后续实现以此为准）：

1) **绝对音高（staff1 pitch）**：允许“只给简谱度数”的输入形态，但系统在进入任何推荐/优化/回放/导出链路前，必须补齐调性/主音/移调等信息，并把绝对 pitch **编译落地写入 MusicXML staff1**。如果处于 pitch-unresolved 状态，则必须阻塞 stage1/stage2 与 MIDI/音频导出（正确地失败，不猜 key/pitch）。
2) **连续位置真值（Profile v0.3）**：以 `pos_ratio` 为主真值（物理/可优化/可回归），`hui_real` 仅作为派生显示/缓存层（可从 `pos_ratio` 或等价信息重复生成并校验），不作为底层真值。
