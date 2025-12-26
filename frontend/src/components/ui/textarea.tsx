"use client";

import { cn } from "@/lib/cn";

export function Textarea(
  props: React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
    ariaLabel?: string;
  }
) {
  const { ariaLabel, ...rest } = props;
  return (
    <textarea
      {...rest}
      aria-label={ariaLabel}
      className={cn(
        "w-full resize-none rounded-xl border border-border bg-panel2 p-3 text-sm text-text outline-none placeholder:text-muted/70 focus:border-primary/60",
        props.className
      )}
    />
  );
}
