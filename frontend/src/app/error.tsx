"use client";

import { PageShell } from "@/components/app/page-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useEffect } from "react";

export default function GlobalError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // 这里保留最小信息：避免在UI层吞掉错误，便于定位与“正确地失败”
    console.error(props.error);
  }, [props.error]);

  return (
    <PageShell title="发生错误" subtitle="前端捕获到未处理异常。">
      <Card>
        <div className="text-sm font-semibold">错误信息</div>
        <pre className="mt-3 overflow-auto rounded-xl border border-border bg-panel2 p-3 text-xs text-muted">
          {props.error.message}
          {props.error.digest ? `\nDigest: ${props.error.digest}` : ""}
        </pre>
        <div className="mt-4 flex items-center gap-2">
          <Button onClick={props.reset}>重试</Button>
          <Button
            variant="secondary"
            onClick={() => window.location.reload()}
          >
            刷新页面
          </Button>
        </div>
      </Card>
    </PageShell>
  );
}
