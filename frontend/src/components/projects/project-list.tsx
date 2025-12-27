"use client";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { http, HttpError } from "@/lib/http";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type ProjectMeta = {
  project_id: string;
  name: string;
  created_at: string;
  updated_at?: string;
  current_revision: string;
};

function formatTime(ts: string) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString();
}

export function ProjectList() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectMeta[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const sorted = useMemo(() => {
    if (!projects) return null;
    const key = (p: ProjectMeta) => String(p.updated_at ?? p.created_at ?? "");
    return [...projects].sort((a, b) => key(b).localeCompare(key(a)));
  }, [projects]);

  async function reload() {
    setError(null);
    try {
      const data = await http<ProjectMeta[]>("/api/backend/projects");
      setProjects(data);
    } catch (err) {
      const e = err as HttpError;
      setProjects(null);
      setError(
        e?.name === "HttpError"
          ? `后端请求失败：${e.status} ${e.url}\n${e.bodyText ?? ""}`
          : `后端请求失败：${err instanceof Error ? err.message : String(err)}`
      );
    }
  }

  async function createDemo() {
    setError(null);
    setBusy(true);
    try {
      const now = new Date();
      const name = `示例工程 ${now.toLocaleString()}`;
      const meta = await http<ProjectMeta>("/api/backend/projects", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name,
          example_filename: "guqin_jzp_profile_v0.2_showcase.musicxml",
        }),
      });
      await reload();
      router.push(`/editor?projectId=${encodeURIComponent(meta.project_id)}`);
    } catch (err) {
      const e = err as HttpError;
      setError(
        e?.name === "HttpError"
          ? `创建失败：${e.status} ${e.url}\n${e.bodyText ?? ""}`
          : `创建失败：${err instanceof Error ? err.message : String(err)}`
      );
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-semibold">工程列表</div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => void reload()} disabled={busy}>
            刷新
          </Button>
          <Button onClick={() => void createDemo()} disabled={busy}>
            新建示例工程
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-danger/30 bg-panel2 p-3 text-xs text-muted whitespace-pre-wrap">
          {error}
          <div className="mt-2">
            提示：先启动后端 `python backend/run_server.py --reload`（7130），再刷新。
          </div>
        </div>
      ) : null}

      {sorted === null ? (
        <Card>
          <div className="text-sm font-semibold">正在加载…</div>
          <div className="mt-2 text-xs text-muted">从后端拉取 workspace 工程列表。</div>
        </Card>
      ) : sorted.length === 0 ? (
        <Card>
          <div className="text-sm font-semibold">暂无工程</div>
          <div className="mt-2 text-xs text-muted">
            点击“新建示例工程”，或直接进入编辑器查看内置示例。
          </div>
          <div className="mt-4 flex items-center gap-2">
            <Link href="/editor">
              <Button variant="secondary">打开编辑器（内置示例）</Button>
            </Link>
          </div>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sorted.map((p) => (
            <Card key={p.project_id} className="group">
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="text-sm font-semibold tracking-tight">{p.name}</div>
                  <div className="text-xs text-muted">
                    更新：{formatTime(p.updated_at ?? p.created_at)}
                  </div>
                  <div className="text-[11px] text-muted">
                    id：<span className="font-mono">{p.project_id}</span>
                  </div>
                </div>
                <Badge variant="outline">{p.current_revision}</Badge>
              </div>
              <div className="mt-4 flex items-center gap-2">
                <Link href={`/editor?projectId=${encodeURIComponent(p.project_id)}`}>
                  <Button size="sm">打开编辑器</Button>
                </Link>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
