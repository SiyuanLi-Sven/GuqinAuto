"use client";

import { cn } from "@/lib/cn";

export type ProjectScoreView = {
  project_id: string;
  revision: string;
  measures: Array<{
    number: string;
    divisions: number | null;
    time: { beats: number; beat_type: number } | null;
    events: Array<{
      eid: string;
      duration: number;
      jzp_text: string;
      jianpu_text: string | null;
      staff2_kv?: Record<string, string>;
      staff1_notes?: Array<{
        slot?: string | null;
        is_rest?: boolean;
        pitch?: { step?: string; alter?: number; octave?: number } | null;
      }>;
    }>;
  }>;
};

export function DualScoreView(props: {
  score: ProjectScoreView;
  className?: string;
  showJianpu?: boolean;
  showJzp?: boolean;
  selectedEid?: string | null;
  onSelectEid?: (eid: string) => void;
}) {
  const score = props.score;
  const showJianpu = props.showJianpu ?? true;
  const showJzp = props.showJzp ?? true;
  return (
    <div className={cn("space-y-3", props.className)}>
      {score.measures.map((m) => (
        <div key={m.number} className="rounded-xl border border-border bg-panel p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold text-muted">
              小节 {m.number || "?"}
            </div>
            <div className="text-[11px] text-muted">
              {m.time ? `${m.time.beats}/${m.time.beat_type}` : "—"} ·{" "}
              {m.divisions != null ? `div=${m.divisions}` : "div=—"} · events:{" "}
              {m.events.length} · rev:{" "}
              <span className="font-mono">{score.revision}</span>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            {m.events.map((e) => (
              <EventCell
                key={e.eid}
                e={e}
                divisions={m.divisions}
                time={m.time}
                showJianpu={showJianpu}
                showJzp={showJzp}
                selected={props.selectedEid === e.eid}
                onSelectEid={props.onSelectEid}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function EventCell(props: {
  e: {
    eid: string;
    jianpu_text: string | null;
    jzp_text: string;
    duration: number;
    staff2_kv?: Record<string, string>;
  };
  divisions: number | null;
  time: { beats: number; beat_type: number } | null;
  showJianpu: boolean;
  showJzp: boolean;
  selected: boolean;
  onSelectEid?: (eid: string) => void;
}) {
  const e = props.e;
  const rhythm = useJianpuRhythm(e.duration, props.divisions);
  const truth = summarizeGuqinTruth(e.staff2_kv);
  return (
    <button
      type="button"
      className={cn(
        "group w-[112px] rounded-xl border bg-panel2 p-2 text-left transition",
        props.selected ? "border-primary/60 ring-2 ring-primary/20" : "border-border hover:border-primary/40"
      )}
      onClick={() => props.onSelectEid?.(e.eid)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="text-[10px] font-mono text-muted">{e.eid}</div>
        <div className="text-[10px] text-muted">{rhythm.label}</div>
      </div>
      {props.showJianpu ? (
        <div className="mt-2 rounded-lg border border-border bg-panel p-2">
          <div className="text-[10px] font-medium text-muted">简谱</div>
          <div className="mt-1 flex items-end justify-center gap-1">
            <div className="text-2xl font-semibold leading-none tracking-tight">
              {e.jianpu_text ?? "—"}
            </div>
            {rhythm.dot ? (
              <div className="text-xl font-semibold leading-none">·</div>
            ) : null}
            {rhythm.dashCount > 0 ? (
              <div className="ml-1 flex items-center gap-1">
                {Array.from({ length: rhythm.dashCount }).map((_, i) => (
                  <div key={i} className="h-[2px] w-3 rounded bg-muted/60" />
                ))}
              </div>
            ) : null}
          </div>
          {rhythm.underlineCount > 0 ? (
            <div className="mt-1 flex items-center justify-center">
              <div className="flex flex-col items-center gap-[2px]">
                {Array.from({ length: rhythm.underlineCount }).map((_, i) => (
                  <div key={i} className="h-[2px] w-8 rounded bg-muted/70" />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {props.showJzp ? (
        <div className={cn("rounded-lg border border-border bg-panel p-2", props.showJianpu ? "mt-2" : "mt-2")}>
          <div className="text-[10px] font-medium text-muted">减字谱</div>
          <div className="mt-1 text-sm font-medium leading-snug">{e.jzp_text}</div>
          {truth ? (
            <div className="mt-2 text-[10px] leading-snug text-muted whitespace-pre-wrap">
              真值：{truth}
            </div>
          ) : null}
        </div>
      ) : null}
    </button>
  );
}

function summarizeGuqinTruth(kv: Record<string, string> | undefined): string | null {
  if (!kv) return null;
  const form = kv.form;
  if (form !== "simple" && form !== "complex") return null;

  const fmt = (v: string | undefined) => {
    if (v == null) return "—";
    const n = Number(v);
    if (Number.isFinite(n)) return String(Math.round(n * 1000) / 1000);
    return v;
  };

  if (form === "simple") {
    const sound = kv.sound;
    const hasV03 =
      sound != null ||
      kv.pos_ratio != null ||
      kv.harmonic_n != null ||
      kv.harmonic_k != null ||
      Object.keys(kv).some((k) => /^pos_ratio_[1-7]$/.test(k));
    if (!hasV03) return null;

    const xian = kv.xian ?? "—";
    if (sound === "open") return `open · xian=${xian}`;
    if (sound === "pressed") {
      const pr = kv.pos_ratio;
      const prs = Object.entries(kv)
        .filter(([k]) => /^pos_ratio_[1-7]$/.test(k))
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => `${k}=${fmt(v)}`);
      return prs.length ? `pressed · xian=${xian} · ${prs.join(" · ")}` : `pressed · xian=${xian} · pos_ratio=${fmt(pr)}`;
    }
    if (sound === "harmonic") {
      const hn = kv.harmonic_n;
      const hk = kv.harmonic_k;
      const pr = kv.pos_ratio;
      const extra = [
        hn != null ? `n=${fmt(hn)}` : null,
        hk != null ? `k=${fmt(hk)}` : null,
        pr != null ? `pos_ratio=${fmt(pr)}` : null,
      ].filter(Boolean);
      return `harmonic · xian=${xian}${extra.length ? " · " + extra.join(" · ") : ""}`;
    }
    return `sound=${sound ?? "—"} · xian=${xian}`;
  }

  // complex
  const hasV03 =
    kv.l_sound != null ||
    kv.l_pos_ratio != null ||
    kv.l_harmonic_n != null ||
    kv.r_sound != null ||
    kv.r_pos_ratio != null ||
    kv.r_harmonic_n != null;
  if (!hasV03) return null;
  const l = [
    `L:${kv.l_sound ?? "—"}`,
    kv.l_xian ? `xian=${kv.l_xian}` : null,
    kv.l_sound === "pressed" ? `pos_ratio=${fmt(kv.l_pos_ratio)}` : null,
    kv.l_sound === "harmonic" ? `n=${fmt(kv.l_harmonic_n)}` : null,
  ].filter(Boolean);
  const r = [
    `R:${kv.r_sound ?? "—"}`,
    kv.r_xian ? `xian=${kv.r_xian}` : null,
    kv.r_sound === "pressed" ? `pos_ratio=${fmt(kv.r_pos_ratio)}` : null,
    kv.r_sound === "harmonic" ? `n=${fmt(kv.r_harmonic_n)}` : null,
  ].filter(Boolean);
  return `${l.join(" · ")}\n${r.join(" · ")}`;
}

function useJianpuRhythm(durationDivisions: number, divisionsPerQuarter: number | null): {
  underlineCount: number;
  dashCount: number;
  dot: boolean;
  label: string;
} {
  const dur = Number.isFinite(durationDivisions) ? Math.max(0, durationDivisions) : 0;
  const div = divisionsPerQuarter ?? null;
  if (!div || div <= 0 || dur <= 0) {
    return { underlineCount: 0, dashCount: 0, dot: false, label: `dur=${dur}` };
  }

  const ratio = dur / div; // quarter=1
  const eps = 1e-6;

  type Base = { base: number; dot: boolean };
  const candidates: Base[] = [];
  for (let n = -6; n <= 4; n += 1) {
    const base = 2 ** n;
    candidates.push({ base, dot: false });
    candidates.push({ base: base * 1.5, dot: true });
  }
  let best: Base | null = null;
  let bestErr = Number.POSITIVE_INFINITY;
  for (const c of candidates) {
    const err = Math.abs(c.base - ratio);
    if (err < bestErr) {
      bestErr = err;
      best = c;
    }
  }
  if (!best || bestErr > 0.01 + eps) {
    // 不属于常见时值（比如连音线合并后的奇怪值），直接展示数值
    return { underlineCount: 0, dashCount: 0, dot: false, label: `dur=${dur}` };
  }

  const dotted = best.dot;
  const base = dotted ? best.base / 1.5 : best.base;

  let underlineCount = 0;
  let dashCount = 0;
  if (base >= 1) {
    dashCount = Math.max(0, Math.round(base - 1));
  } else {
    underlineCount = Math.max(0, Math.round(Math.log2(1 / base)));
  }

  const label = dotted ? `${base}q.` : `${base}q`;
  return { underlineCount, dashCount, dot: dotted, label };
}
