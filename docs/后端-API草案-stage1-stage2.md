# 后端 API 草案：stage1 音位枚举 + stage2 指法优化（v0 草案）

本文档把“简谱 → 古琴减字谱”的两阶段建模（stage1/stage2）落成可实现的后端 API 契约，供前端编辑器与后端实现对齐使用。

定位与原则：

- **真源**：单个 MusicXML（`score-partwise 4.1`），双 staff；事件身份 `eid` 全曲唯一。
- **综合视图**：每行 system 上简谱下减字谱，两者不可拆分。
- **学术级**：宁可失败也不静默降级；校验失败必须 4xx 明确报错。
- **结构化指法字段为真值**：`jzp_text` 仅为可重复生成的派生显示层。

现有最小编辑协议见：`docs/后端-编辑协议.md`

---

## 0. 术语

- **事件（Event）**：节奏时间线的一个时刻片段，由 staff1 决定；用 `eid` 标识。
- **stage1（候选枚举）**：给定目标音高与定弦，枚举所有可行音位候选（散/按/泛、弦号、位置）。
- **stage2（序列优化）**：在每个事件候选集合上选择一条满足约束的“可弹路径”，并输出 top-K 与解释。

---

## 1. 数据模型草案（JSON Schema 级别描述）

### 1.1 调弦（tuning）

后端统一使用绝对音高（建议 MIDI note number），避免“相对音高+调性”在 stage1 引入歧义。

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
    "hui_real": 7.0000,
    "pos_ratio": 0.5000,
    "hui_quantized": {"hui": 7, "fen": null, "fen_kind": null}
  },
  "source": {
    "method": "12tet_table",
    "table": "NoteViz(d=0..36)",
    "confidence": 1.0
  }
}
```

约束：

- `technique` ∈ `{ "open", "press", "harmonic" }`
- `d_semitones_from_open`：`open/press` 必须为整数；`open` 时为 0
- `pos.hui_real`：`press/harmonic` 建议必填；`open` 可为 null
- `pos_ratio`：建议作为与 `hui_real` 等价的“物理真值”（按弦点相对有效弦长比例），便于跨实现对齐  
  - `hui_real` 是传统“按徽位连续坐标”的表达；`pos_ratio` 是更通用的物理表达

### 1.3 stage1 输出（按事件聚合）

```json
{
  "project_id": "Pxxxx",
  "revision": "R000123",
  "tuning": { "...": "..." },
  "events": [
    {
      "eid": "E000001",
      "target_pitch": {"midi": 72},
      "candidates": [ /* PositionCandidate[] */ ],
      "errors": []
    }
  ],
  "warnings": []
}
```

说明：

- `errors` 用于“该事件无候选”或“谱面缺少 pitch 无法进入 stage1”
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
    {"eid": "E000011", "fields": {"technique": "open"}}
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

---

## 2. API 端点草案（与现有 /projects/* 兼容）

### 2.1 stage1：枚举候选音位

`POST /projects/{project_id}/stage1`

请求体：

```json
{
  "base_revision": "R000001",
  "tuning": {
    "name": "F_5612356",
    "open_pitches_midi": [67,69,72,74,76,79,81],
    "transpose_semitones": 0
  },
  "options": {
    "include_harmonics": false,
    "max_d_semitones": 36
  }
}
```

返回：
- `Stage1Result`（见 1.3）

失败（400）：
- MusicXML 缺少 staff1 pitch（无法得出 `target_pitch`）
- `open_pitches_midi` 非法（长度不为 7、或存在非 int）

> 备注：当前 Profile v0.2 里 staff1 pitch 可能为空（若仅保留简谱度数），则必须先明确“调性/主音”或直接把绝对 pitch 写入 MusicXML。

### 2.2 stage2：在候选图上做优化，产出 top-K 并写回

`POST /projects/{project_id}/stage2`

请求体：

```json
{
  "base_revision": "R000001",
  "tuning": { "...同 stage1..." },
  "k": 5,
  "locks": [ /* 见 1.4 */ ],
  "preferences": { /* 见 1.4 */ },
  "window": {"from_eid": "E000001", "to_eid": "E000064"},
  "apply": {
    "mode": "commit_best",
    "message": "stage2 optimize window E1..E64"
  }
}
```

返回（当 `apply.mode=commit_best`）：

```json
{
  "project": { /* ProjectMeta，revision 前进 */ },
  "score": { /* ProjectScoreView，新 revision */ },
  "stage2": { /* Stage2Result，含 top-K 与 explain */ }
}
```

失败（409）：
- `base_revision` 冲突（与现有编辑协议一致）

失败（400）：
- stage1 无法为某个 eid 枚举候选
- locks 导致候选集为空/不一致
- 生成 `derived_guqinjzp_kv` 无法通过 Profile 校验（必须失败）

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

1) 连续位置真值：`hui_real` 或 `pos_ratio`
2) 声源类别：`sound=open|pressed|harmonic`
3) 泛音节点表达：`harmonic_node` 或 `harmonic_ratio`

建议策略：

- **真值字段先行**（可校验/可诊断/可优化）
- `hui/fen/OUT` 与 `jzp_text` 继续作为派生显示层（可重复生成与一致性校验）

---

## 4. 与 NancyLiang 参考的对应关系（仅用于设计对齐）

更多背景与启发总结见：
- `references/NancyLiang/启发-对GuqinAuto的启发.md`

