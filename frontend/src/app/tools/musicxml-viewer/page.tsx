"use client";

import { useMemo, useRef, useState } from "react";
import { TopNav } from "@/components/app/top-nav";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { DualScoreView } from "@/components/score/dual-score-view";
import { OsmdViewer } from "@/components/score/osmd-viewer";
import { parseMusicXmlToDualView } from "@/lib/musicxml/parse-dual-view";
import { stripMusicXmlToStaff1 } from "@/lib/musicxml/strip-to-staff1";

type ViewMode = "综合视图" | "OSMD";
type OsmdStaffMode = "原始(含TAB)" | "仅staff1(隐藏TAB)";

export default function MusicXmlViewerToolPage() {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [mode, setMode] = useState<ViewMode>("综合视图");
  const [osmdStaffMode, setOsmdStaffMode] = useState<OsmdStaffMode>("仅staff1(隐藏TAB)");
  const [filename, setFilename] = useState<string | null>(null);
  const [musicxml, setMusicxml] = useState<string>("");

  const parsed = useMemo((): { view: ReturnType<typeof parseMusicXmlToDualView>["view"] | null; warnings: string[]; error: string | null } => {
    if (!musicxml) return { view: null, warnings: [], error: null };
    try {
      const r = parseMusicXmlToDualView(musicxml, { projectId: "local", revision: "local" });
      return { view: r.view, warnings: r.warnings, error: null };
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      return { view: null, warnings: [], error: msg };
    }
  }, [musicxml]);

  const osmdXml = useMemo(() => {
    if (!musicxml) return "";
    if (osmdStaffMode === "原始(含TAB)") return musicxml;
    try {
      return stripMusicXmlToStaff1(musicxml);
    } catch {
      // 若裁剪失败，宁可让 OSMD 去渲染原始 XML，同时由左侧提示里看到解析警告即可。
      return musicxml;
    }
  }, [musicxml, osmdStaffMode]);

  async function loadFile(f: File) {
    setFilename(f.name);
    const text = await f.text();
    setMusicxml(text);
  }

  return (
    <div className="min-h-screen">
      <TopNav />
      <div className="mx-auto w-full max-w-[1400px] px-4 pb-10 pt-6 sm:px-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="text-lg font-semibold tracking-tight">MusicXML 阅读工具</div>
            <div className="mt-1 text-sm text-muted">
              拖拽一个 `.musicxml/.xml` 文件即可本地渲染：OSMD（五线谱） + 综合视图（简谱/减字谱文本）。
            </div>
          </div>
          <div className="w-full max-w-[320px]">
            <Tabs<ViewMode> items={["综合视图", "OSMD"]} value={mode} onChange={setMode} />
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <Card>
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-semibold">文件</div>
                <div className="flex items-center gap-2">
                  <input
                    ref={inputRef}
                    type="file"
                    accept=".musicxml,.xml"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void loadFile(f);
                      e.currentTarget.value = "";
                    }}
                  />
                  <Button size="sm" variant="secondary" onClick={() => inputRef.current?.click()}>
                    选择文件
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setFilename(null);
                      setMusicxml("");
                    }}
                    disabled={!musicxml}
                  >
                    清空
                  </Button>
                </div>
              </div>

              <div
                className="mt-4 rounded-2xl border border-dashed border-border bg-panel2 p-4"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const f = e.dataTransfer.files?.[0];
                  if (f) void loadFile(f);
                }}
              >
                <div className="text-sm font-medium">拖拽文件到这里</div>
                <div className="mt-1 text-xs text-muted">
                  仅本地解析，不上传到后端；适合快速阅读 MusicXML。
                </div>
                <div className="mt-3 text-xs text-muted">
                  当前：{filename ?? "（未选择）"}
                </div>
              </div>

              {parsed.error ? (
                <div className="mt-4 rounded-xl border border-danger/30 bg-panel2 p-3 text-xs text-muted whitespace-pre-wrap">
                  解析失败：{parsed.error}
                </div>
              ) : null}
              {parsed.warnings.length ? (
                <div className="mt-4 rounded-xl border border-border bg-panel2 p-3 text-xs text-muted">
                  <div className="text-xs font-semibold text-text">提示</div>
                  <ul className="mt-2 list-disc space-y-1 pl-5">
                    {parsed.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </Card>

            <Card className="mt-3">
              <div className="text-sm font-semibold">说明</div>
              <div className="mt-2 text-xs text-muted">
                综合视图读取：
                <div className="mt-1">
                  - 简谱：`lyric placement=&quot;above&quot;`
                </div>
                <div>
                  - 减字谱：`lyric placement=&quot;below&quot;`（如“散挑三”）
                </div>
                <div className="mt-2">
                  若缺少 `eid=` 对齐信息（GuqinLink/GuqinJZP），综合视图会降级为“顺序事件”（仅用于阅读）。
                </div>
                <div className="mt-2">
                  OSMD 默认仅渲染 staff1（隐藏 TAB staff）；减字谱仍由综合视图渲染在下方（不依赖 OSMD）。
                </div>
              </div>
            </Card>
          </div>

          <div className="lg:col-span-8">
            <Card>
              {!musicxml ? (
                <div className="rounded-xl border border-border bg-panel2 p-4 text-sm text-muted">
                  先拖入一个 MusicXML 文件。
                </div>
              ) : mode === "OSMD" ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-xs text-muted">OSMD 只负责 staff1 五线谱渲染。</div>
                    <div className="w-full max-w-[260px]">
                      <Tabs<OsmdStaffMode>
                        items={["仅staff1(隐藏TAB)", "原始(含TAB)"]}
                        value={osmdStaffMode}
                        onChange={setOsmdStaffMode}
                      />
                    </div>
                  </div>
                  <OsmdViewer musicxml={osmdXml} className="rounded-xl" />
                  {parsed.view ? (
                    <div className="rounded-xl border border-border bg-panel2 p-3">
                      <div className="text-xs font-semibold text-muted">减字谱（文本）</div>
                      <div className="mt-2">
                        <DualScoreView score={parsed.view} showJianpu={false} showJzp={true} />
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : parsed.view ? (
                <DualScoreView score={parsed.view} />
              ) : (
                <div className="rounded-xl border border-border bg-panel2 p-4 text-sm text-muted">
                  综合视图解析失败（见左侧错误信息）。
                </div>
              )}
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
