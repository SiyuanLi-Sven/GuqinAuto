import Link from "next/link";
import { TopNav } from "@/components/app/top-nav";

export function PageShell(props: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-4 pb-10 pt-6 sm:px-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-1">
            <h1 className="text-xl font-semibold tracking-tight">
              {props.title}
            </h1>
            {props.subtitle ? (
              <p className="max-w-3xl text-sm text-muted">{props.subtitle}</p>
            ) : null}
          </div>
          {props.actions ? (
            <div className="flex items-center gap-2">{props.actions}</div>
          ) : null}
        </div>

        <div className="mt-6">{props.children}</div>

        <footer className="mt-10 border-t border-border pt-6 text-xs text-muted">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              GuqinAuto · 前端骨架（Next.js）·{" "}
              <span className="font-mono">localhost:7137</span>
            </div>
            <div className="flex items-center gap-3">
              <Link className="hover:underline" href="/settings">
                设置
              </Link>
              <a
                className="hover:underline"
                href="https://github.com/opensheetmusicdisplay/opensheetmusicdisplay"
                target="_blank"
                rel="noreferrer"
              >
                OSMD
              </a>
            </div>
          </div>
        </footer>
      </main>
    </div>
  );
}

