"use client";

import { PageShell } from "@/components/app/page-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { http, HttpError } from "@/lib/http";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

export default function ImportPage() {
  const router = useRouter();

  const [title, setTitle] = useState("未命名工程");
  const [rawJson, setRawJson] = useState(
    JSON.stringify(
      {
        note: "该 JSON 输入仅为历史占位。当前 MVP 先支持上传 MusicXML 创建工程。",
      },
      null,
      2
    )
  );
  const [fileName, setFileName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ project_id: string; current_revision: string } | null>(
    null
  );

  const parseResult = useMemo(() => {
    try {
      JSON.parse(rawJson);
      return { ok: true as const, message: "JSON 语法正确（仅占位校验）" };
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      return { ok: false as const, message: msg };
    }
  }, [rawJson]);

  async function uploadMusicXml(file: File) {
    setUploadError(null);
    setDraftError(null);
    setBusy(true);
    setCreated(null);
    try {
      const fd = new FormData();
      fd.append("file", file, file.name);
      if (title.trim()) fd.append("name", title.trim());

      const res = await fetch("/api/backend/projects/import_musicxml", {
        method: "POST",
        body: fd,
      });
      if (!res.ok) {
        const bodyText = await res.text().catch(() => "");
        throw {
          name: "HttpError",
          status: res.status,
          url: "/api/backend/projects/import_musicxml",
          bodyText,
        } satisfies HttpError;
      }
      const data = (await res.json()) as { project: { project_id: string; current_revision: string } };
      const pid = data?.project?.project_id;
      if (!pid) throw new Error("后端返回缺少 project_id");
      const rev = data?.project?.current_revision;
      if (!rev) throw new Error("后端返回缺少 current_revision");
      setCreated({ project_id: pid, current_revision: rev });
      setFileName(file.name);
    } catch (err) {
      const e = err as HttpError;
      setUploadError(
        e?.name === "HttpError"
          ? `上传失败：${e.status} ${e.url}\n${e.bodyText ?? ""}`
          : `上传失败：${err instanceof Error ? err.message : String(err)}`
      );
    } finally {
      setBusy(false);
    }
  }

  async function generateDraft() {
    if (!created) return;
    setDraftError(null);
    setBusy(true);
    try {
      const data = await http<{
        commit?: { project?: { project_id: string; current_revision: string } };
      }>(`/api/backend/projects/${encodeURIComponent(created.project_id)}/stage2`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          base_revision: created.current_revision,
          k: 1,
          apply_mode: "commit_best",
          message: "import: generate autodraft (stage2 commit_best)",
        }),
      });
      const proj = data?.commit?.project;
      if (!proj?.project_id || !proj?.current_revision) {
        throw new Error("后端返回缺少 commit.project 信息");
      }
      setCreated({ project_id: proj.project_id, current_revision: proj.current_revision });
      router.push(`/editor?projectId=${encodeURIComponent(proj.project_id)}`);
    } catch (err) {
      const e = err as HttpError;
      setDraftError(
        e?.name === "HttpError"
          ? `生成初稿失败：${e.status} ${e.url}\n${e.bodyText ?? ""}`
          : `生成初稿失败：${err instanceof Error ? err.message : String(err)}`
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell
      title="导入与参数"
      subtitle="当前 MVP：上传 MusicXML → 创建 workspace 工程 → 进入编辑器。后续再兼容其他输入格式（统一编译为 MusicXML 真源）。"
      actions={
        <div className="flex items-center gap-2">
          <Link href="/">
            <Button variant="ghost">返回项目</Button>
          </Link>
          <Button
            disabled={!created?.project_id}
            onClick={() => {
              if (!created?.project_id) return;
              router.push(`/editor?projectId=${encodeURIComponent(created.project_id)}`);
            }}
          >
            进入编辑器
          </Button>
        </div>
      }
    >
      <div className="grid gap-3 lg:grid-cols-2">
        <Card>
          <div className="text-sm font-semibold">上传 MusicXML（MVP）</div>
          <div className="mt-4 grid gap-3">
            <Input
              label="工程名称"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例如：秋风词（练习版）"
            />
          </div>

          <div className="mt-4 rounded-2xl border border-dashed border-border bg-panel2 p-4">
            <div className="text-sm font-medium">拖拽 `.musicxml/.xml` 到这里</div>
            <div className="mt-1 text-xs text-muted">
              后端会严格校验当前 Profile（GuqinLink/GuqinJZP 对齐等），不符合则直接失败（不会隐式补全）。
            </div>
            <div
              className="mt-3"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const f = e.dataTransfer.files?.[0];
                if (f) void uploadMusicXml(f);
              }}
            >
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => document.getElementById("musicxml-file-input")?.click()}
              >
                选择文件上传
              </Button>
              <input
                id="musicxml-file-input"
                type="file"
                accept=".musicxml,.xml"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void uploadMusicXml(f);
                  e.currentTarget.value = "";
                }}
              />
            </div>

            <div className="mt-3 text-xs text-muted">
              当前文件：{fileName ?? "（未选择）"} {busy ? "（上传中…）" : ""}
            </div>
          </div>

          {uploadError ? (
            <div className="mt-4 rounded-xl border border-danger/30 bg-panel2 p-3 text-xs text-muted whitespace-pre-wrap">
              {uploadError}
              <div className="mt-2">
                提示：先启动后端 `python backend/run_server.py --reload`（7130），再上传。
              </div>
            </div>
          ) : null}

          {created?.project_id ? (
            <div className="mt-4 rounded-xl border border-border bg-panel2 p-3 text-xs text-muted">
              已创建工程：<span className="font-mono">{created.project_id}</span>
              <div className="mt-2 flex items-center gap-2">
                <Button
                  size="sm"
                  onClick={() =>
                    router.push(`/editor?projectId=${encodeURIComponent(created.project_id)}`)
                  }
                >
                  打开编辑器
                </Button>
                <Button size="sm" variant="secondary" disabled={busy} onClick={() => void generateDraft()}>
                  生成初稿（Top-1）
                </Button>
                <Link href="/">
                  <Button size="sm" variant="secondary">
                    返回项目列表
                  </Button>
                </Link>
              </div>
            </div>
          ) : null}

          {draftError ? (
            <div className="mt-3 rounded-xl border border-danger/30 bg-panel2 p-3 text-xs text-muted whitespace-pre-wrap">
              {draftError}
            </div>
          ) : null}
        </Card>

        <Card className="flex flex-col">
          <div className="text-sm font-semibold">其他输入格式（占位）</div>
          <div className="mt-3 flex-1">
            <Textarea
              value={rawJson}
              onChange={(e) => setRawJson(e.target.value)}
              className="h-[440px] font-mono text-xs"
              ariaLabel="简谱JSON"
            />
          </div>
          <div className="mt-3 flex items-center justify-between">
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Badge tone={parseResult.ok ? "ok" : "danger"}>
                {parseResult.ok ? "占位 JSON 可解析" : "占位 JSON 有误"}
              </Badge>
              <span className="text-xs text-muted">{parseResult.message}</span>
            </div>
            <Link href="/tools/musicxml-viewer">
              <Button variant="ghost">打开 MusicXML 阅读工具</Button>
            </Link>
          </div>
        </Card>
      </div>
    </PageShell>
  );
}
