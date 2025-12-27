"use client";

/**
 * MusicXML → “综合双谱视图”解析器（前端本地）。
 *
 * 目标：
 * - 用于工具页/调试：把一个 MusicXML 文件直接解析成“上简谱、下减字谱”的轻量视图。
 * - 不依赖后端，不做任何写回。
 *
 * 约束（学术级：正确地失败 + 显式提示）：
 * - 如果缺少 XML 结构（<part>/<measure> 等）则抛错。
 * - 如果缺少 GuqinLink/GuqinJZP 的 eid 对齐信息，则降级为“顺序事件”（显式提示 warning）。
 *
 * 注意：
 * - 这里不解析 GuqinJZP 的结构化 KV（那是后端真源校验职责）；只读取 staff1/staff2 的 lyric 文本作为显示层。
 */

import type { ProjectScoreView } from "@/components/score/dual-score-view";

export type ParseDualViewOptions = {
  projectId?: string;
  revision?: string;
};

export type ParseDualViewResult = {
  view: ProjectScoreView;
  warnings: string[];
};

function getText(el: Element | undefined | null): string | null {
  const t = el?.textContent?.trim();
  return t ? t : null;
}

function findLyricText(note: Element, placement: "above" | "below"): string | null {
  const lyrics = Array.from(note.getElementsByTagName("lyric"));
  const target = lyrics.find((l) => l.getAttribute("placement") === placement);
  return getText(target?.getElementsByTagName("text")[0] ?? null);
}

function findOtherTechnical(note: Element): string | null {
  const other = note.getElementsByTagName("other-technical")[0];
  return getText(other);
}

function parseEidFromOtherTechnical(text: string | null): string | null {
  if (!text) return null;
  return /(?:^|;)eid=([^;]+)/.exec(text)?.[1] ?? null;
}

export function parseMusicXmlToDualView(xml: string, opts: ParseDualViewOptions = {}): ParseDualViewResult {
  const warnings: string[] = [];
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  const parserError = doc.getElementsByTagName("parsererror")[0];
  if (parserError) {
    throw new Error("MusicXML XML 解析失败（parsererror）");
  }

  const part = doc.getElementsByTagName("part")[0];
  if (!part) throw new Error("MusicXML 缺少 <part>");

  const measures = Array.from(part.getElementsByTagName("measure"));
  const outMeasures: ProjectScoreView["measures"] = [];

  let sawAnyEid = false;
  let syntheticEidSeq = 0;
  const nextSyntheticEid = () => {
    syntheticEidSeq += 1;
    return `L${String(syntheticEidSeq).padStart(6, "0")}`;
  };

  let curDivisions: number | null = null;
  let curTime: { beats: number; beat_type: number } | null = null;

  for (const m of measures) {
    const mNumber = m.getAttribute("number") ?? "";
    const notes = Array.from(m.getElementsByTagName("note"));

    const attr = Array.from(m.getElementsByTagName("attributes"))[0] ?? null;
    if (attr) {
      const divText = getText(attr.getElementsByTagName("divisions")[0] ?? null);
      if (divText) {
        const dv = Number.parseInt(divText, 10);
        if (Number.isFinite(dv) && dv > 0) curDivisions = dv;
      }
      const beatsText = getText(attr.getElementsByTagName("beats")[0] ?? null);
      const beatTypeText = getText(attr.getElementsByTagName("beat-type")[0] ?? null);
      if (beatsText && beatTypeText) {
        const b = Number.parseInt(beatsText, 10);
        const bt = Number.parseInt(beatTypeText, 10);
        if (Number.isFinite(b) && Number.isFinite(bt) && b > 0 && bt > 0) {
          curTime = { beats: b, beat_type: bt };
        }
      }
    }

    const staff1Notes = notes.filter(
      (n) => n.getElementsByTagName("staff")[0]?.textContent?.trim() === "1"
    );
    const staff2Notes = notes.filter(
      (n) => n.getElementsByTagName("staff")[0]?.textContent?.trim() === "2"
    );

    // staff2: eid -> note
    const staff2ByEid = new Map<string, Element>();
    for (const n of staff2Notes) {
      const eid = parseEidFromOtherTechnical(findOtherTechnical(n));
      if (!eid) continue;
      sawAnyEid = true;
      staff2ByEid.set(eid, n);
    }

    // staff1: group contiguous notes by eid（chord/多音事件会连续出现）
    const events: Array<{ eid: string; duration: number; jianpu_text: string | null; jzp_text: string }> = [];
    let currentEid: string | null = null;
    let group: Element[] = [];

    function flush() {
      if (!currentEid) return;
      const first = group[0];
      const jianpuText = findLyricText(first, "above");
      const durText = getText(first.getElementsByTagName("duration")[0] ?? null);
      const duration = durText ? Number.parseInt(durText, 10) : 0;

      const staff2 = staff2ByEid.get(currentEid);
      const jzpText = (staff2 ? findLyricText(staff2, "below") : null) ?? "—";
      events.push({ eid: currentEid, duration: Number.isFinite(duration) ? duration : 0, jianpu_text: jianpuText, jzp_text: jzpText });
    }

    for (const n of staff1Notes) {
      const eid = parseEidFromOtherTechnical(findOtherTechnical(n));
      const resolvedEid = eid ?? nextSyntheticEid();
      if (eid) sawAnyEid = true;

      if (currentEid === null) {
        currentEid = resolvedEid;
        group = [n];
      } else if (resolvedEid === currentEid) {
        group.push(n);
      } else {
        flush();
        currentEid = resolvedEid;
        group = [n];
      }
    }
    flush();

    // 若完全没有 staff1 eid，也没有 staff2 eid：提示这是“非 GuqinAuto profile”的纯查看模式
    if (!staff1Notes.length && !staff2Notes.length) {
      continue;
    }

    outMeasures.push({
      number: mNumber,
      divisions: curDivisions,
      time: curTime,
      events: events.map((e) => ({
        eid: e.eid,
        duration: e.duration,
        jzp_text: e.jzp_text,
        jianpu_text: e.jianpu_text,
      })),
    });
  }

  if (!sawAnyEid) {
    warnings.push("未发现 GuqinLink/GuqinJZP 的 eid 字段：综合视图已降级为顺序事件（仅用于阅读）。");
  }

  return {
    view: {
      project_id: opts.projectId ?? "local",
      revision: opts.revision ?? "local",
      measures: outMeasures,
    },
    warnings,
  };
}
