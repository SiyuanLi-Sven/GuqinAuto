import Link from "next/link";
import { PageShell } from "@/components/app/page-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export default function NotFound() {
  return (
    <PageShell title="页面不存在" subtitle="路径可能已变更，或该功能尚未实现。">
      <Card>
        <div className="text-sm font-semibold">404</div>
        <div className="mt-2 text-sm text-muted">
          你可以返回项目页，或进入编辑器骨架查看整体布局。
        </div>
        <div className="mt-4 flex items-center gap-2">
          <Link href="/">
            <Button>返回项目</Button>
          </Link>
          <Link href="/editor">
            <Button variant="secondary">打开编辑器</Button>
          </Link>
        </div>
      </Card>
    </PageShell>
  );
}

