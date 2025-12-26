import { PageShell } from "@/components/app/page-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import Link from "next/link";

const demoProjects = [
  {
    id: "demo-001",
    name: "示例工程：秋风词",
    meta: "上次修改：刚刚 · 定弦：正调",
    status: "草稿",
  },
  {
    id: "demo-002",
    name: "示例工程：流水（片段）",
    meta: "上次修改：2 天前 · 定弦：慢三",
    status: "可导出",
  },
];

export default function HomePage() {
  return (
    <PageShell
      title="项目"
      subtitle="管理工程、导入简谱、进入编辑器。这里先提供精致的骨架与信息架构占位。"
      actions={
        <div className="flex items-center gap-2">
          <Link href="/import">
            <Button>导入简谱</Button>
          </Link>
          <Button variant="secondary">新建空白工程</Button>
        </div>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {demoProjects.map((p) => (
          <Card key={p.id} className="group">
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-1">
                <div className="text-sm font-semibold tracking-tight">
                  {p.name}
                </div>
                <div className="text-xs text-muted">{p.meta}</div>
              </div>
              <Badge>{p.status}</Badge>
            </div>
            <div className="mt-4 flex items-center gap-2">
              <Link href={`/editor?projectId=${encodeURIComponent(p.id)}`}>
                <Button size="sm">打开编辑器</Button>
              </Link>
            </div>
            <div className="mt-3 text-xs text-muted">
              说明：真实工程列表与后端API对接后替换。
            </div>
          </Card>
        ))}
      </div>
    </PageShell>
  );
}
