import { TopNav } from "@/components/app/top-nav";
import { Card } from "@/components/ui/card";

export default function Loading() {
  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-4 pb-10 pt-6 sm:px-6">
        <Card>
          <div className="text-sm font-semibold">加载中</div>
          <div className="mt-2 text-xs text-muted">
            这是一层全局占位加载态；真实数据接入后可替换为骨架屏。
          </div>
          <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-panel2">
            <div className="h-full w-2/3 animate-pulse rounded-full bg-primary/30" />
          </div>
        </Card>
      </main>
    </div>
  );
}

