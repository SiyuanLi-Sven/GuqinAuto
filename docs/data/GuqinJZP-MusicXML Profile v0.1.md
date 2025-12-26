[![古琴指法简表(减字谱) | C'Joy](https://tse3.mm.bing.net/th/id/OIP.G5M1FGAeZ9NIhMb_rCiCwwHaJ7?pid=Api)](https://blog.yelf.me/enjoy/hobby/guqin-reference/?utm_source=chatgpt.com)

下面给你一套“**以 MusicXML 为底座、可扩展、能覆盖常见减字谱指法**”的数字化方案（我把它写成一个可直接落地的 **GuqinJZP-MusicXML Profile v0.1** 规范草案）。减字谱本质上是古琴的指法谱/tablature ([维基百科][1])，而 MusicXML 正好允许把“常规音符（节奏/音高）”与“演奏法/技术记号（technical / other-technical / other-notation）”绑在同一个 `<note>` 上，并支持用 SMuFL glyph 名称做渲染挂钩 ([W3C][2])。

---

## 1) 设计目标：把“简谱+减字谱”放进一个可编辑、可回放、可渲染的统一对象

你的产品里用户看到的是“简谱（节奏）+减字谱（指法）”，因为减字谱天生不含节奏信息；所以底层需要一个同时承载节奏与指法的结构。MusicXML 的定位更像“**乐谱交换与排版语义**”，比 MIDI 这种“**事件/回放语义**”更适合作为编辑器“本位”。（你后面做回放再从 MusicXML 导出 MIDI/音频就行。）

---

## 2) 总体分层：MusicXML 里保留 4 层信息

**(A) 节奏层**：完全用 MusicXML 原生 `<duration> / <type> / <dot> / <time-modification>` 表示。
**(B) 音高层**：可以存“实际发声音高”（方便回放），也可以额外存“简谱级数”（方便用户显示与输入）。
**(C) 古琴指法层（核心）**：把每个音的“音别（散/按/泛）+ 弦序 + 徽位/微分 + 左右手指法/组合技法”绑定到对应 `<note>`。减字谱常见符号里明确区分了散音/按音/泛音等音别 ([维基百科][1])。
**(D) 渲染层**：给减字谱字形一个“可重复生成”的 canonical 编码（比如 ASCII/罗马码），渲染时可对接现有“减字谱字体/合字系统”。现有的 JianZiPu 字体方案会把一个谱字拆成多个组件并用合字/编译器组合出来 ([nyl.io][3])。

---

## 3) 核心对象：GuqinEvent（每个 MusicXML `<note>` 对应一个）

我建议你把“古琴信息”收敛成一个确定性对象，然后**序列化塞进 MusicXML 的 `<other-technical>` 文本里**（因为 MusicXML 明确允许用 other-technical 承载未覆盖的演奏法，并可挂 smufl glyph 名称 ([W3C][2])）。

### 3.1 GuqinEvent 字段（v0.1）

| 字段    |          类型 |   必填 | 含义                                                                          |
| ----- | ----------: | ---: | --------------------------------------------------------------------------- |
| `v`   |      string |    是 | 版本号，如 `guqin-jzp@1`                                                         |
| `sd`  |        enum |    是 | 音别：`SAN`(散) / `AN`(按) / `FAN`(泛)（减字谱常见音别符号）([维基百科][1])                      |
| `gs`  | int / int[] |    是 | 弦序 1–7（和减字谱一致）。若是撮/和弦可为数组                                                   |
| `hp`  |      string | 条件必填 | 徽位/微分位置，如 `9`、`7.6`、`10.3`（现代常用“徽.分/微分”写法可用小数表达）([mondayisformusic.com][4]) |
| `lf`  |        enum | 条件必填 | 左手指：`THUMB/INDEX/MIDDLE/RING` 以及 `RING_KNEEL`（“跪”）等（减字谱左手指法符号）([维基百科][1])   |
| `la`  |      enum[] |    否 | 左手动作（见第6节枚举）：上/下/进/退/绰/注/吟/猱/掐起/带起/罨… ([维基百科][1])                           |
| `rh`  |        enum |    是 | 右手指法（见第5节枚举）：擘/托/抹/挑/勾/剔/打/摘/历/轮/锁/撮/滚/拂… ([维基百科][1])                       |
| `rt`  |      enum[] |    否 | 右手扩展标签：如 `XIAO_CUO/DA_CUO`（撮大小撮）等 ([维基百科][1])                               |
| `co`  |      enum[] |    否 | 左右配合技法：分开/同声/应合/放合/掐撮… ([维基百科][1])                                          |
| `jzp` |      string | 否但推荐 | canonical 减字谱编码（给渲染/回写用），可用“六名勾(九)”或 ASCII 简写“6sk(9)”这类体系 ([nyl.io][3])     |

> 规则：**尽量让这些字段“可逆”**——你从简谱生成减字谱时输出它；用户手动改减字谱时也改它；然后你再从它反写回 MusicXML 和回放层。

---

## 4) MusicXML 承载方式（尽量不破坏通用兼容性）

### 4.1 绑定到 `<note>` 的位置

* 用 `<notations><technical>` 放“可复用的通用字段”：如 `<string>`（弦序）。MusicXML 的 technical 体系里本就有 `<string>` 元素（常用于指法谱/吉他谱）([W3C][5])
* 用 `<notations><technical><other-technical>` 放“古琴扩展字段串”：`guqin-jzp@1;sd=...;gs=...;...` ([W3C][2])
* 用 `<notations><technical><harmonic>` 表示泛音（能用原生就用原生，方便其它软件理解）。减字谱中也把泛音作为独立音别 ([维基百科][1])
* 需要跨音符的滑音/连贯动作时，优先用 `<glissando>` / `<slide>` 等原生 start/stop；表达不了再用 `<other-notation type="start/stop">` ([W3C][6])

### 4.2 “简谱显示”怎么放

如果你希望 MusicXML 里能显式声明“简谱谱号”，MusicXML 有 `clef-sign` 的 `jianpu`/`jianpu-2` 等符号值 ([W3C][7])。实际工程里，你也可以把简谱数字放进 `<lyric>` 或 `<direction><words>` 作为 UI 层显示的保底方案。

---

## 5) 右手指法枚举（覆盖减字谱常见集合）

我建议内部代码统一用 `RH_*`，并保留中文名做展示。下表基本按减字谱“常见右手指法符号”覆盖：擘/托/抹/挑/勾/剔/打/摘，以及轮、锁、撮、滚、拂等扩展 ([维基百科][1])。

| `rh` 代码        | 中文  | 典型含义（简述）                    |
| -------------- | --- | --------------------------- |
| `RH_PI`        | 擘   | 大指向内拨弦 ([维基百科][1])          |
| `RH_TUO`       | 托   | 大指向外拨弦 ([维基百科][1])          |
| `RH_MO`        | 抹   | 食指向内拨弦 ([维基百科][1])          |
| `RH_TIAO`      | 挑   | 食指向外拨弦 ([维基百科][1])          |
| `RH_GOU`       | 勾   | 中指向内拨弦 ([维基百科][1])          |
| `RH_TI`        | 剔   | 中指向外拨弦 ([维基百科][1])          |
| `RH_GOU_TI`    | 勾剔  | 勾、剔相连 ([维基百科][1])           |
| `RH_DA`        | 打   | 无名指向内拨弦 ([维基百科][1])         |
| `RH_ZHAI`      | 摘   | 无名指向外拨弦 ([维基百科][1])         |
| `RH_LI`        | 历   | 食指连挑两弦或数弦 ([维基百科][1])       |
| `RH_JUAN`      | 蠲   | 同一弦连续抹、勾 ([维基百科][1])        |
| `RH_LUN`       | 轮   | 同一弦连续摘、剔、挑 ([维基百科][1])      |
| `RH_BANLUN`    | 半轮  | 同一弦连续摘剔或剔挑 ([维基百科][1])      |
| `RH_SUO`       | 锁   | 同一弦连续剔抹挑 ([维基百科][1])        |
| `RH_BEI_SUO`   | 背锁  | 锁的变体（常三声/四声） ([维基百科][1])    |
| `RH_DUAN_SUO`  | 短锁  | 五声锁 ([维基百科][1])             |
| `RH_CHANG_SUO` | 长锁  | 六至十三声锁（七声常见） ([维基百科][1])    |
| `RH_RUYI`      | 如一声 | 前两声合为一声 ([维基百科][1])         |
| `RH_SHUANGTAN` | 双弹  | 在按音与空弦上弹两个“如一声” ([维基百科][1]) |
| `RH_BO`        | 拨   | 食/中/名同时向内拨弦 ([维基百科][1])     |
| `RH_LA`        | 剌   | 食/中/名同时向外拨弦 ([维基百科][1])     |
| `RH_BOLA`      | 拨剌  | 拨、剌相连 ([维基百科][1])           |
| `RH_FU_STOP`   | 伏   | 三指落弦“煞住余音” ([维基百科][1])      |
| `RH_LA_FU`     | 剌伏  | 剌、伏相连 ([维基百科][1])           |
| `RH_CUO`       | 撮   | 同时挑勾（小撮）或托勾（大撮）([维基百科][1])  |
| `RH_DA_YUAN`   | 打圆  | 先急后缓，共得六声 ([维基百科][1])       |
| `RH_GUN`       | 滚   | 无名指向外拨弦，连续摘数声 ([维基百科][1])   |
| `RH_FU_BRUSH`  | 拂   | 食指向内拨弦，连续抹数声 ([维基百科][1])    |
| `RH_GUN_FU`    | 滚拂  | 滚、拂相连 ([维基百科][1])           |
| `RH_QUAN_FU`   | 全扶  | 一种复合（跨弦连抹/连勾+煞音）([维基百科][1]) |

> 这张表已经覆盖了“常见符号”层面的右手；如果你后面要纳入更细的流派细分/176指法那类，建议作为 `rt` 扩展标签去加，而不要破坏 `rh` 主枚举的稳定性。

---

## 6) 左手指法与动作枚举（把“指”与“动”拆开）

减字谱里左手部分既有“用哪根手指”（大/食/中/名/跪），也有“怎么动”（上/下/进/退/绰/注/吟/猱/掐起/带起/罨…）([维基百科][1])。我建议拆成：

* `lf`：左手指（Thumb/Index/Middle/Ring/RingKneel）
* `la[]`：左手动作数组（一个音可以同时有：按音+吟/猱；或绰/注；或掐起等）

### 6.1 左手“指”枚举（`lf`）

| `lf`         | 对应减字谱 | 含义                    |
| ------------ | ----- | --------------------- |
| `THUMB`      | 大     | 大指 ([维基百科][1])        |
| `INDEX`      | 食     | 食指 ([维基百科][1])        |
| `MIDDLE`     | 中     | 中指 ([维基百科][1])        |
| `RING`       | 名     | 无名指 ([维基百科][1])       |
| `RING_KNEEL` | 跪     | 无名指末节外侧按弦 ([维基百科][1]) |

### 6.2 左手“动”枚举（`la[]`，常见符号覆盖）

| `la` 代码        | 中文   | 含义（简述）                        |
| -------------- | ---- | ----------------------------- |
| `LA_SHANG`     | 上    | 按弦后向右移 ([维基百科][1])            |
| `LA_XIA`       | 下    | 按弦后向左移 ([维基百科][1])            |
| `LA_JIN`       | 进    | 按弦后向右移一音 ([维基百科][1])          |
| `LA_TUI`       | 退    | 按弦后向左移一音 ([维基百科][1])          |
| `LA_FU`        | 复    | 回到原位（含进复/退复可做组合）([维基百科][1])   |
| `LA_YIN_SLOW`  | 引/引上 | 按弦后向右慢移 ([维基百科][1])           |
| `LA_TANG_SLOW` | 淌/淌下 | 按弦后向左慢移 ([维基百科][1])           |
| `LA_WANGLAI`   | 往来   | 连续绰、注数次 ([维基百科][1])           |
| `LA_ZHUANG`    | 撞    | 急速小幅向上后回位 ([维基百科][1])         |
| `LA_QIAQI`     | 掐起   | 大指提起拨弦，发出名指所按音 ([维基百科][1])    |
| `LA_ZHUAQI`    | 抓起   | 大指按弦后抓起散音 ([维基百科][1])         |
| `LA_DAIQI`     | 带起   | 无名指按弦后带起散音 ([维基百科][1])        |
| `LA_YAN`       | 罨/掩  | 名指按弦后大指在上一音击按（含虚罨）([维基百科][1]) |
| `LA_TUICHU`    | 推出   | 中指向外推出散音 ([维基百科][1])          |
| `LA_BU_DONG`   | 不动   | 按弦后不动 ([维基百科][1])             |
| `LA_JIU`       | 就    | 在前一音处再拨一次 ([维基百科][1])         |
| `LA_CHUO`      | 绰    | 向右移产生上滑音 ([维基百科][1])          |
| `LA_ZHU`       | 注    | 向左移产生下滑音 ([维基百科][1])          |
| `LA_YIN`       | 吟    | 按音后左右微摆 ([维基百科][1])           |
| `LA_NAO`       | 猱    | 比吟幅度更大 ([维基百科][1])            |

（你如果想用“更抽象的 6 基本左手动作”也可以：吟、揉、绰、注、上、下这类分法在一些入门体系里常见；但工程上我更推荐直接对齐减字谱符号集合，避免流派口径差导致歧义。）

---

## 7) 左右配合技法枚举（`co[]`）

减字谱还把一些“左右手联动”作为独立符号，如分开、同声、应合、放合、掐撮等 ([维基百科][1])。

| `co` 代码        | 中文   | 含义（简述）                          |
| -------------- | ---- | ------------------------------- |
| `CO_FENKAI`    | 分开   | 右手得音后左手上移再得音并回位（常三声）([维基百科][1]) |
| `CO_TONGSHENG` | 同声   | 左手抓起/带起同时右手拨空弦得一声 ([维基百科][1])   |
| `CO_YINGHE`    | 应合   | 左手上/下以应散音 ([维基百科][1])           |
| `CO_FANGHE`    | 放合   | 内移放出散音后再按弹相邻弦高八度应和 ([维基百科][1])  |
| `CO_QIACUO`    | 掐撮声  | 在之前两弦上掐撮 ([维基百科][1])            |
| `CO_QIACUO_3`  | 掐撮三声 | 连续掩掐撮得三个音 ([维基百科][1])           |

---

## 8) 徽位/微分 `hp` 的推荐格式（保证可计算、可显示、可回写）

你最终要做“简谱→减字谱优化器”，徽位必须可比较、可算距离、可做代价函数。建议 `hp` 用**字符串**但限定语法：

* `H`：整数徽位 1–13，如 `9`
* `H.F`：徽位+十分（或常用小数表达），如 `7.6`
  现代资料里常见用类似 `6.7` 这样的小数来写徽位之间的位置（并且与“几徽几分”体系相容）([mondayisformusic.com][4])。

内部计算时把它解析成有理数即可：`hp="7.6"` → `hui=7, fen=6`。

---

## 9) 把 GuqinEvent 塞进 MusicXML 的“可解析字符串”规范

我建议用 **分号分隔 KV**，既适合手写也适合 diff：

`guqin-jzp@1;sd=AN;gs=4;hp=9;lf=RING;la=LA_YIN,LA_CHUO;rh=RH_GOU;co=;jzp=4sk(9)+...;`

落地时你就把它放到：

* `<notations><technical><other-technical>...</other-technical></technical></notations>` ([W3C][2])
* 如果需要 start/stop 跨音符（例如滚/拂的范围、或某些“泛起/泛止”样式），可以再配 `<other-notation type="start/stop">` ([W3C][6])

---

## 10) 一个最小可用的 MusicXML 例子（示意）

下面片段强调“**不追求所有软件都懂**，但保证所有软件都能**保留**这些信息；你的前端/后端能读懂就行”。

```xml
<note>
  <pitch>
    <step>D</step><octave>4</octave>
  </pitch>
  <duration>480</duration>
  <type>quarter</type>

  <notations>
    <technical>
      <!-- MusicXML 原生：弦序 -->
      <string>6</string>

      <!-- MusicXML 扩展：古琴字段串 + 可选 smufl 挂钩 -->
      <other-technical smufl="guqinJzp.gou">
        guqin-jzp@1;sd=AN;gs=6;hp=9;lf=RING;la=LA_YIN;rh=RH_GOU;jzp=6sk(9)
      </other-technical>
    </technical>
  </notations>

  <!-- 可选：简谱数字当作 UI 展示的保底层 -->
  <lyric><text>5</text></lyric>
</note>
```

`<string>` 这种元素在 MusicXML 技法层里是标准项 ([W3C][5])，而 `<other-technical>` 负责兜底所有“古琴特有信息” ([W3C][2])。

---

## 11) 渲染落点：不要自己造“Guqin-Unicode”，先对接现有减字谱编码/字体生态

你现在最稳的路线是：

1. `GuqinEvent` 里保留一个 `jzp` canonical 字符串；
2. 渲染时把 `jzp` 交给“减字谱字体/合字系统”去显示。JianZiPu 字体体系（以及一些衍生字体）就是为了解决“减字谱谱字不是通用字符集”的问题，并且支持把谱字拆组件再组合 ([nyl.io][3])。
3. 你自己只要保证 `jzp` 的语法稳定，就能换字体、换渲染器、甚至换成 SVG 拼字而不动数据结构。

另外，已经有人在做“减字谱输入、编码、显示方案”的开源工程，你可以直接借它的编码口径做 `jzp` 层的解析/生成（至少能省掉一大块“语法/解析器”工作量）([GitHub][8])。

---

[1]: https://zh.wikipedia.org/wiki/%E5%87%8F%E5%AD%97%E8%B0%B1 "减字谱 - 维基百科，自由的百科全书"
[2]: https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/other-technical/ "The <other-technical> element | MusicXML 4.0"
[3]: https://blog.nyl.io/jian-zi-pu-font/ "Guqin Part 4: Jian Zi Pu Font (减字谱)"
[4]: https://www.mondayisformusic.com/basics/reading-tablature "Monday is for Music - Reading Tablature"
[5]: https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/string/?utm_source=chatgpt.com "The <string> element | MusicXML 4.0"
[6]: https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/other-notation/ "The <other-notation> element | MusicXML 4.0"
[7]: https://www.w3.org/2021/06/musicxml40/musicxml-reference/data-types/clef-sign/?utm_source=chatgpt.com "clef-sign data type | MusicXML 4.0"
[8]: https://github.com/alephpi/jianzipu?utm_source=chatgpt.com "alephpi/jianzipu - 减字谱输入、编码、显示方案"
