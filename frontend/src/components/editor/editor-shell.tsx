"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { TopNav } from "@/components/app/top-nav";
import { OsmdViewer } from "@/components/score/osmd-viewer";
import { DualScoreView, ProjectScoreView } from "@/components/score/dual-score-view";
import { parseMusicXmlToDualView } from "@/lib/musicxml/parse-dual-view";
import { stripMusicXmlToStaff1 } from "@/lib/musicxml/strip-to-staff1";
import { http, HttpError } from "@/lib/http";
import { useEffect, useMemo, useState } from "react";

type InspectorTab = "简谱属性" | "减字属性" | "候选与诊断" | "回放表现";
type CenterView = "综合视图" | "OSMD";
type OsmdStaffMode = "仅staff1(隐藏TAB)" | "原始(含TAB)";

type BackendStatus = {
  pitch_resolved: boolean;
  has_chords: boolean;
  pitch_issues: Array<{ eid: string; slot: string | null; reason: string }>;
  consistency_warnings: Array<{
    eid: string;
    slot: string | null;
    reason: string;
    expected_pitch_midi: number | null;
    actual_pitch_midi: number | null;
  }>;
};

type Stage1Candidate = {
  string: number;
  technique: "open" | "press" | "harmonic" | string;
  pitch_midi: number;
  d_semitones_from_open: number;
  pos: { pos_ratio: number | null; hui_real: number | null; source: string | null } | null;
  temperament: string | null;
  harmonic_n: number | null;
  harmonic_k: number | null;
  cents_error: number | null;
  source: { method: string; [k: string]: unknown } | null;
};

type Stage1Target = {
  slot: string | null;
  target_pitch: { midi: number };
  candidates: Stage1Candidate[];
  errors?: string[];
};

type Stage2Lock = { eid: string; fields: Record<string, unknown> };

type Stage2Solution = {
  solution_id: string;
  total_cost: number;
  assignments: Array<
    | { eid: string; choice: { string: number; technique: string; pos?: { pos_ratio?: number | null } | null; harmonic_n?: number | null; harmonic_k?: number | null } }
    | { eid: string; choices: Array<{ slot: string; choice: { string: number; technique: string; pos?: { pos_ratio?: number | null } | null; harmonic_n?: number | null; harmonic_k?: number | null } }> }
  >;
  explain: Record<string, unknown>;
};

type Stage1CommitChoice =
  | { kind: "single"; candidate: Stage1Candidate }
  | { kind: "complex_chord"; left: Stage1Candidate; right: Stage1Candidate }
  | { kind: "simple_multistring"; candidates: Stage1Candidate[] };

export function EditorShell(props: { projectId?: string | null }) {
  const [tab, setTab] = useState<InspectorTab>("简谱属性");
  const [centerView, setCenterView] = useState<CenterView>("综合视图");
  const [osmdStaffMode, setOsmdStaffMode] = useState<OsmdStaffMode>("仅staff1(隐藏TAB)");
  const [musicxml, setMusicxml] = useState<string>("");
  const [score, setScore] = useState<ProjectScoreView | null>(null);
  const [source, setSource] = useState<"builtin" | "backend">("builtin");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [projectMeta, setProjectMeta] = useState<{ project_id: string; name: string; current_revision: string } | null>(
    null
  );
  const [projectStatus, setProjectStatus] = useState<BackendStatus | null>(null);
  const [selectedEid, setSelectedEid] = useState<string | null>(null);
  const [stage1ByEid, setStage1ByEid] = useState<Record<string, Stage1Target[]> | null>(null);
  const [stage1Error, setStage1Error] = useState<string | null>(null);
  const [stage2Locks, setStage2Locks] = useState<Stage2Lock[]>([]);
  const [stage2K, setStage2K] = useState(5);
  const [stage2Solutions, setStage2Solutions] = useState<Stage2Solution[] | null>(null);
  const [stage2Error, setStage2Error] = useState<string | null>(null);
  const [selectedSolutionId, setSelectedSolutionId] = useState<string | null>(null);
  const [pitchCompile, setPitchCompile] = useState<{ step: string; alter: number; octave: number; mode: "major" | "minor"; octave_shift: number }>({
    step: "C",
    alter: 0,
    octave: 4,
    mode: "major",
    octave_shift: 0,
  });

  const status = useMemo(() => {
    const projectName =
      source === "backend"
        ? projectMeta?.name ?? (props.projectId ? `工程 ${props.projectId}` : "未命名工程")
        : "内置示例";
    const scheme = projectStatus
      ? `pitch_resolved=${projectStatus.pitch_resolved ? "true" : "false"} · issues=${projectStatus.pitch_issues.length} · warn=${projectStatus.consistency_warnings.length}`
      : "pitch_resolved=—";
    return {
      project: projectName,
      scheme,
      locked: score ? `rev=${score.revision}` : "rev=—",
      saved: source === "backend" ? "快照制（revision）" : "只读示例",
      bpm: 72,
    };
  }, [source, projectMeta, projectStatus, props.projectId, score]);

  async function loadBuiltinExample() {
    setLoadError(null);
    setActionError(null);
    setSource("builtin");
    setBusy(true);
    setProjectMeta(null);
    setProjectStatus(null);
    setSelectedEid(null);
    setStage1ByEid(null);
    setStage1Error(null);
    setStage2Locks([]);
    setStage2Solutions(null);
    setStage2Error(null);
    setSelectedSolutionId(null);
    try {
      const res = await fetch("/examples/guqin_jzp_profile_v0.3_mary_had_a_little_lamb_input.musicxml");
      if (!res.ok) throw new Error(`加载内置示例失败：HTTP ${res.status}`);
      const xml = await res.text();
      setMusicxml(xml);
      setScore(parseMusicXmlToDualView(xml, { projectId: "builtin", revision: "builtin" }).view);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLoadError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function loadFromBackend() {
    setLoadError(null);
    setActionError(null);
    setSource("backend");
    const projectId = props.projectId;
    if (!projectId) {
      setLoadError("缺少 projectId：请从项目页打开，或在 URL 里传 ?projectId=xxx");
      return;
    }
    setBusy(true);
    setSelectedEid(null);
    setStage1ByEid(null);
    setStage1Error(null);
    setStage2Solutions(null);
    setStage2Error(null);
    setSelectedSolutionId(null);
    try {
      const [scoreData, st] = await Promise.all([
        http<ProjectScoreView>(`/api/backend/projects/${encodeURIComponent(projectId)}/score`),
        http<{ project: { project_id: string; name: string; current_revision: string }; status: BackendStatus }>(
          `/api/backend/projects/${encodeURIComponent(projectId)}/status`
        ),
      ]);
      setScore(scoreData);
      setProjectMeta(st.project);
      setProjectStatus(st.status);

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
    } finally {
      setBusy(false);
    }
  }

  async function generateDraftTop1() {
    if (source !== "backend") return;
    if (!props.projectId) return;
    if (!projectMeta?.current_revision) return;
    setLoadError(null);
    setActionError(null);
    setBusy(true);
    try {
      const pid = props.projectId;
      const data = await http<{
        commit?: { project?: { project_id: string; name: string; current_revision: string }; score?: ProjectScoreView; skipped?: boolean; reason?: string };
      }>(`/api/backend/projects/${encodeURIComponent(pid)}/stage2`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          base_revision: projectMeta.current_revision,
          k: 1,
          apply_mode: "commit_best",
          message: "editor: generate autodraft (stage2 commit_best)",
        }),
      });

      const commit = data?.commit;
      if (commit?.skipped) {
        setActionError(`生成初稿跳过：${commit.reason ?? "no_ops_after_filter"}`);
        return;
      }
      if (!commit?.project?.project_id || !commit?.project?.current_revision || !commit?.score) {
        throw new Error("后端返回缺少 commit.project/commit.score 信息");
      }

      setProjectMeta(commit.project);
      setScore(commit.score);

      const st = await http<{ status: BackendStatus }>(
        `/api/backend/projects/${encodeURIComponent(commit.project.project_id)}/status`
      );
      setProjectStatus(st.status);

      if (centerView === "OSMD") {
        const xmlData = await http<{ musicxml: string }>(
          `/api/backend/projects/${encodeURIComponent(commit.project.project_id)}/musicxml`
        );
        setMusicxml(xmlData.musicxml);
      }
    } catch (err) {
      const e = err as HttpError;
      setActionError(
        e?.name === "HttpError"
          ? `生成初稿失败：${e.status} ${e.url}\n${e.bodyText ?? ""}`
          : `生成初稿失败：${err instanceof Error ? err.message : String(err)}`
      );
    } finally {
      setBusy(false);
    }
  }

  const osmdXml = useMemo(() => {
    if (!musicxml) return "";
    if (osmdStaffMode === "原始(含TAB)") return musicxml;
    try {
      return stripMusicXmlToStaff1(musicxml);
    } catch {
      return musicxml;
    }
  }, [musicxml, osmdStaffMode]);

  useEffect(() => {
    // 默认行为：有 projectId 就拉后端真源；否则直接加载内置示例，保证“打开编辑器就能看到谱面”。
    if (props.projectId) {
      void loadFromBackend();
    } else {
      void loadBuiltinExample();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.projectId]);

  async function loadStage1() {
    if (source !== "backend") return;
    if (!props.projectId) return;
    if (!projectMeta?.current_revision) return;
    setStage1Error(null);
    setBusy(true);
    try {
      const data = await http<{
        project_id: string;
        revision: string;
        events: Array<{ eid: string; targets: Stage1Target[] }>;
        warnings: string[];
      }>(`/api/backend/projects/${encodeURIComponent(props.projectId)}/stage1`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          base_revision: projectMeta.current_revision,
          options: { include_errors: true },
        }),
      });
      const map: Record<string, Stage1Target[]> = {};
      for (const ev of data.events ?? []) {
        if (!ev?.eid) continue;
        map[String(ev.eid)] = (ev.targets ?? []) as Stage1Target[];
      }
      setStage1ByEid(map);
    } catch (err) {
      const e = err as HttpError;
      setStage1ByEid(null);
      setStage1Error(
        e?.name === "HttpError"
          ? `拉取 stage1 失败：${e.status} ${e.url}\n${e.bodyText ?? ""}`
          : `拉取 stage1 失败：${err instanceof Error ? err.message : String(err)}`
      );
    } finally {
      setBusy(false);
    }
  }

  async function runStage2TopK() {
    if (source !== "backend") return;
    if (!props.projectId) return;
    if (!projectMeta?.current_revision) return;
    setStage2Error(null);
    setBusy(true);
    try {
      const data = await http<{
        project_id: string;
        revision: string;
        stage2: { k: number; solutions: Stage2Solution[] };
        stage1_warnings: string[];
      }>(`/api/backend/projects/${encodeURIComponent(props.projectId)}/stage2`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          base_revision: projectMeta.current_revision,
          k: Math.max(1, Math.min(50, Number(stage2K) || 5)),
          apply_mode: "none",
          locks: stage2Locks,
          message: "editor: stage2 top-k (preview)",
        }),
      });
      const sols = data?.stage2?.solutions ?? [];
      setStage2Solutions(sols);
      setSelectedSolutionId(sols.length ? sols[0].solution_id : null);
    } catch (err) {
      const e = err as HttpError;
      setStage2Solutions(null);
      setSelectedSolutionId(null);
      setStage2Error(
        e?.name === "HttpError"
          ? `stage2 失败：${e.status} ${e.url}\n${e.bodyText ?? ""}`
          : `stage2 失败：${err instanceof Error ? err.message : String(err)}`
      );
    } finally {
      setBusy(false);
    }
  }

  async function commitBestWithLocks() {
    if (source !== "backend") return;
    if (!props.projectId) return;
    if (!projectMeta?.current_revision) return;
    setActionError(null);
    setBusy(true);
    try {
      const data = await http<{
        commit?: { project?: { project_id: string; name: string; current_revision: string }; score?: ProjectScoreView; skipped?: boolean; reason?: string };
      }>(`/api/backend/projects/${encodeURIComponent(props.projectId)}/stage2`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          base_revision: projectMeta.current_revision,
          k: 1,
          apply_mode: "commit_best",
          locks: stage2Locks,
          message: "editor: rerun stage2 commit_best (respect locks)",
        }),
      });
      const commit = data?.commit;
      if (commit?.skipped) {
        setActionError(`再推荐跳过：${commit.reason ?? "no_ops_after_filters_or_no_changes"}`);
        return;
      }
      if (!commit?.project?.project_id || !commit?.project?.current_revision || !commit?.score) {
        throw new Error("后端返回缺少 commit.project/commit.score 信息");
      }
      setProjectMeta(commit.project);
      setScore(commit.score);
      setStage1ByEid(null);
      setStage1Error(null);
      setStage2Solutions(null);
      setStage2Error(null);
      setSelectedSolutionId(null);

      const st = await http<{ status: BackendStatus }>(
        `/api/backend/projects/${encodeURIComponent(commit.project.project_id)}/status`
      );
      setProjectStatus(st.status);

      if (centerView === "OSMD") {
        const xmlData = await http<{ musicxml: string }>(
          `/api/backend/projects/${encodeURIComponent(commit.project.project_id)}/musicxml`
        );
        setMusicxml(xmlData.musicxml);
      }
    } catch (err) {
      const e = err as HttpError;
      setActionError(
        e?.name === "HttpError"
          ? `再推荐失败：${e.status} ${e.url}\n${e.bodyText ?? ""}`
          : `再推荐失败：${err instanceof Error ? err.message : String(err)}`
      );
    } finally {
      setBusy(false);
    }
  }

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
            {source === "backend" && projectStatus ? (
              <div className="mt-4 rounded-xl border border-border bg-panel2 p-3 text-xs text-muted">
                <div className="text-xs font-semibold text-text">就绪性</div>
                <div className="mt-2 space-y-1">
                  <div>pitch_resolved：{projectStatus.pitch_resolved ? "true" : "false"}</div>
                  <div>pitch_issues：{projectStatus.pitch_issues.length}</div>
                  <div>一致性 warning：{projectStatus.consistency_warnings.length}</div>
                </div>
                {!projectStatus.pitch_resolved && projectStatus.pitch_issues.length ? (
                  <div className="mt-2 whitespace-pre-wrap">
                    {projectStatus.pitch_issues.slice(0, 5).map((it) => `- ${it.eid}${it.slot ? `/${it.slot}` : ""}: ${it.reason}`).join("\n")}
                    {projectStatus.pitch_issues.length > 5 ? "\n…" : ""}
                  </div>
                ) : null}
                {projectStatus.consistency_warnings.length ? (
                  <div className="mt-3 whitespace-pre-wrap">
                    <div className="text-xs font-semibold text-text">一致性问题（前 5 条）</div>
                    <div className="mt-1">
                      {projectStatus.consistency_warnings
                        .slice(0, 5)
                        .map((w) => {
                          const exp = w.expected_pitch_midi == null ? "—" : String(w.expected_pitch_midi);
                          const act = w.actual_pitch_midi == null ? "—" : String(w.actual_pitch_midi);
                          return `- ${w.eid}${w.slot ? `/${w.slot}` : ""}: ${w.reason} (exp=${exp} act=${act})`;
                        })
                        .join("\n")}
                      {projectStatus.consistency_warnings.length > 5 ? "\n…" : ""}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
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
                  <Button
                    size="sm"
                    disabled={busy || source !== "backend" || !projectMeta?.current_revision}
                    onClick={() => void generateDraftTop1()}
                  >
                    生成初稿（Top-1）
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
                {actionError ? (
                  <div className="rounded-xl border border-danger/30 bg-panel2 p-3 text-xs text-muted whitespace-pre-wrap">
                    {actionError}
                  </div>
                ) : null}
                {centerView === "综合视图" ? (
                  score ? (
                    <DualScoreView
                      score={score}
                      selectedEid={selectedEid}
                      onSelectEid={(eid) => {
                        setSelectedEid(eid);
                        setTab("候选与诊断");
                      }}
                    />
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
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="text-xs text-muted">OSMD 仅渲染 staff1；减字谱由综合视图负责。</div>
                      <div className="w-full max-w-[260px]">
                        <Tabs<OsmdStaffMode>
                          items={["仅staff1(隐藏TAB)", "原始(含TAB)"]}
                          value={osmdStaffMode}
                          onChange={setOsmdStaffMode}
                        />
                      </div>
                    </div>
                    <OsmdViewer musicxml={osmdXml} className="rounded-xl" />
                  </div>
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
                <div className="space-y-3">
                    <div className="rounded-xl border border-border bg-panel2 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-xs font-semibold">候选与诊断（stage1）</div>
                        <div className="mt-1 text-xs text-muted">
                          先点选一个事件格（eid），再拉取候选；pitch_resolved 为 false 时会正确失败。
                        </div>
                      </div>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={busy || source !== "backend" || !projectMeta?.current_revision}
                        onClick={() => void loadStage1()}
                      >
                        拉取候选
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={busy || source !== "backend" || !projectMeta?.current_revision}
                        onClick={() => void runStage2TopK()}
                      >
                        stage2 Top-K
                      </Button>
                    </div>
                    <div className="mt-2 text-xs text-muted">
                      当前 eid：<span className="font-mono">{selectedEid ?? "（未选择）"}</span>
                    </div>
                    {stage1Error ? (
                      <div className="mt-3 rounded-xl border border-danger/30 bg-panel p-3 text-xs text-muted whitespace-pre-wrap">
                        {stage1Error}
                      </div>
                    ) : null}
                    {stage2Error ? (
                      <div className="mt-3 rounded-xl border border-danger/30 bg-panel p-3 text-xs text-muted whitespace-pre-wrap">
                        {stage2Error}
                      </div>
                    ) : null}
                    {source === "backend" && projectStatus?.consistency_warnings?.length && selectedEid ? (
                      <div className="mt-3 rounded-xl border border-border bg-panel p-3 text-xs text-muted whitespace-pre-wrap">
                        <div className="text-xs font-semibold text-text">该事件的一致性问题</div>
                        <div className="mt-1">
                          {projectStatus.consistency_warnings
                            .filter((w) => w.eid === selectedEid)
                            .slice(0, 8)
                            .map((w) => {
                              const exp = w.expected_pitch_midi == null ? "—" : String(w.expected_pitch_midi);
                              const act = w.actual_pitch_midi == null ? "—" : String(w.actual_pitch_midi);
                              return `- ${w.eid}${w.slot ? `/${w.slot}` : ""}: ${w.reason} (exp=${exp} act=${act})`;
                            })
                            .join("\n") || "（无）"}
                        </div>
                      </div>
                    ) : null}
                  </div>

                  {source === "backend" ? (
                    <Stage2LocksPanel
                      eid={selectedEid}
                      staff2Kv={
                        selectedEid
                          ? score?.measures.flatMap((m) => m.events).find((e) => e.eid === selectedEid)?.staff2_kv ?? null
                          : null
                      }
                      locks={stage2Locks}
                      onChangeLocks={setStage2Locks}
                      onCommitBest={() => void commitBestWithLocks()}
                      busy={busy}
                    />
                  ) : null}

                  {source === "backend" ? (
                    <Stage2TopKPanel
                      eid={selectedEid}
                      k={stage2K}
                      onChangeK={setStage2K}
                      solutions={stage2Solutions}
                      selectedSolutionId={selectedSolutionId}
                      onSelectSolutionId={setSelectedSolutionId}
                    />
                  ) : null}

                  {selectedEid && stage1ByEid?.[selectedEid] ? (
                    <Stage1CandidatePanel
                      eid={selectedEid}
                      targets={stage1ByEid[selectedEid]}
                      staff2Kv={
                        score?.measures.flatMap((m) => m.events).find((e) => e.eid === selectedEid)
                          ?.staff2_kv ?? null
                      }
                      onCommit={async (choice) => {
                        if (source !== "backend") return;
                        if (!props.projectId) return;
                        if (!projectMeta?.current_revision) return;
                        setActionError(null);
                        setBusy(true);
                        try {
                          const changes: Record<string, string | null> = {};
                          if (choice.kind === "single") {
                            Object.assign(changes, buildV03PatchFromCandidate(choice.candidate));
                          } else if (choice.kind === "simple_multistring") {
                            Object.assign(changes, buildV03PatchFromSimpleMultistring(choice.candidates));
                          } else {
                            Object.assign(changes, buildV03PatchFromCandidate(choice.left, { prefix: "l_" }));
                            Object.assign(changes, buildV03PatchFromCandidate(choice.right, { prefix: "r_" }));
                          }

                          const data = await http<{
                            project?: { project_id: string; name: string; current_revision: string };
                            score?: ProjectScoreView;
                          }>(`/api/backend/projects/${encodeURIComponent(props.projectId)}/apply`, {
                            method: "POST",
                            headers: { "content-type": "application/json" },
                            body: JSON.stringify({
                              base_revision: projectMeta.current_revision,
                              edit_source: "user",
                              message: `editor: commit stage1 choice eid=${selectedEid}`,
                              ops: [{ op: "update_guqin_event", eid: selectedEid, changes }],
                            }),
                          });

                          if (!data?.project?.current_revision || !data?.score) {
                            throw new Error("后端返回缺少 project/score");
                          }
                          setProjectMeta(data.project);
                          setScore(data.score);

                          const st = await http<{ status: BackendStatus }>(
                            `/api/backend/projects/${encodeURIComponent(data.project.project_id)}/status`
                          );
                          setProjectStatus(st.status);
                          setStage1ByEid(null);

                          if (centerView === "OSMD") {
                            const xmlData = await http<{ musicxml: string }>(
                              `/api/backend/projects/${encodeURIComponent(data.project.project_id)}/musicxml`
                            );
                            setMusicxml(xmlData.musicxml);
                          }
                        } catch (err) {
                          const e = err as HttpError;
                          setActionError(
                            e?.name === "HttpError"
                              ? `写回失败：${e.status} ${e.url}\n${e.bodyText ?? ""}`
                              : `写回失败：${err instanceof Error ? err.message : String(err)}`
                          );
                        } finally {
                          setBusy(false);
                        }
                      }}
                    />
                  ) : (
                    <InspectorCard
                      title="提示"
                      body="未选中事件或还未拉取候选。先点击综合视图里的事件格，然后点“拉取候选”。"
                    />
                  )}
                </div>
              ) : null}
              {tab === "回放表现" ? (
                <InspectorCard
                  title="回放表现（占位）"
                  body="把谱面语义映射到“能听”：滑音/吟猱强度、起止时间百分比、装饰音抢拍、泛音音色衰减等。"
                />
              ) : null}

              {tab === "候选与诊断" && source === "backend" && projectStatus && !projectStatus.pitch_resolved ? (
                <div className="rounded-xl border border-border bg-panel2 p-3">
                  <div className="text-xs font-semibold">Pitch 编译（简谱→绝对 pitch）</div>
                  <div className="mt-2 text-xs text-muted">
                    当前项目 pitch_resolved=false；stage1/stage2 会正确失败。若 staff1 已有 `lyric@above` 简谱度数，可在这里指定调性后编译写回。
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <label className="text-xs text-muted">
                      主音 step
                      <input
                        className="mt-1 w-full rounded-lg border border-border bg-panel px-2 py-1 text-xs text-text outline-none"
                        value={pitchCompile.step}
                        onChange={(e) => setPitchCompile((p) => ({ ...p, step: e.target.value.trim() || "C" }))}
                      />
                    </label>
                    <label className="text-xs text-muted">
                      alter
                      <input
                        className="mt-1 w-full rounded-lg border border-border bg-panel px-2 py-1 text-xs text-text outline-none"
                        value={String(pitchCompile.alter)}
                        onChange={(e) => setPitchCompile((p) => ({ ...p, alter: Number.parseInt(e.target.value || "0", 10) || 0 }))}
                      />
                    </label>
                    <label className="text-xs text-muted">
                      octave
                      <input
                        className="mt-1 w-full rounded-lg border border-border bg-panel px-2 py-1 text-xs text-text outline-none"
                        value={String(pitchCompile.octave)}
                        onChange={(e) => setPitchCompile((p) => ({ ...p, octave: Number.parseInt(e.target.value || "4", 10) || 4 }))}
                      />
                    </label>
                    <label className="text-xs text-muted">
                      mode
                      <select
                        className="mt-1 w-full rounded-lg border border-border bg-panel px-2 py-1 text-xs text-text outline-none"
                        value={pitchCompile.mode}
                        onChange={(e) => setPitchCompile((p) => ({ ...p, mode: (e.target.value as "major" | "minor") || "major" }))}
                      >
                        <option value="major">major</option>
                        <option value="minor">minor</option>
                      </select>
                    </label>
                    <label className="text-xs text-muted col-span-2">
                      octave_shift
                      <input
                        className="mt-1 w-full rounded-lg border border-border bg-panel px-2 py-1 text-xs text-text outline-none"
                        value={String(pitchCompile.octave_shift)}
                        onChange={(e) => setPitchCompile((p) => ({ ...p, octave_shift: Number.parseInt(e.target.value || "0", 10) || 0 }))}
                      />
                    </label>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <Button
                      size="sm"
                      disabled={busy || !projectMeta?.current_revision || !props.projectId}
                      onClick={() => {
                        if (!props.projectId || !projectMeta?.current_revision) return;
                        setActionError(null);
                        setBusy(true);
                        void (async () => {
                          try {
                            const data = await http<{ project?: { project_id: string; name: string; current_revision: string }; score?: ProjectScoreView }>(
                              `/api/backend/projects/${encodeURIComponent(props.projectId!)}/compile_pitch_from_jianpu`,
                              {
                                method: "POST",
                                headers: { "content-type": "application/json" },
                                body: JSON.stringify({
                                  base_revision: projectMeta.current_revision,
                                  tonic: { step: pitchCompile.step, alter: pitchCompile.alter, octave: pitchCompile.octave },
                                  mode: pitchCompile.mode,
                                  octave_shift: pitchCompile.octave_shift,
                                  message: "editor: compile_pitch_from_jianpu",
                                }),
                              }
                            );
                            if (!data?.project?.current_revision || !data?.score) throw new Error("后端返回缺少 project/score");
                            setProjectMeta(data.project);
                            setScore(data.score);
                            const st = await http<{ status: BackendStatus }>(
                              `/api/backend/projects/${encodeURIComponent(data.project.project_id)}/status`
                            );
                            setProjectStatus(st.status);
                          } catch (err) {
                            const e = err as HttpError;
                            setActionError(
                              e?.name === "HttpError"
                                ? `pitch 编译失败：${e.status} ${e.url}\n${e.bodyText ?? ""}`
                                : `pitch 编译失败：${err instanceof Error ? err.message : String(err)}`
                            );
                          } finally {
                            setBusy(false);
                          }
                        })();
                      }}
                    >
                      编译并写回
                    </Button>
                  </div>
                </div>
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

function Stage1CandidatePanel(props: {
  eid: string;
  targets: Stage1Target[];
  staff2Kv: Record<string, string> | null;
  onCommit: (choice: Stage1CommitChoice) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const single = props.targets.length === 1 ? props.targets[0] : null;
  const complexChord =
    props.targets.length === 2 &&
    props.targets.every((t) => t.slot === "L" || t.slot === "R") &&
    props.staff2Kv?.form === "complex";
  const simpleMultistring =
    props.targets.length >= 2 &&
    props.staff2Kv?.form === "simple" &&
    props.staff2Kv?.xian_finger === "历" &&
    props.targets.every((t) => typeof t.slot === "string" && /^[1-7]$/.test(t.slot));

  if (!single && !complexChord && !simpleMultistring) {
    return (
      <InspectorCard
        title="暂不支持"
        body={`当前事件 targets=${props.targets.length}；编辑器 MVP 目前仅支持：单音；form=complex 的 2-note 和弦（slot=L/R）；或 form=simple 的多弦（slot=1..N）。eid=${props.eid}`}
      />
    );
  }

  if (complexChord) {
    const left = props.targets.find((t) => t.slot === "L")!;
    const right = props.targets.find((t) => t.slot === "R")!;
    return (
      <Stage1ComplexChordPanel
        eid={props.eid}
        left={left}
        right={right}
        onCommit={(l, r) => props.onCommit({ kind: "complex_chord", left: l, right: r })}
      />
    );
  }

  if (simpleMultistring) {
    const targets = [...props.targets].sort((a, b) => Number(a.slot) - Number(b.slot));
    return (
      <Stage1SimpleMultistringPanel
        eid={props.eid}
        targets={targets}
        onCommit={(cands) => props.onCommit({ kind: "simple_multistring", candidates: cands })}
      />
    );
  }

  const s = single!;
  const candidates = s.candidates ?? [];
  const top = expanded ? candidates : candidates.slice(0, 12);

  return (
    <div className="rounded-xl border border-border bg-panel2 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold">eid={props.eid}</div>
          <div className="mt-1 text-xs text-muted">
            target_midi={s.target_pitch?.midi ?? "—"} · candidates={candidates.length}
          </div>
        </div>
        <Button size="sm" variant="ghost" onClick={() => setExpanded((v) => !v)} disabled={candidates.length <= 12}>
          {expanded ? "收起" : "展开"}
        </Button>
      </div>

      {s.errors?.length ? (
        <div className="mt-3 rounded-xl border border-danger/30 bg-panel p-3 text-xs text-muted whitespace-pre-wrap">
          {s.errors.map((e) => `- ${e}`).join("\n")}
        </div>
      ) : null}

      {top.length ? (
        <div className="mt-3 space-y-2">
          {top.map((c, idx) => (
            <div key={idx} className="rounded-xl border border-border bg-panel p-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs font-semibold">
                    {c.technique} · 弦 {c.string}
                  </div>
                  <div className="mt-1 text-[11px] text-muted whitespace-pre-wrap">
                    pitch_midi={c.pitch_midi} · d={c.d_semitones_from_open} ·
                    {c.technique === "press" ? ` pos_ratio=${fmtNum(c.pos?.pos_ratio)}` : ""}
                    {c.technique === "harmonic" ? ` n=${fmtNum(c.harmonic_n)} k=${fmtNum(c.harmonic_k)} pr=${fmtNum(c.pos?.pos_ratio)}` : ""}
                    {c.cents_error != null ? ` · cents_err=${fmtNum(c.cents_error)}` : ""}
                  </div>
                </div>
                <Button size="sm" onClick={() => void props.onCommit({ kind: "single", candidate: c })}>
                  写回
                </Button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-3 text-xs text-muted">无候选（可能是调弦/transpose/max_d 设置导致）。</div>
      )}
    </div>
  );
}

function fmtNum(v: number | null | undefined): string {
  if (v == null) return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return String(Math.round(n * 1000) / 1000);
}

function Stage2LocksPanel(props: {
  eid: string | null;
  staff2Kv: Record<string, string> | null;
  locks: Stage2Lock[];
  onChangeLocks: (locks: Stage2Lock[]) => void;
  onCommitBest: () => void;
  busy: boolean;
}) {
  const eid = props.eid;
  const kv = props.staff2Kv;
  const curLocks = eid ? props.locks.filter((l) => l.eid === eid) : [];

  const form = kv?.form ?? null;
  const soundToTechnique = (s: string | undefined | null): string | null => {
    if (!s) return null;
    if (s === "open") return "open";
    if (s === "pressed") return "press";
    if (s === "harmonic") return "harmonic";
    return null;
  };

  const addOrReplaceLock = (lock: Stage2Lock) => {
    const rest = props.locks.filter((l) => !(l.eid === lock.eid && String(l.fields.slot ?? "") === String(lock.fields.slot ?? "")));
    props.onChangeLocks([...rest, lock]);
  };

  const removeLocksForEid = () => {
    if (!eid) return;
    props.onChangeLocks(props.locks.filter((l) => l.eid !== eid));
  };

  const removeLock = (slot?: string) => {
    if (!eid) return;
    props.onChangeLocks(
      props.locks.filter((l) => !(l.eid === eid && String(l.fields.slot ?? "") === String(slot ?? "")))
    );
  };

  const guessSingleLock = (): Stage2Lock | null => {
    if (!eid || !kv) return null;
    const xian = kv.xian ? Number(String(kv.xian).split(",")[0]) : null;
    const tech = soundToTechnique(kv.sound);
    const fields: Record<string, unknown> = {};
    if (Number.isFinite(xian ?? NaN)) fields.string = xian!;
    if (tech) fields.technique = tech;
    if (!Object.keys(fields).length) return null;
    return { eid, fields };
  };

  const guessComplexLock = (slot: "L" | "R"): Stage2Lock | null => {
    if (!eid || !kv) return null;
    const xian = slot === "L" ? Number(kv.l_xian) : Number(kv.r_xian);
    const tech = soundToTechnique(slot === "L" ? kv.l_sound : kv.r_sound);
    const fields: Record<string, unknown> = { slot };
    if (Number.isFinite(xian ?? NaN)) fields.string = xian!;
    if (tech) fields.technique = tech;
    if (Object.keys(fields).length <= 1) return null;
    return { eid, fields };
  };

  return (
    <div className="rounded-xl border border-border bg-panel2 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold">锁定（stage2 locks）</div>
          <div className="mt-1 text-xs text-muted">
            锁定会作为硬约束传给 stage2；无解会正确失败。锁定仅影响“再推荐/Top-K”，不自动写回。
          </div>
        </div>
        <Button size="sm" variant="ghost" disabled={!eid || !curLocks.length} onClick={() => removeLocksForEid()}>
          清空本 eid
        </Button>
      </div>

      <div className="mt-3 text-xs text-muted">
        当前锁：{curLocks.length ? curLocks.map((l) => JSON.stringify(l.fields)).join(" | ") : "（无）"}
      </div>

      {!eid ? (
        <div className="mt-3 text-xs text-muted">先点选一个事件格（eid）。</div>
      ) : form === "complex" ? (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="rounded-xl border border-border bg-panel p-2">
            <div className="text-xs font-semibold">L</div>
            <div className="mt-2 flex items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  const lk = guessComplexLock("L");
                  if (lk) addOrReplaceLock(lk);
                }}
              >
                从当前真值生成锁
              </Button>
              <Button size="sm" variant="ghost" onClick={() => removeLock("L")}>
                移除
              </Button>
            </div>
          </div>
          <div className="rounded-xl border border-border bg-panel p-2">
            <div className="text-xs font-semibold">R</div>
            <div className="mt-2 flex items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  const lk = guessComplexLock("R");
                  if (lk) addOrReplaceLock(lk);
                }}
              >
                从当前真值生成锁
              </Button>
              <Button size="sm" variant="ghost" onClick={() => removeLock("R")}>
                移除
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              const lk = guessSingleLock();
              if (lk) addOrReplaceLock(lk);
            }}
          >
            从当前真值生成锁
          </Button>
        </div>
      )}

      <div className="mt-3 flex items-center justify-between gap-2">
        <div className="text-xs text-muted">
          再推荐只覆盖 `user_touched=0`（且 `truth_src!=user`）的单元。
        </div>
        <Button size="sm" disabled={props.busy || !props.eid} onClick={() => props.onCommitBest()}>
          对未改部分再推荐（Top-1）
        </Button>
      </div>
    </div>
  );
}

function Stage2TopKPanel(props: {
  eid: string | null;
  k: number;
  onChangeK: (k: number) => void;
  solutions: Stage2Solution[] | null;
  selectedSolutionId: string | null;
  onSelectSolutionId: (id: string | null) => void;
}) {
  const sols = props.solutions ?? [];
  const sel = sols.find((s) => s.solution_id === props.selectedSolutionId) ?? sols[0] ?? null;

  const choiceForEid = (sol: Stage2Solution, eid: string) => {
    const a = sol.assignments.find((x) => x.eid === eid);
    if (!a) return null;
    if ("choice" in a) return { kind: "single" as const, choice: a.choice };
    if ("choices" in a) return { kind: "chord" as const, choices: a.choices };
    return null;
  };

  const fmtChoice = (c: { string: number; technique: string; pos?: { pos_ratio?: number | null } | null; harmonic_n?: number | null }) => {
    const pr = c.pos?.pos_ratio;
    const prS = typeof pr === "number" ? ` pr=${fmtNum(pr)}` : "";
    const hnS = typeof c.harmonic_n === "number" ? ` n=${c.harmonic_n}` : "";
    return `${c.technique} · 弦${c.string}${prS}${hnS}`;
  };

  return (
    <div className="rounded-xl border border-border bg-panel2 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold">Top-K（stage2）</div>
          <div className="mt-1 text-xs text-muted">展示序列级 Top-K 方案；当前 MVP 仅预览，不直接“应用某个方案”。</div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted">K</span>
          <input
            className="w-16 rounded-lg border border-border bg-panel px-2 py-1 text-xs text-text outline-none"
            value={String(props.k)}
            onChange={(e) => props.onChangeK(Math.max(1, Math.min(50, Number.parseInt(e.target.value || \"5\", 10) || 5)))}
          />
        </div>
      </div>

      {!sols.length ? (
        <div className="mt-3 text-xs text-muted">尚未运行 stage2（点“stage2 Top-K”）。</div>
      ) : (
        <div className="mt-3 space-y-2">
          {sols.slice(0, 10).map((s) => (
            <button
              key={s.solution_id}
              type="button"
              className={`w-full rounded-xl border bg-panel p-2 text-left ${props.selectedSolutionId === s.solution_id ? "border-primary/60" : "border-border hover:border-primary/30"}`}
              onClick={() => props.onSelectSolutionId(s.solution_id)}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs font-semibold">{s.solution_id}</div>
                <div className="text-xs text-muted">cost={fmtNum(s.total_cost)}</div>
              </div>
              {props.eid ? (
                <div className="mt-1 text-[11px] text-muted">
                  {(() => {
                    const x = choiceForEid(s, props.eid!);
                    if (!x) return "该 eid 不在方案中";
                    if (x.kind === "single") return fmtChoice(x.choice);
                    const bySlot = [...x.choices].sort((a, b) => a.slot.localeCompare(b.slot));
                    return bySlot.map((it) => `${it.slot}:${fmtChoice(it.choice)}`).join(" · ");
                  })()}
                </div>
              ) : null}
            </button>
          ))}
        </div>
      )}

      {sel && props.eid ? (
        <div className="mt-3 rounded-xl border border-border bg-panel p-2 text-xs text-muted whitespace-pre-wrap">
          当前选中：{sel.solution_id}\n{(() => {
            const x = choiceForEid(sel, props.eid!);
            if (!x) return "（该 eid 不在方案中）";
            if (x.kind === "single") return fmtChoice(x.choice);
            const bySlot = [...x.choices].sort((a, b) => a.slot.localeCompare(b.slot));
            return bySlot.map((it) => `${it.slot}:${fmtChoice(it.choice)}`).join("\n");
          })()}
        </div>
      ) : null}
    </div>
  );
}

function buildV03PatchFromCandidate(
  c: Stage1Candidate,
  opts: { prefix?: "" | "l_" | "r_" } = {}
): Record<string, string | null> {
  const prefix = opts.prefix ?? "";
  const changes: Record<string, string | null> = {};

  if (prefix) {
    changes[`${prefix}xian`] = String(c.string);
  } else {
    changes.xian = String(c.string);
  }

  const set = (k: string, v: string | null) => {
    changes[prefix ? `${prefix}${k}` : k] = v;
  };

  // 显式清空互斥字段（后端支持 value=null 表示删除 key）。
  if (prefix === "") {
    const keys = ["sound", "pos_ratio", "harmonic_n", "harmonic_k"];
    for (let i = 1; i <= 7; i += 1) keys.push(`pos_ratio_${i}`);
    for (const k of keys) set(k, null);
  } else if (prefix === "l_" || prefix === "r_") {
    for (const k of ["sound", "pos_ratio", "harmonic_n", "harmonic_k"]) set(k, null);
  }

  if (c.technique === "open") {
    set("sound", "open");
    return changes;
  }
  if (c.technique === "press") {
    set("sound", "pressed");
    if (typeof c.pos?.pos_ratio !== "number") throw new Error("press 候选缺少 pos.pos_ratio（无法写回）");
    set("pos_ratio", String(c.pos.pos_ratio));
    return changes;
  }
  if (c.technique === "harmonic") {
    set("sound", "harmonic");
    if (typeof c.harmonic_n !== "number") throw new Error("harmonic 候选缺少 harmonic_n（无法写回）");
    set("harmonic_n", String(c.harmonic_n));
    if (typeof c.harmonic_k === "number") set("harmonic_k", String(c.harmonic_k));
    if (typeof c.pos?.pos_ratio === "number") set("pos_ratio", String(c.pos.pos_ratio));
    return changes;
  }
  throw new Error(`暂不支持写回 technique=${c.technique}`);
}

function buildV03PatchFromSimpleMultistring(candidates: Stage1Candidate[]): Record<string, string | null> {
  if (candidates.length < 2) throw new Error("simple 多弦写回需要 >=2 个候选");
  const technique = candidates[0].technique;
  if (!candidates.every((c) => c.technique === technique)) {
    throw new Error("simple 多弦写回要求 technique 一致");
  }

  const changes: Record<string, string | null> = {};
  changes.form = "simple";
  changes.xian = candidates.map((c) => String(c.string)).join(",");

  // 清空互斥字段
  const keys: string[] = ["sound", "pos_ratio", "harmonic_n", "harmonic_k"];
  for (let i = 1; i <= 7; i += 1) keys.push(`pos_ratio_${i}`);
  for (const k of keys) changes[k] = null;

  if (technique === "open") {
    changes.sound = "open";
    return changes;
  }
  if (technique === "press") {
    changes.sound = "pressed";
    for (let i = 0; i < candidates.length; i += 1) {
      const pr = candidates[i].pos?.pos_ratio;
      if (typeof pr !== "number") throw new Error(`press 多弦候选缺少 pos_ratio：slot=${i + 1}`);
      changes[`pos_ratio_${i + 1}`] = String(pr);
    }
    return changes;
  }
  if (technique === "harmonic") {
    changes.sound = "harmonic";
    const ns = new Set(candidates.map((c) => c.harmonic_n).filter((n): n is number => typeof n === "number"));
    if (ns.size !== 1) throw new Error("harmonic 多弦写回要求 harmonic_n 一致");
    changes.harmonic_n = String([...ns][0]);
    return changes;
  }

  throw new Error(`暂不支持 simple 多弦 technique=${technique}`);
}

function Stage1ComplexChordPanel(props: {
  eid: string;
  left: Stage1Target;
  right: Stage1Target;
  onCommit: (left: Stage1Candidate, right: Stage1Candidate) => void;
}) {
  const [lIdx, setLIdx] = useState(0);
  const [rIdx, setRIdx] = useState(0);
  const leftCandidates = props.left.candidates ?? [];
  const rightCandidates = props.right.candidates ?? [];
  const l = leftCandidates[lIdx] ?? null;
  const r = rightCandidates[rIdx] ?? null;
  const stringConflict = l != null && r != null && Number(l.string) === Number(r.string);

  return (
    <div className="rounded-xl border border-border bg-panel2 p-3 space-y-3">
      <div className="text-xs font-semibold">complex 和弦（eid={props.eid}）</div>
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-xl border border-border bg-panel p-2">
          <div className="text-xs font-semibold">L</div>
          <div className="mt-1 text-[11px] text-muted">
            target_midi={props.left.target_pitch?.midi ?? "—"} · candidates={leftCandidates.length}
          </div>
          <select
            className="mt-2 w-full rounded-lg border border-border bg-panel2 px-2 py-1 text-xs text-text outline-none"
            value={String(lIdx)}
            onChange={(e) => setLIdx(Number.parseInt(e.target.value, 10) || 0)}
          >
            {leftCandidates.slice(0, 50).map((c, idx) => (
              <option key={idx} value={String(idx)}>
                {idx + 1}. {c.technique} · 弦{c.string}
                {c.technique === "press" ? ` · pr=${fmtNum(c.pos?.pos_ratio)}` : ""}
                {c.technique === "harmonic" ? ` · n=${fmtNum(c.harmonic_n)}` : ""}
              </option>
            ))}
          </select>
          {l ? (
            <div className="mt-2 text-[11px] text-muted whitespace-pre-wrap">
              pitch_midi={l.pitch_midi} · d={l.d_semitones_from_open}
            </div>
          ) : null}
        </div>
        <div className="rounded-xl border border-border bg-panel p-2">
          <div className="text-xs font-semibold">R</div>
          <div className="mt-1 text-[11px] text-muted">
            target_midi={props.right.target_pitch?.midi ?? "—"} · candidates={rightCandidates.length}
          </div>
          <select
            className="mt-2 w-full rounded-lg border border-border bg-panel2 px-2 py-1 text-xs text-text outline-none"
            value={String(rIdx)}
            onChange={(e) => setRIdx(Number.parseInt(e.target.value, 10) || 0)}
          >
            {rightCandidates.slice(0, 50).map((c, idx) => (
              <option key={idx} value={String(idx)}>
                {idx + 1}. {c.technique} · 弦{c.string}
                {c.technique === "press" ? ` · pr=${fmtNum(c.pos?.pos_ratio)}` : ""}
                {c.technique === "harmonic" ? ` · n=${fmtNum(c.harmonic_n)}` : ""}
              </option>
            ))}
          </select>
          {r ? (
            <div className="mt-2 text-[11px] text-muted whitespace-pre-wrap">
              pitch_midi={r.pitch_midi} · d={r.d_semitones_from_open}
            </div>
          ) : null}
        </div>
      </div>
      <div className="flex items-center justify-end gap-2">
        <Button size="sm" disabled={!l || !r || stringConflict} onClick={() => l && r && !stringConflict && props.onCommit(l, r)}>
          写回（L/R）
        </Button>
      </div>
      {stringConflict ? (
        <div className="rounded-xl border border-danger/30 bg-panel p-3 text-xs text-muted">
          物理约束：同一时刻一根弦不能发两个音；请为 L/R 选择不同弦号的候选。
        </div>
      ) : null}
    </div>
  );
}

function Stage1SimpleMultistringPanel(props: {
  eid: string;
  targets: Stage1Target[];
  onCommit: (candidates: Stage1Candidate[]) => void;
}) {
  const [idxBySlot, setIdxBySlot] = useState<Record<string, number>>(() => {
    const init: Record<string, number> = {};
    for (const t of props.targets) init[String(t.slot)] = 0;
    return init;
  });

  const picked: Array<{ slot: string; candidate: Stage1Candidate | null }> = props.targets.map((t) => {
    const slot = String(t.slot);
    const idx = idxBySlot[slot] ?? 0;
    const c = (t.candidates ?? [])[idx] ?? null;
    return { slot, candidate: c };
  });

  const candidates = picked.map((p) => p.candidate).filter((c): c is Stage1Candidate => c != null);
  const techniqueSet = new Set(candidates.map((c) => c.technique));
  const techniqueOk = candidates.length === picked.length && techniqueSet.size === 1;
  const technique = techniqueOk ? (candidates[0].technique as Stage1Candidate["technique"]) : null;
  const stringOk = candidates.length === picked.length && new Set(candidates.map((c) => Number(c.string))).size === candidates.length;

  let harmonicOk = true;
  if (technique === "harmonic") {
    const ns = new Set(candidates.map((c) => c.harmonic_n).filter((n) => typeof n === "number"));
    harmonicOk = ns.size === 1;
  }

  const canCommit = techniqueOk && harmonicOk && stringOk;

  return (
    <div className="rounded-xl border border-border bg-panel2 p-3 space-y-3">
      <div className="text-xs font-semibold">simple 多弦（eid={props.eid}）</div>
      <div className="text-xs text-muted">
        约束：写回 v0.3 真值要求各 slot technique 一致；harmonic 还要求 harmonic_n 一致。
      </div>
      <div className="space-y-2">
        {props.targets.map((t) => {
          const slot = String(t.slot);
          const cands = t.candidates ?? [];
          const curIdx = idxBySlot[slot] ?? 0;
          const cur = cands[curIdx] ?? null;
          return (
            <div key={slot} className="rounded-xl border border-border bg-panel p-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs font-semibold">slot {slot}</div>
                  <div className="mt-1 text-[11px] text-muted">
                    target_midi={t.target_pitch?.midi ?? "—"} · candidates={cands.length}
                  </div>
                </div>
                <select
                  className="w-[220px] rounded-lg border border-border bg-panel2 px-2 py-1 text-xs text-text outline-none"
                  value={String(curIdx)}
                  onChange={(e) => {
                    const v = Number.parseInt(e.target.value, 10) || 0;
                    setIdxBySlot((m) => ({ ...m, [slot]: v }));
                  }}
                >
                  {cands.slice(0, 60).map((c, idx) => (
                    <option key={idx} value={String(idx)}>
                      {idx + 1}. {c.technique} · 弦{c.string}
                      {c.technique === "press" ? ` · pr=${fmtNum(c.pos?.pos_ratio)}` : ""}
                      {c.technique === "harmonic" ? ` · n=${fmtNum(c.harmonic_n)}` : ""}
                    </option>
                  ))}
                </select>
              </div>
              {cur ? (
                <div className="mt-2 text-[11px] text-muted whitespace-pre-wrap">
                  pitch_midi={cur.pitch_midi} · d={cur.d_semitones_from_open}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {!techniqueOk ? (
        <div className="rounded-xl border border-danger/30 bg-panel p-3 text-xs text-muted">
          请先为每个 slot 选择候选（且确保 technique 一致）。
        </div>
      ) : !stringOk ? (
        <div className="rounded-xl border border-danger/30 bg-panel p-3 text-xs text-muted">
          物理约束：同一时刻一根弦不能发两个音；请确保各 slot 选择的弦号不重复。
        </div>
      ) : !harmonicOk ? (
        <div className="rounded-xl border border-danger/30 bg-panel p-3 text-xs text-muted">
          harmonic 多弦要求 harmonic_n 一致；请重新选择。
        </div>
      ) : null}

      <div className="flex items-center justify-end gap-2">
        <Button size="sm" disabled={!canCommit} onClick={() => canCommit && props.onCommit(candidates)}>
          写回（{technique ?? "—"}）
        </Button>
      </div>
    </div>
  );
}

// 解析器已抽到 lib：`src/lib/musicxml/parse-dual-view.ts`
