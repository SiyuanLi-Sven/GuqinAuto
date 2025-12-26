"""
GuqinAuto 的“古琴减字谱 + 简谱”内部数据结构与工具。

定位：
- 本目录放置 GuqinAuto 自己实现/维护的核心逻辑，禁止运行期依赖 `references` 目录。
- 当前阶段主要提供：减字谱读法（jianzipu text）token 集合与最小解析器，
  用于 Profile 文档/示例的可验证闭环（结构化字段 → jzp_text → 可解析）。
"""
