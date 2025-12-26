import { PageShell } from "@/components/app/page-shell";
import { Card } from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <PageShell
      title="设置"
      subtitle="默认定弦、音源映射、渲染质量与缓存策略（占位页）。"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Card>
          <div className="text-sm font-semibold">默认参数</div>
          <div className="mt-2 text-xs text-muted">
            默认定弦、速度、拍号等（后续与导入页联动）。
          </div>
        </Card>
        <Card>
          <div className="text-sm font-semibold">试听与音源</div>
          <div className="mt-2 text-xs text-muted">
            选择音源映射、播放延迟、缓存策略。
          </div>
        </Card>
      </div>
    </PageShell>
  );
}

