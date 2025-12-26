"use client";

import { cn } from "@/lib/cn";

export function Button(
  props: React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: "primary" | "secondary" | "ghost";
    size?: "sm" | "md";
  }
) {
  const variant = props.variant ?? "primary";
  const size = props.size ?? "md";

  const base =
    "inline-flex items-center justify-center gap-2 rounded-xl border px-3 py-2 text-sm font-medium shadow-sm transition active:translate-y-[0.5px] disabled:cursor-not-allowed disabled:opacity-50";
  const variants: Record<string, string> = {
    primary:
      "border-transparent bg-primary text-white hover:bg-primary/90 shadow-soft",
    secondary:
      "border-border bg-panel2 text-text hover:bg-panel2/80 shadow-none",
    ghost: "border-transparent bg-transparent text-muted hover:bg-panel2",
  };
  const sizes: Record<string, string> = {
    sm: "h-8 px-3 text-xs rounded-lg",
    md: "h-10 px-3",
  };

  return (
    <button
      {...props}
      className={cn(base, variants[variant], sizes[size], props.className)}
    />
  );
}

