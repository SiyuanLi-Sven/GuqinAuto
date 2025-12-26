"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { TopNav } from "@/components/app/top-nav";
import { useMemo, useState } from "react";

type InspectorTab = "简谱属性" | "减字属性" | "候选与诊断" | "回放表现";

export function EditorShell() {
  const [tab, setTab] = useState<InspectorTab>("简谱属性");

  const status = useMemo(() => {
    return {
      project: "未命名工程",
      scheme: "当前方案：A",
      locked: "锁定：3 / 128",
      saved: "未保存",
      bpm: 72,
    };
  }, []);

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
                  <Button size="sm" variant="ghost">
                    同步滚动
                  </Button>
                  <Button size="sm" variant="ghost">
                    同步光标
                  </Button>
                </div>
              </div>
              <div className="mt-4 space-y-3">
                <ScoreSystem
                  title="第 1 行（小节 1–4）"
                  subtitle="点击任意音符后：整行高亮同一 note-id，并在右侧 Inspector 打开。"
                />
                <ScoreSystem
                  title="第 2 行（小节 5–8）"
                  subtitle="后续 OSMD 渲染建议以“同一份 MusicXML 的两层显示/或两条 staff”实现。"
                />
                <ScoreSystem
                  title="第 3 行（小节 9–12）"
                  subtitle="这里仅是交互骨架占位：真实渲染与命中测试后再定细节。"
                />
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

function ScoreSystem(props: { title: string; subtitle?: string }) {
  return (
    <div className="rounded-xl border border-border bg-panel2 p-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="text-xs font-semibold">{props.title}</div>
        {props.subtitle ? (
          <div className="text-xs text-muted">{props.subtitle}</div>
        ) : null}
      </div>
      <div className="mt-3 grid gap-2">
        <div className="rounded-lg border border-border bg-panel p-3">
          <div className="text-[11px] font-medium text-muted">简谱（上）</div>
          <div className="mt-2 h-14 rounded-md border border-dashed border-border bg-panel2/60 p-2 text-xs text-muted">
            TODO：OSMD 渲染（简谱 clef-sign=jianpu），并与减字谱共享 note-id。
          </div>
        </div>
        <div className="rounded-lg border border-border bg-panel p-3">
          <div className="text-[11px] font-medium text-muted">减字谱（下）</div>
          <div className="mt-2 h-14 rounded-md border border-dashed border-border bg-panel2/60 p-2 text-xs text-muted">
            TODO：OSMD 渲染（减字谱 glyph/扩展槽位），与简谱联动高亮与选择。
          </div>
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
