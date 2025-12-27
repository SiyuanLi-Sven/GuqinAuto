import Link from "next/link";
import { Badge } from "@/components/ui/badge";

const items = [
  { href: "/", label: "项目" },
  { href: "/import", label: "导入" },
  { href: "/editor", label: "编辑器" },
  { href: "/tools/musicxml-viewer", label: "工具" },
  { href: "/settings", label: "设置" },
];

export function TopNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-panel/80 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-panel2"
          >
            <span className="text-sm font-semibold tracking-tight">
              GuqinAuto
            </span>
            <Badge variant="outline">MVP</Badge>
          </Link>
          <div className="hidden items-center gap-1 sm:flex">
            {items.map((it) => (
              <Link
                key={it.href}
                href={it.href}
                className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-panel2 hover:text-text"
              >
                {it.label}
              </Link>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone="info">后端：7130</Badge>
          <Badge tone="ok">前端：7137</Badge>
        </div>
      </div>
    </header>
  );
}
