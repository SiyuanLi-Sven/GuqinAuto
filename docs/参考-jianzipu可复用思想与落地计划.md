---
title: "参考：jianzipu 项目可复用思想与落地计划"
status: draft
updated_at: "2025-12-27"
---

# 参考：jianzipu 项目可复用思想与落地计划

本文档总结我们从 `references/jianzipu`（https://github.com/alephpi/jianzipu）学到的、对 GuqinAuto **“自动推荐指法 + 编辑器输入体验 + 多音/撮建模”** 最有价值的思想，并给出**具体落地路线**。

> 重要约束（写死）
> - `references/` 仅供参考：**运行期禁止 import / 直接依赖** `references/` 下任何代码与资产。
> - GuqinAuto 的**真源**始终是 MusicXML（`score-partwise 4.1` + `GuqinJZP-MusicXML Profile`）。
> - 我们倾向“正确地失败”：解析失败/不一致必须显式暴露，禁止静默猜测。

相关背景材料（更偏“逐文件调查”）见：
- `references/文档/jianzipu-调查与启发.md`

---

## 0. TL;DR（先讲结论）

`jianzipu` 本质解决的是：**“减字谱读法（自然语言短语）→ 结构化谱字语法树(AST) → 字形渲染（SVG/KAGE）”**。

它并不解决：
- 音高/节奏/调弦的音乐建模（这正是 GuqinAuto 的真源层职责）
- 指法推荐优化（pitch→候选→序列优化）

因此对 GuqinAuto 最可复用的是两条主线：

1) **结构化表达与输入语法**（强相关）  
   - 把减字谱按 `simple/complex/aside/marker/both` 分类  
   - 明确 `abbr/ortho` 两种体例与解析策略（最长匹配 + 歧义补丁）  
   - 进一步引入“技法元数据”（valence/slot 需求）来支撑 chord/撮/历等多音结构

2) **输入体验**（强相关）  
   - 其 RIME 键盘方案表明：减字谱天然适合“键盘组合语言”  
   - 我们可以在编辑器里提供“菜单选择”之外的“文本/快捷键输入模式”，显著提升效率

“字形渲染（KAGE/IDS/SVG）”也可参考，但应视为后续可选路线（且其工程实现并不完全收敛）。

---

## 1. `jianzipu` 的关键抽象（对我们最有用的部分）

### 1.1 四层概念分离（非常值得保留）

`jianzipu` 明确区分：

- **读法文本**：例如 `大指二徽三分注勾一弦`（ortho），或 `大二三勾一`（abbr）
- **解析结构**：把读法解析成结构化树（AST）
- **显示方案**：AST → 字形（SVG），或 AST → 其它输出
- **输入方案**：RIME 键盘映射，降低输入成本

这与 GuqinAuto 的“真源/派生层”非常兼容：

```mermaid
flowchart LR
  A[用户输入] --> B[结构化真值]
  B --> C[派生显示层]

  subgraph GuqinAuto
    B --> D[MusicXML 真源 staff2 other-technical: GuqinJZP KV]
    D --> E[jzp_text (lyric below)]
  end

  subgraph jianzipu
    A --> F[读法 parse -> AST]
    F --> G[SVG/KAGE 渲染]
  end
```

我们的结论：**真值必须结构化（KV/字段），`jzp_text` 只是可重复生成的显示层**（这与你已写死的决策一致）。

### 1.2 五类谱字（forms）的分类是“规范级”的

`jianzipu` 将谱字分为：
- `simple`：简式（徽位/左右手 + 弦序）
- `complex`：复式（撮/掐撮/双弹/拨剌/齐撮 等，含左右子式）
- `aside`：旁注（上/下/进/退/吟/猱 等走位类）
- `marker`：记号（少息/大息/从头再作 等）
- `both`：联袂指法（同声/应合/放合/掐撮三声 等）

这与我们 Profile v0.2 现有的 `form=simple|complex|aside|marker|both` 是同构的；因此在 GuqinAuto 中，**继续坚持这五类 form，避免发散到更多“互斥不清”的分类**。

### 1.3 `abbr/ortho` 的二体例与“最长匹配分词”是工程关键

`jianzipu` 的解析器（pyparsing）有几个工程经验非常关键：
- token 必须**按长度降序**，保证 `勾剔` 不被拆成 `勾` + `剔`
- `abbr` 简写法存在 `十一/十二/十三` 的歧义，需要补丁（它对 complex 的子式做了修正）

我们已经把这些思想实现为本仓库自有解析器（运行期不依赖 references）：
- `backend/src/guqinjzp/jianzipu_text.py`

后续建议：把 `jianzipu` 的测试用例（`references/jianzipu/package/test.py`）中**可支持的语句**抽取为我们的回归测试集合（只复制测试数据，不 import references 代码）。

---

## 2. 对“自动分配指法（stage1/stage2）”最关键的借鉴：技法元数据（valence / slot）

`jianzipu` 虽然不做 pitch/tuning，但它隐含了一个对我们非常关键的事实：

> 很多“谱字/技法”天然要求**多个同时音**或**多个弦位**，这是语义约束，不是 UI 选择。

典型例子：
- `历`：常见为两弦（本质上要求 2 个弦位输入）
- `撮/掐撮/双弹/拨剌/齐撮`：一个谱字对应多个同时音（左右子式各一条弦）

这对 GuqinAuto 的影响是“端到端”的：

### 2.1 对 stage1（候选枚举）的影响

stage1 现在是“单音 pitch → 候选音位集合”。要支持撮/和弦，必须升级为：

- **输入**：一个事件可能含多个 target pitch（slot=1/2 或 L/R）
- **输出**：候选应当是 **组合候选（tuple of positions）**，或至少能表达“多 slot 同时满足”的候选结构

否则会出现两类错误：
- 推荐无法生成（因为 stage1 不知道需要两个音）
- 推荐看似生成但语义错（例如把 `撮` 当成单音处理）

### 2.2 对 stage2（序列优化）的影响

stage2 当前明确不支持 chord（`targets!=1` 会失败）。未来升级时需要：
- cost 函数包含“同一事件内部”的组合代价（例如两个音的弦距/位置可行性）
- 以及事件间的过渡代价（现有 shift/string_change/technique_change）

### 2.3 对 UI（用户输入）的影响

UI 不能把“单元是单音还是双音/撮”当成隐藏逻辑；必须显式：
- 单元结构（单音 / 双音 / complex 左右子式）
- 每个 slot 的弦/徽位选择
- 技法选择（并受结构约束）

---

## 3. 建议落地：在 GuqinAuto 内新增“技法元数据表”（我们自己的）

目标：把 `jianzipu` 的“谱字分类/隐含元数”升级为可执行的约束系统。

### 3.1 新增一个 YAML：`GuqinJZP-TechniqueMeta v0.1`

建议放在 `docs/data/`，与 token 集同级，作为**规范的一部分**（而不是散在代码里）。

内容建议包括（示例字段名，可调整）：
- `token`: 技法 token（例如 `历`, `撮`, `掐撮`, `双弹`）
- `form_allowed`: 允许出现在哪些 form（simple/complex/both/aside/marker）
- `valence`: 该 token 需要的同时音数量（例如 `历=2`, `撮=2`）
- `slot_schema`: slot 命名与结构（`[1,2]` 或 `[L,R]`）
- `xian_count_allowed`: 允许的弦数量（例如 `simple` 可为 1 或 2，但 `历` 必须为 2）
- `sound_allowed`: open/pressed/harmonic 的允许集合（与 Profile v0.3 的 `sound` 对齐）
- `defaults`: 当用户只选了“结构/技法”而未填全时，UI 默认填什么（注意：默认仅用于 UI 提示，真源写回仍需显式确认）

### 3.2 后端/前端共同消费这张表

后端用途：
- Profile 校验：检查 `xian_finger` 与 `xian` 列表长度一致（例如 `历` 必须两弦）
- stage1：若事件是 chord，按 slot_schema 枚举候选
- stage2：对 chord 事件可计算 cost 并输出 top-k

前端用途：
- Inspector：先选“结构/技法”，再展示对应 slot 的参数编辑控件
- 候选菜单：按 slot_schema 展示组合候选（而不是单音候选）

> 注意：这张表必须是“严格约束”，不是“软建议”，否则会回到“虚假成功”的老路。

---

## 4. 输入体验借鉴：把 RIME 的“键盘组合语言”转化为编辑器的快捷输入模式

`jianzipu` 的 `im/jianzipu_min.schema.yaml` 很值得我们学习，它把高频 token 映射为单键：
- 例如 `k=勾`, `j=抹`, `u=挑`, `i=剔`，以及数字键输入“徽/分/弦”

我们不需要把 RIME 嵌到浏览器，但可以借鉴其“输入语法”设计为编辑器提供两种模式：

### 4.1 菜单模式（低门槛）

适合新用户：
- 点击单元 → 弹出候选（来自 stage1/stage2）
- 选择后写回（`edit_source=user`）

### 4.2 文本/快捷键模式（高效率）

适合熟练用户：
- 光标选中单元后，直接输入一个 `abbr` 读法（例如 `散勾三`、`大七九挑六`）
- 前端调用我们的解析器（或后端解析服务）进行严格校验
- 校验通过后，映射成结构化 KV（并写回 MusicXML）

这要求我们在 GuqinAuto 内明确：
- **允许的输入语言**（我们自己的 token 集 + lex + 语法）
- **错误提示**（解析失败必须告诉用户“哪里不合法/缺哪个字段”）
- **与结构化真值的双向映射**（KV → jzp_text 已有；jzp_text → KV 需要补齐/明确）

---

## 5. 与 GuqinAuto Profile 的对齐建议（v0.2/v0.3）

### 5.1 `jianzipu` 的 form 与我们 Profile 的 form 一致（保持）

继续使用：
- `form=simple|complex|aside|marker|both`
- `lex=abbr|ortho`

### 5.2 多音/撮的“真值字段”必须结构化（与 `jzp_text` 分离）

我们已经有：
- `simple`：`xian=1` 或 `xian=1,2`（slot=1/2）
- `complex`：`l_xian/r_xian`（slot=L/R）

下一步要做的是把**技法元数据**与**pitch 一致性检查**接入：
- 如果是 `complex`（撮等），必须同时检查 L/R 两个 slot 的 derived pitch 与 staff1 pitch 的对应关系
- 如果是 `simple` 且 `xian` 两弦，也必须能检查两个 slot

这也是我们现在 stage2 “不支持 chord”需要升级的根因：缺少 slot-aware 的端到端表示。

---

## 6. 字形渲染（KAGE/IDS）能怎么用？（结论：先不急，但路线要写清）

`jianzipu` 具备“AST → KAGE → SVG”的完整愿景，但其代码实现存在明显工程未收敛点：
- KAGE 引擎在其 repo 中存在硬编码路径（不可移植）
- 复杂形式（complex）渲染并未覆盖全部 token
- token 集、渲染资产、语法之间存在演进不一致

因此对 GuqinAuto 的建议是：
- 近期：继续用 `jzp_text`（如“散挑三”）显示，不阻塞主链路
- 中期：我们自己做一条“可维护的、单一路线”的渲染：
  - `GuqinJZP KV -> AST -> SVG`（SVG 组件组合或字体）
  - 或直接 `KV -> SVG`（不引入完整 AST，但保持 form/slot 结构）
- 长期：可参考其 KAGE 资产/排布规则，但要以“复制/改写到本仓库”为前提，并在 LICENSE/NOTICE 中明确致谢与传播方式（本项目已是 AGPL，许可证层面兼容，但仍要保证来源标注清晰）。

---

## 7. 具体落地路线（建议按这个顺序做）

### Phase A：把“技法元数据表”写死并接入校验（最优先）
1) 新增 `docs/data/GuqinJZP-TechniqueMeta v0.1.yaml`
2) 后端：
   - Profile 校验：`xian_finger` 对应的弦数/slot 约束必须满足
   - `/status`：对 chord/complex 的一致性检查输出 slot 级 warning
3) 前端：
   - Inspector：根据 meta 表渲染输入控件（单音/双音/complex）

### Phase B：实现 chord-aware 的 stage1/stage2（核心能力升级）
1) stage1：支持多个 target pitch（slot-aware），输出组合候选结构
2) stage2：支持 chord 的 DP/beam（内部候选是“tuple”）
3) 写回：支持 `apply_mode=commit_best` 生成初稿（仅覆盖 `user_touched=0`）

### Phase C：编辑器“文本输入模式”
1) 前端提供一个输入框（abbr/ortho 可切换）
2) 前端本地解析（使用我们自己的 parser），或后端提供 parse endpoint（二选一）
3) parse 结果映射成 KV changes，通过 `/apply edit_source=user` 写回

### Phase D：字形渲染（可选）
在前面三步完成且稳定后再做。

---

## 8. 合规与工程卫生（AGPL 与 references 禁依赖）

我们当前仓库 `LICENSE` 已是 **AGPL-3.0**，与 `jianzipu` 的 `LICENSE` 在大方向上兼容。

但仍需注意：
- `references/jianzipu/readme.md` 末尾有 “All rights reserved” 叙述，与 `LICENSE` 文件的开放许可表述存在冲突；工程合规上应以 `LICENSE` 为准，但我们在复制代码/资产时仍应谨慎并保留来源信息。
- 运行期禁止依赖 `references/`：若要复用其代码/资产，必须复制到本仓库目录（并在 docs/README 中声明来源与修改）。

