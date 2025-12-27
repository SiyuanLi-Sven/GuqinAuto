"use client";

/**
 * 把一个“多 staff 的 MusicXML”裁剪为“仅 staff1”，用于 OSMD 只渲染上方五线谱。
 *
 * 背景：
 * - 我们的 Guqin-MusicXML Profile 把 staff2 用作“减字谱真值容器”（GuqinJZP），OSMD 会把它当作 TAB staff 画出来。
 * - 但在阅读工具里，我们更希望：OSMD 只画 staff1（音高+节奏），减字谱由我们自己的综合视图渲染在下方。
 *
 * 约束：
 * - 这是阅读工具的“显示层变换”，不改变真源；不保证对任意复杂 MusicXML 都 100% 等价。
 * - 对本项目 Profile 形态（staff2 通过 <backup> 回到小节起点，然后写一条并行 staff2 事件流）是稳定可用的。
 */

function getText(el: Element | null): string | null {
  const t = el?.textContent?.trim();
  return t ? t : null;
}

function getNoteStaff(note: Element): string | null {
  return getText(note.getElementsByTagName("staff")[0] ?? null);
}

function elementChildren(parent: Element): Element[] {
  return Array.from(parent.childNodes).filter((n): n is Element => n.nodeType === Node.ELEMENT_NODE);
}

function removeChildren(parent: Element, shouldRemove: (el: Element) => boolean) {
  const children = elementChildren(parent);
  for (const ch of children) {
    if (shouldRemove(ch)) parent.removeChild(ch);
  }
}

function shouldRemoveBackupUsedForStaff2(measure: Element, backupEl: Element): boolean {
  // 策略：从 backup 的下一个 sibling 开始往后看，直到下一个 backup（或小节结束）
  // 若期间出现任意 staff=2 的 note，则认为该 backup 是为 staff2 服务的，应移除。
  const siblings = elementChildren(measure);
  const idx = siblings.indexOf(backupEl);
  if (idx < 0) return false;
  for (let i = idx + 1; i < siblings.length; i += 1) {
    const el = siblings[i];
    if (el.tagName === "backup") break;
    if (el.tagName !== "note") continue;
    if (getNoteStaff(el) === "2") return true;
  }
  return false;
}

export function stripMusicXmlToStaff1(xml: string): string {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  const parserError = doc.getElementsByTagName("parsererror")[0];
  if (parserError) throw new Error("MusicXML XML 解析失败（parsererror）");

  const parts = Array.from(doc.getElementsByTagName("part"));
  for (const part of parts) {
    const measures = Array.from(part.getElementsByTagName("measure"));
    for (const m of measures) {
      const attr = m.getElementsByTagName("attributes")[0] ?? null;
      if (attr) {
        const staves = attr.getElementsByTagName("staves")[0] ?? null;
        if (staves) staves.textContent = "1";

        removeChildren(attr, (el) => {
          if (el.tagName === "clef" && el.getAttribute("number") === "2") return true;
          if (el.tagName === "staff-details" && el.getAttribute("number") === "2") return true;
          return false;
        });
      }

      // 移除 staff2 的 note；并移除“用于 staff2 的 backup”
      const children = elementChildren(m);
      for (const ch of children) {
        if (ch.tagName === "note") {
          if (getNoteStaff(ch) === "2") m.removeChild(ch);
          continue;
        }
        if (ch.tagName === "backup") {
          if (shouldRemoveBackupUsedForStaff2(m, ch)) m.removeChild(ch);
        }
      }
    }
  }

  return new XMLSerializer().serializeToString(doc);
}

