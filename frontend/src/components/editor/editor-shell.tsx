"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { TopNav } from "@/components/app/top-nav";
import { OsmdViewer } from "@/components/score/osmd-viewer";
import { DualScoreView, ProjectScoreView } from "@/components/score/dual-score-view";
import { http, HttpError } from "@/lib/http";
import { useEffect, useMemo, useState } from "react";

type InspectorTab = "简谱属性" | "减字属性" | "候选与诊断" | "回放表现";
type CenterView = "综合视图" | "OSMD";

export function EditorShell(props: { projectId?: string | null }) {
  const [tab, setTab] = useState<InspectorTab>("简谱属性");
  const [centerView, setCenterView] = useState<CenterView>("综合视图");
  const [musicxml, setMusicxml] = useState<string>("");
  const [score, setScore] = useState<ProjectScoreView | null>(null);
  const [source, setSource] = useState<"builtin" | "backend">("builtin");
  const [loadError, setLoadError] = useState<string | null>(null);

  const status = useMemo(() => {
    return {
      project: "未命名工程",
      scheme: "当前方案：A",
      locked: "锁定：3 / 128",
      saved: "未保存",
      bpm: 72,
    };
  }, []);

  async function loadBuiltinExample() {
    setLoadError(null);
    setSource("builtin");
    try {
      const res = await fetch("/examples/guqin_jzp_profile_v0.2_showcase.musicxml");
      if (!res.ok) throw new Error(`加载内置示例失败：HTTP ${res.status}`);
      const xml = await res.text();
      setMusicxml(xml);
      setScore(parseMusicXmlToDualView(xml));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLoadError(msg);
    }
  }

  async function loadFromBackend() {
    setLoadError(null);
    setSource("backend");
    const projectId = props.projectId;
    if (!projectId) {
      setLoadError("缺少 projectId：请从项目页打开，或在 URL 里传 ?projectId=xxx");
      return;
    }
    try {
      const data = await http<ProjectScoreView>(
        `/api/backend/projects/${encodeURIComponent(projectId)}/score`
      );
      setScore(data);

      // OSMD 视图需要 XML：只在用户切换到 OSMD 时再拉取，避免无意义的额外请求。
      if (centerView === "OSMD") {
        const xmlData = await http<{ musicxml: string }>(
          `/api/backend/projects/${encodeURIComponent(projectId)}/musicxml`
        );
        setMusicxml(xmlData.musicxml);
      }
    } catch (err) {
      const e = err as HttpError;
      setLoadError(
        e?.name === "HttpError"
          ? `后端请求失败：${e.status} ${e.url}\n${e.bodyText ?? ""}`
          : `后端请求失败：${err instanceof Error ? err.message : String(err)}`
      );
    }
  }

  useEffect(() => {
    // 默认行为：有 projectId 就拉后端真源；否则直接加载内置示例，保证“打开编辑器就能看到谱面”。
    if (props.projectId) {
      void loadFromBackend();
    } else {
      void loadBuiltinExample();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.projectId]);

  useEffect(() => {
    // 若用户切到 OSMD 且当前源是 backend，但还没拉 XML，则补一次拉取。
    if (centerView !== "OSMD") return;
    if (source !== "backend") return;
    if (!props.projectId) return;
    if (musicxml) return;
    void (async () => {
      try {
        const xmlData = await http<{ musicxml: string }>(
          `/api/backend/projects/${encodeURIComponent(props.projectId!)}/musicxml`
        );
        setMusicxml(xmlData.musicxml);
      } catch {
        // 这里不吞错：由 loadError 主路径负责显示。
      }
    })();
  }, [centerView, source, props.projectId, musicxml]);

  return (
    <div className="min-h-screen">
      <TopNav />
      <EditorTopBar status={status} />
      <div className="mx-auto grid w-full max-w-[1400px] grid-cols-12 gap-3 px-4 pb-6 pt-3 sm:px-6">
        {/* 左侧结构栏 */}
        <aside className="col-span-12 lg:col-span-3">
          <Card className="sticky top-[8.25rem]">
            <div className="text-sm font-semibold">结构栏</div>
            <div className="mt-3 space-y-2 text-xs text-muted">
              <div>工程：{status.project}</div>
              <div>{status.scheme}</div>
              <div>{status.locked}</div>
            </div>
            <div className="mt-4 rounded-xl border border-border bg-panel2 p-3 text-xs text-muted">
              这里最终会放：段落/小节导航、方案 Top-K 切换、锁定统计与“局部再优化”入口。
            </div>
          </Card>
        </aside>

        {/* 中央谱面区 */}
        <section className="col-span-12 lg:col-span-6">
          <div className="space-y-3">
            <Card>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold">综合双谱面视图</div>
                  <div className="mt-1 text-xs text-muted">
                    每一行：上方简谱（节奏锚点）+ 下方减字谱（动作锚点），两者共享同一
                    note-id。
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant={source === "builtin" ? "secondary" : "ghost"} onClick={loadBuiltinExample}>
                    加载内置示例
                  </Button>
                  <Button size="sm" variant={source === "backend" ? "secondary" : "ghost"} onClick={loadFromBackend}>
                    从后端加载
                  </Button>
                </div>
              </div>
              <div className="mt-4 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs text-muted">
                    默认展示“综合视图”（真实需求）。OSMD 仅用于调试 MusicXML 渲染器能力。
                  </div>
                  <div className="min-w-[220px]">
                    <Tabs<CenterView>
                      items={["综合视图", "OSMD"]}
                      value={centerView}
                      onChange={setCenterView}
                    />
                  </div>
                </div>
                {loadError ? (
                  <div className="rounded-xl border border-danger/30 bg-panel2 p-3 text-xs text-muted whitespace-pre-wrap">
                    {loadError}
                  </div>
                ) : null}
                {centerView === "综合视图" ? (
                  score ? (
                    <DualScoreView score={score} />
                  ) : (
                    <div className="rounded-xl border border-border bg-panel2 p-3 text-xs text-muted">
                      还未加载谱面（score view）。请点击“加载内置示例”或“从后端加载”。
                    </div>
                  )
                ) : !musicxml ? (
                  <div className="rounded-xl border border-border bg-panel2 p-3 text-xs text-muted">
                    OSMD 视图需要 MusicXML 文本；当前尚未获取到 XML。
                  </div>
                ) : (
                  <OsmdViewer musicxml={musicxml} className="rounded-xl" />
                )}
              </div>
            </Card>

            <Card>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold">事件条（可选）</div>
                  <div className="mt-1 text-xs text-muted">
                    时间线展示滑音/吟猱曲线、技法切换、力度/音色控制（占位）
                  </div>
                </div>
                <Button size="sm" variant="secondary">
                  打开
                </Button>
              </div>
              <div className="mt-4 h-[140px] rounded-xl border border-border bg-panel2 p-3 text-xs text-muted">
                TODO：基于同一真源事件流，提供可视化调参入口。
              </div>
            </Card>
          </div>
        </section>

        {/* 右侧属性面板 */}
        <aside className="col-span-12 lg:col-span-3">
          <Card className="sticky top-[8.25rem]">
            <div className="flex items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold">Inspector</div>
                <div className="mt-1 text-xs text-muted">
                  点选音符→编辑字段→后端更新→重绘
                </div>
              </div>
              <Button size="sm" variant="ghost">
                关闭
              </Button>
            </div>

            <div className="mt-4">
              <Tabs<InspectorTab>
                items={["简谱属性", "减字属性", "候选与诊断", "回放表现"]}
                value={tab}
                onChange={setTab}
              />
            </div>

            <div className="mt-4 space-y-3">
              {tab === "简谱属性" ? (
                <InspectorCard
                  title="简谱属性（占位）"
                  body="度数/升降/八度点/时值/附点/连音线/小节位置。这里最终需要做“总时值平衡”的即时校验。"
                />
              ) : null}
              {tab === "减字属性" ? (
                <InspectorCard
                  title="减字属性（占位）"
                  body="弦号/散按泛/徽位/左右手技法/滑音吟猱参数/细粒度锁定。锁定保护 + 局部再优化是关键。"
                />
              ) : null}
              {tab === "候选与诊断" ? (
                <InspectorCard
                  title="候选与诊断（占位）"
                  body="Top-K 切换、差异摘要、不可弹/风险/风格偏离三类诊断。要可解释、可复现。"
                />
              ) : null}
              {tab === "回放表现" ? (
                <InspectorCard
                  title="回放表现（占位）"
                  body="把谱面语义映射到“能听”：滑音/吟猱强度、起止时间百分比、装饰音抢拍、泛音音色衰减等。"
                />
              ) : null}

              <div className="grid grid-cols-2 gap-2 pt-1">
                <Button size="sm">应用</Button>
                <Button size="sm" variant="secondary">
                  恢复
                </Button>
              </div>
            </div>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function EditorTopBar(props: {
  status: { project: string; scheme: string; locked: string; saved: string; bpm: number };
}) {
  return (
    <div className="sticky top-14 z-30 border-b border-border bg-panel/80 backdrop-blur">
      <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-2 px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-[220px]">
            <div className="text-sm font-semibold tracking-tight">
              {props.status.project}
            </div>
            <div className="mt-1 text-xs text-muted">
              {props.status.scheme} · {props.status.locked} · {props.status.saved}
            </div>
          </div>
          <div className="h-8 w-px bg-border/70" />
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="secondary">
              撤销
            </Button>
            <Button size="sm" variant="secondary">
              重做
            </Button>
            <Button size="sm">保存</Button>
            <Button size="sm" variant="ghost">
              导出（MusicXML/MIDI/音频）
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary">
            播放/暂停
          </Button>
          <Button size="sm" variant="ghost">
            循环段
          </Button>
          <Button size="sm" variant="ghost">
            节拍器
          </Button>
          <Button size="sm" variant="ghost">
            速度：{props.status.bpm} BPM
          </Button>
        </div>
      </div>
    </div>
  );
}

function InspectorCard(props: { title: string; body: string }) {
  return (
    <div className="rounded-xl border border-border bg-panel2 p-3">
      <div className="text-xs font-semibold">{props.title}</div>
      <div className="mt-2 text-xs text-muted">{props.body}</div>
    </div>
  );
}

function parseMusicXmlToDualView(xml: string): ProjectScoreView {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  const parserError = doc.getElementsByTagName("parsererror")[0];
  if (parserError) {
    throw new Error("MusicXML XML 解析失败（parsererror）");
  }

  const part = doc.getElementsByTagName("part")[0];
  if (!part) throw new Error("MusicXML 缺少 <part>");

  const measures = Array.from(part.getElementsByTagName("measure"));
  const outMeasures: ProjectScoreView["measures"] = [];

  for (const m of measures) {
    const mNumber = m.getAttribute("number") ?? "";
    const notes = Array.from(m.getElementsByTagName("note"));

    const staff1Notes = notes.filter((n) => n.getElementsByTagName("staff")[0]?.textContent?.trim() === "1");
    const staff2Notes = notes.filter((n) => n.getElementsByTagName("staff")[0]?.textContent?.trim() === "2");

    const staff2ByEid = new Map<string, Element>();
    for (const n of staff2Notes) {
      const other = n.getElementsByTagName("other-technical")[0];
      const text = other?.textContent?.trim() ?? "";
      const mEid = /(?:^|;)eid=([^;]+)/.exec(text)?.[1];
      if (!mEid) continue;
      staff2ByEid.set(mEid, n);
    }

    const events: Array<{ eid: string; jianpu_text: string | null; jzp_text: string }> = [];
    let currentEid: string | null = null;
    let group: Element[] = [];

    function flush() {
      if (!currentEid) return;
      const first = group[0];
      const jianpuText =
        Array.from(first.getElementsByTagName("lyric")).find((l) => l.getAttribute("placement") === "above")?.getElementsByTagName("text")[0]?.textContent?.trim() ??
        null;

      const staff2 = staff2ByEid.get(currentEid);
      const jzpText =
        (staff2
          ? Array.from(staff2.getElementsByTagName("lyric")).find((l) => l.getAttribute("placement") === "below")?.getElementsByTagName("text")[0]?.textContent?.trim()
          : null) ?? "（staff2 缺失）";

      events.push({ eid: currentEid, jianpu_text: jianpuText, jzp_text: jzpText });
    }

    for (const n of staff1Notes) {
      const other = n.getElementsByTagName("other-technical")[0];
      const text = other?.textContent?.trim() ?? "";
      const eid = /(?:^|;)eid=([^;]+)/.exec(text)?.[1];
      if (!eid) continue;
      if (currentEid === null) {
        currentEid = eid;
        group = [n];
      } else if (eid === currentEid) {
        group.push(n);
      } else {
        flush();
        currentEid = eid;
        group = [n];
      }
    }
    flush();

    outMeasures.push({
      number: mNumber,
      events: events.map((e) => ({ eid: e.eid, duration: 0, jzp_text: e.jzp_text, jianpu_text: e.jianpu_text })),
    });
  }

  return { project_id: "builtin", revision: "builtin", measures: outMeasures };
}
