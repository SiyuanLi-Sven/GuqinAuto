import { cn } from "@/lib/cn";

export function Card(props: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-border bg-panel p-4 shadow-soft",
        props.className
      )}
    >
      {props.children}
    </div>
  );
}

