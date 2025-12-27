"use client";

import { cn } from "@/lib/cn";

export type ProjectScoreView = {
  project_id: string;
  revision: string;
  measures: Array<{
    number: string;
    events: Array<{
      eid: string;
      duration: number;
      jzp_text: string;
      jianpu_text: string | null;
    }>;
  }>;
};

export function DualScoreView(props: { score: ProjectScoreView; className?: string }) {
  const score = props.score;
  return (
    <div className={cn("space-y-3", props.className)}>
      {score.measures.map((m) => (
        <div key={m.number} className="rounded-xl border border-border bg-panel p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold text-muted">
              小节 {m.number || "?"}
            </div>
            <div className="text-[11px] text-muted">
              events: {m.events.length} · rev:{" "}
              <span className="font-mono">{score.revision}</span>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            {m.events.map((e) => (
              <EventCell key={e.eid} e={e} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function EventCell(props: {
  e: { eid: string; jianpu_text: string | null; jzp_text: string };
}) {
  const e = props.e;
  return (
    <div className="group w-[92px] rounded-xl border border-border bg-panel2 p-2">
      <div className="flex items-start justify-between gap-2">
        <div className="text-[10px] font-mono text-muted">{e.eid}</div>
      </div>
      <div className="mt-2 rounded-lg border border-border bg-panel p-2">
        <div className="text-[10px] font-medium text-muted">简谱</div>
        <div className="mt-1 text-lg font-semibold leading-none tracking-tight">
          {e.jianpu_text ?? "—"}
        </div>
      </div>
      <div className="mt-2 rounded-lg border border-border bg-panel p-2">
        <div className="text-[10px] font-medium text-muted">减字谱</div>
        <div className="mt-1 text-sm font-medium leading-snug">{e.jzp_text}</div>
      </div>
    </div>
  );
}

