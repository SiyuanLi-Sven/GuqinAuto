"use client";

import { cn } from "@/lib/cn";

export function Input(
  props: React.InputHTMLAttributes<HTMLInputElement> & { label?: string }
) {
  const { label, ...rest } = props;
  return (
    <label className="block">
      {label ? (
        <div className="mb-1 text-xs font-medium text-muted">{label}</div>
      ) : null}
      <input
        {...rest}
        className={cn(
          "h-10 w-full rounded-xl border border-border bg-panel2 px-3 text-sm text-text outline-none ring-0 placeholder:text-muted/70 focus:border-primary/60",
          props.className
        )}
      />
    </label>
  );
}

