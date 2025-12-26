import { cn } from "@/lib/cn";

export function Badge(props: {
  children: React.ReactNode;
  className?: string;
  variant?: "solid" | "outline";
  tone?: "neutral" | "info" | "ok" | "danger";
}) {
  const variant = props.variant ?? "solid";
  const tone = props.tone ?? "neutral";

  const toneClass =
    tone === "ok"
      ? "bg-emerald-500/12 text-emerald-600 border-emerald-500/20"
      : tone === "danger"
        ? "bg-red-500/12 text-red-600 border-red-500/20"
        : tone === "info"
          ? "bg-sky-500/12 text-sky-600 border-sky-500/20"
          : "bg-slate-500/10 text-slate-600 border-slate-500/20";

  const style =
    variant === "outline"
      ? "bg-transparent text-muted border-border"
      : toneClass;

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-1 text-[11px] font-medium leading-none",
        style,
        props.className
      )}
    >
      {props.children}
    </span>
  );
}

