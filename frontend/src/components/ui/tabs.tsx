"use client";

import { cn } from "@/lib/cn";

export function Tabs<T extends string>(props: {
  items: readonly T[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex w-full items-center gap-1 rounded-xl border border-border bg-panel2 p-1",
        props.className
      )}
    >
      {props.items.map((it) => {
        const active = it === props.value;
        return (
          <button
            key={it}
            type="button"
            onClick={() => props.onChange(it)}
            className={cn(
              "flex-1 rounded-lg px-2 py-2 text-[11px] font-medium transition",
              active
                ? "bg-panel text-text shadow-soft"
                : "text-muted hover:bg-panel/70 hover:text-text"
            )}
          >
            {it}
          </button>
        );
      })}
    </div>
  );
}

