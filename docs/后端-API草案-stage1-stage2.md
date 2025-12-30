# 后端 API 草案：stage1 音位枚举 + stage2 指法优化（v0 草案）

本文档把“简谱 → 古琴减字谱”的两阶段建模（stage1/stage2）落成可实现的后端 API 契约，供前端编辑器与后端实现对齐使用。

定位与原则：

- **真源**：单个 MusicXML（`score-partwise 4.1`），双 staff；事件身份 `eid` 全曲唯一。
- **综合视图**：每行 system 上简谱下减字谱，两者不可拆分。
- **学术级**：宁可失败也不静默降级；校验失败必须 4xx 明确报错。
- **结构化指法字段为真值**：`jzp_text` 仅为可重复生成的派生显示层。
- **写回由用户显式触发（写死）**：
  - stage1/stage2 负责“计算与建议”
  - 写回分两类：导入后“一键生成初稿”（允许写回）与编辑期“逐单元确认写回”
  - 禁止静默写回：不得在后台悄悄改谱

现有最小编辑协议见：`docs/后端-编辑协议.md`

---

## 0. 术语

- **事件（Event）**：节奏时间线的一个时刻片段，由 staff1 决定；用 `eid` 标识。
- **stage1（候选枚举）**：给定目标音高与定弦，枚举所有可行音位候选（散/按/泛、弦号、位置）。
- **stage2（序列优化）**：在每个事件候选集合上选择一条满足约束的“可弹路径”，并输出 top-K 与解释。
  - 注意：stage2 输出是“建议态”，用于 UI 展示默认建议/对比，不直接写回真源。

---

## 1. 数据模型草案（JSON Schema 级别描述）

### 1.1 调弦（tuning）

后端统一使用绝对音高（建议 MIDI note number），避免“相对音高+调性”在 stage1 引入歧义。

重要约束（写死）：

- 系统允许“只给简谱度数”的输入形态，但在进入 stage1/stage2/回放/导出链路之前，必须补齐调性/主音/移调等信息，并把绝对 pitch **编译落地写入 MusicXML staff1**。
- 若 MusicXML 当前处于 pitch-unresolved 状态（staff1 无法提供绝对 pitch），stage1/stage2 MUST 失败（正确地失败，不猜 key/pitch）。

```json
{
  "tuning": {
    "name": "F_5612356",
    "open_pitches_midi": [67, 69, 72, 74, 76, 79, 81],
    "transpose_semitones": 0
  }
}
```

字段说明：

- `open_pitches_midi`: 长度必须为 7，对应弦序 1..7
- `transpose_semitones`: 整体移调（为“谱面整体升降”留接口）

> 注：具体 F 调 5612356 的 open MIDI 只是示例。最终应支持多预置与自定义。

### 1.2 stage1 候选（PositionCandidate）

stage1 输出以“可计算/可诊断/可回归”为目标，建议显式包含连续位置真值：

```json
{
  "string": 3,
  "technique": "press",
  "pitch_midi": 72,
  "d_semitones_from_open": 12,
  "pos": {
    "pos_ratio": 0.5000,
    "hui_real": 7.0000,
    "source": "pos_ratio=12tet; hui_real=table"
  },
  "cents_error": 0.0,
  "harmonic_n": null,
  "harmonic_k": null,
  "temperament": "equal",
  "source": {"method": "12tet_press"}
}
```

约束：

- `technique` ∈ `{ "open", "press", "harmonic" }`
- `d_semitones_from_open`：`open/press` 必须为整数；`open` 时为 0
- `pos.pos_ratio`：`press/harmonic` 建议必填；`open` 可为 null  
  - `pos_ratio` 是连续位置的主真值（物理/可优化/可回归）
- `pos.hui_real`：派生显示/缓存层，`press/harmonic` 可选；`open` 可为 null  
  - `hui_real` 不作为底层真值，不能替代 `pos_ratio`
- `cents_error`：与所选模型（pressed 为 12-TET；harmonic 为自然泛音 n）之间的偏差，单位 cents  
  - pressed/open 默认 `0.0`；harmonic 可能为非零，前端可据此提示“近似泛音”
- `harmonic_n/harmonic_k`：仅当 `technique=harmonic` 时存在，表示候选来自第 n 泛音、节点位置 k/n（pos_ratio=k/n）

### 1.3 stage1 输出（按事件聚合）

```json
{
  "project_id": "Pxxxx",
  "revision": "R000123",
  "tuning": { "...": "..." },
  "events": [
    {
      "eid": "E000001",
      "targets": [
        {
          "slot": "L",
          "target_pitch": {"midi": 72},
          "candidates": [ /* PositionCandidate[] */ ],
          "errors": []
        },
        {
          "slot": "R",
          "target_pitch": {"midi": 76},
          "candidates": [ /* PositionCandidate[] */ ],
          "errors": []
        }
      ]
    }
  ],
  "warnings": []
}
```

说明：

- `targets`：一个事件可能是单音或 chord；stage1 按 staff1 的每个 note 输出一个 target
  - `slot` 来自 `GuqinLink@0.2.slot`，用于后续在 stage2/写回时对齐撮/和弦结构
- `errors` 用于“该 target 在当前 tuning 下无候选”等可诊断信息；若 MusicXML 缺少绝对 pitch，则 stage1 直接失败（pitch-unresolved）
- `warnings` 用于“候选过少/过多”或“需要用户设定调性/绝对音高”

### 1.4 stage2 约束输入（Locks / Preferences）

stage2 输入必须同时支持：

- 编辑器对单个事件或范围的锁定（硬约束）
- 风格/偏好（软约束，反映在代价函数）

建议结构：

```json
{
  "locks": [
    {"eid": "E000010", "fields": {"string": 3}},
    {"eid": "E000011", "fields": {"technique": "open"}},
    {"eid": "E000012", "fields": {"slot": "L", "string": 3}}
  ],
  "preferences": {
    "prefer_harmonic": 0.2,
    "prefer_same_string": 0.6,
    "avoid_large_shifts": 0.8
  },
  "window": {"from_eid": "E000001", "to_eid": "E000064"}
}
```

约束与失败策略：

- 锁定字段导致候选集合为空：必须 400 失败，并返回“最小冲突集”或至少指出冲突 eid
- chord 锁定必须显式指定 `fields.slot`（例如 `L/R` 或 `1/2/...`）；若缺失 slot，必须失败（避免歧义）。

### 1.5 stage2 输出（Top-K 方案 + 可解释）

```json
{
  "k": 5,
  "solutions": [
    {
      "solution_id": "S0001",
      "total_cost": 123.4,
      "assignments": [
        {
          "eid": "E000001",
          "choice": { /* PositionCandidate 的精简引用或 index */ },
          "derived_guqinjzp_kv": { /* 用于写回 MusicXML 的结构化字段 */ }
        }
      ],
      "explain": {
        "cost_breakdown": {
          "shift": 80.0,
          "string_change": 15.0,
          "style": 10.0,
          "risk": 18.4
        },
        "notable_transitions": [
          {"from_eid": "E000010", "to_eid": "E000011", "reason": "large_shift", "delta_hui_real": 3.2}
        ]
      }
    }
  ]
}
```

关键：`derived_guqinjzp_kv` 是“写回真源”的桥梁，必须能严格校验并生成 `jzp_text`。

重要边界（写死）：

- stage2 产出的 `derived_guqinjzp_kv` 仅用于 UI 展示与“候选对比”，不等于已经写回真源
- 真值写回必须由用户显式触发：前端在用户确认后调用 `POST /projects/{project_id}/apply` 提交 `update_guqin_event`（或未来的更细粒度 op）

---

## 现状备注（与代码对齐）

- stage2 推荐目前已支持：
  - 单音事件（targets=1, slot=null）
  - 2-note chord（targets=2，要求 slot 非空且唯一；输出 `assignments[].choices[]`）
- stage2 的锁定（locks）目前仅对单音事件生效；若对 chord 事件传 locks，后端会明确失败（避免锁定语义歧义）。
- stage2 的 `apply_mode=commit_best`（生成初稿写回）：
  - 单音事件：支持（写入 `sound/pos_ratio/harmonic_n` 等 v0.3 真值字段）
  - chord 事件：仅在 staff2 已具备可承载结构时支持写回（例如 `form=complex` 且 slot=L/R）；否则会明确失败（不猜结构）。

---

## 2. API 端点草案（与现有 /projects/* 兼容）

### 2.0 pitch-resolved：把绝对 pitch 编译落地写入 staff1

stage1/stage2 的硬前提是 staff1 能提供绝对 pitch。为了避免“猜 key/猜 enharmonic”，后端提供一个严格端点用于写回绝对 pitch：

- `POST /projects/{project_id}/resolve_pitch`

请求体（示例）：

```json
{
  "base_revision": "R000001",
  "message": "resolve staff1 pitch",
  "require_pitch_resolved_after": true,
  "assignments": [
    {"eid": "E000010", "slot": "L", "step": "D", "alter": 0, "octave": 4},
    {"eid": "E000010", "slot": "R", "step": "F", "alter": 0, "octave": 4}
  ]
}
```

约束（写死）：
- 调用方必须明确给出 `step/alter/octave`；后端不会把 MIDI 自动反解为 step（避免 enharmonic 猜测）
- `slot=null` 仅在该 `eid` 在 staff1 非 chord（仅 1 个 note）时允许，否则必须提供 slot

返回：
- `project`（新 revision）
- `score`（新 revision 的 `ProjectScoreView`）

### 2.0.1 pitch-resolved：从简谱度数编译（严格子集）

为了覆盖“输入只有简谱度数”的常见工作流，后端提供一个**严格子集**编译端点：

- `POST /projects/{project_id}/compile_pitch_from_jianpu`

请求体（示例）：

```json
{
  "base_revision": "R000001",
  "message": "compile pitch from jianpu",
  "tonic": {"step": "C", "alter": 0, "octave": 4},
  "mode": "major",
  "octave_shift": 0,
  "require_pitch_resolved_after": true
}
```

约束（写死，避免“虚假成功”）：
- 主音必须以 `step/alter/octave` 明确给出（不接受只给 MIDI 再反推 step，因为那会引入 enharmonic 猜测）
- 当前只支持简谱度数文本为单个字符 `'1'..'7'`（来自 staff1 `lyric@above`）；出现升降号/八度点/复杂语法必须失败
- 当前只支持单音事件（staff1 每个 `eid` 仅 1 个 note）；遇到 chord 必须失败

### 2.1 stage1：枚举候选音位

`POST /projects/{project_id}/stage1`

请求体：

```json
{
  "base_revision": "R000001",
  "tuning": null,
  "options": {
    "include_harmonics": false,
    "max_harmonic_n": 12,
    "max_harmonic_cents_error": 25.0,
    "max_d_semitones": 36
  }
}
```

说明：
- `tuning=null` 表示使用项目配置（`project.json`）中的 tuning；也允许在请求体中提供 tuning 来覆盖本次计算。
- `include_harmonics=true` 时，stage1 会额外输出自然泛音的近似候选（以 harmonic number `n` 匹配，并输出节点 `k/n` 的 `pos_ratio`）。该功能必须显式声明其覆盖范围，不能假装完整无损。

返回：
- `Stage1Result`（见 1.3）

失败（400，示例）：
- MusicXML 缺少 staff1 pitch（无法得出 `target_pitch`）
- `open_pitches_midi` 非法（长度不为 7、或存在非 int）

> 备注：当前 Profile v0.2 里 staff1 pitch 可能为空（若仅保留简谱度数），则必须先明确“调性/主音”或直接把绝对 pitch 写入 MusicXML。

返回中的 `events[].errors`（若启用）用于表达“该 eid 在当前 tuning/transpose/max_d 下无候选”等可诊断信息；这不是静默降级，前端可据此提示用户调整参数。stage2 在遇到无候选时必须失败。

### 2.1.1 读取/更新项目 tuning

为便于前端把 tuning 作为项目参数管理，后端提供：

- `GET /projects/{project_id}/tuning`
- `PUT /projects/{project_id}/tuning`

`PUT` 请求体：

```json
{
  "tuning": {
    "name": "custom",
    "open_pitches_midi": [55,57,60,62,64,67,69],
    "transpose_semitones": 0
  }
}
```

### 2.1.2 创建项目时指定 tuning（可选）

`POST /projects` 请求体可以携带 `tuning`，用于项目创建后默认的 stage1/stage2 参数；若不提供则使用后端内置默认 demo tuning。

### 2.1.3 项目就绪性诊断（pitch-resolved）

前端在展示“推荐/再优化/导出回放”等按钮前，应先查询：

- `GET /projects/{project_id}/status`

该端点返回：
- `pitch_resolved`：是否已满足 stage1/stage2 的绝对 pitch 前提
- `pitch_issues`：缺失的 `eid/slot` 列表（用于 UI 引导用户补齐调性并编译落地）

### 2.2 stage2：在候选图上做优化，产出 top-K（不写回）

`POST /projects/{project_id}/stage2`

请求体：

```json
{
  "base_revision": "R000001",
  "tuning": { "...同 stage1..." },
  "k": 5,
  "locks": [ /* 见 1.4 */ ],
  "preferences": { /* 见 1.4 */ }
}
```

当前实现说明（重要）：

- stage2 仅支持“推荐不写回”：后端返回 top-K 方案，但不会修改 MusicXML 真源。
- 写回（把建议变成真值）必须由用户显式触发，通过 `/apply` 提交：
  - A) 导入后“一键生成初稿”：把某个 solution 写回生成新 revision（初步方案）
  - B) 编辑期逐单元：用户在菜单中选择候选与技法后写回

写回元数据（SHOULD）：

- 前端在调用 `/apply` 写回初稿时，建议传 `edit_source=auto`（用于写回 `truth_src=auto,user_touched=0`）
- 用户逐单元修改确认时，传 `edit_source=user`（写回 `truth_src=user,user_touched=1`）

---

## 2.3 再次主动推荐（方向先记录，未实现）

场景：用户已对部分单元做了修改确认（`user_touched=1`），希望系统根据这些上下文对剩余未改部分（`user_touched=0`）做“再次推荐”。

约束（写死）：

- `user_touched=1` 的单元在再次推荐时视为硬约束，不允许被修改
- `user_touched=0` 的单元允许被重新推荐与写回

建议的落地形式（两种都可，二选一或都做）：

1) **建议态返回（不写回）**：返回新的 top-K 建议供 UI 选择，不自动写回
2) **生成新初稿 revision（写回）**：用户点击“对未改部分再推荐”，后端生成一个新 revision 并写回（仅覆盖 `user_touched=0` 的单元），用于对比/回滚

该端点/协议目前仅记录为需求方向，尚未实现。

返回（当前实现）：

```json
{
  "project_id": "Pxxxx",
  "revision": "R000001",
  "tuning": { "...": "..." },
  "stage1_warnings": [],
  "stage2": { "k": 5, "solutions": [] }
}
```

错误约定：
- `409`：`base_revision` 冲突（与现有编辑协议一致）
- `400`：stage1 无法为某个 eid 枚举候选、locks 导致无候选、或遇到暂不支持情况（例如 chord）

### 2.3 与现有 `/apply` 的关系

建议保留现有：
- `POST /projects/{project_id}/apply`：用于用户在 Inspector 的“结构化字段级编辑”

新增 stage2 后的调用关系：
- Inspector 改字段（锁定/硬约束） → `/apply`
- 用户点击“按当前锁定再优化（窗口/全曲）” → `/stage2`

这样保证：
- 手工编辑与自动优化都通过 revision/delta 统一审计
- 不引入第二真源

---

## 3. 对 MusicXML Profile 的最小演进建议（v0.2 → v0.3 方向）

stage1/stage2 要把“音乐建模”做严谨，Profile v0.2 需要补齐的信息主要是：

1) 连续位置真值：`pos_ratio`（主真值）与 `hui_real`（派生显示/缓存）
2) 声源类别：`sound=open|pressed|harmonic`
3) 泛音节点表达：`harmonic_node` 或 `harmonic_ratio`

建议策略：

- **真值字段先行**（可校验/可诊断/可优化）
- `hui/fen/OUT` 与 `jzp_text` 继续作为派生显示层（可重复生成与一致性校验）

---

## 4. 与 NancyLiang 参考的对应关系（仅用于设计对齐）

更多背景与启发总结见：
- `references/NancyLiang/启发-对GuqinAuto的启发.md`
