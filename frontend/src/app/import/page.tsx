"use client";

import { PageShell } from "@/components/app/page-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import Link from "next/link";
import { useMemo, useState } from "react";

export default function ImportPage() {
  const [title, setTitle] = useState("未命名工程");
  const [tempo, setTempo] = useState("72");
  const [timeSig, setTimeSig] = useState("4/4");
  const [tuning, setTuning] = useState("正调");
  const [rawJson, setRawJson] = useState(
    JSON.stringify(
      {
        schema: "guqin-auto-jianpu@0.1",
        meta: { title: "示例：输入占位", tempo: 72, timeSignature: "4/4" },
        notes: [
          { degree: 1, octave: 0, dur: "1/8" },
          { degree: 2, octave: 0, dur: "1/8" },
        ],
      },
      null,
      2
    )
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

  return (
    <PageShell
      title="导入与参数"
      subtitle="接收“干净的简谱数据结构”，并设置生成约束。后续对接后端校验与生成。"
      actions={
        <div className="flex items-center gap-2">
          <Link href="/">
            <Button variant="ghost">返回项目</Button>
          </Link>
          <Link href="/editor">
            <Button disabled={!parseResult.ok}>进入编辑器</Button>
          </Link>
        </div>
      }
    >
      <div className="grid gap-3 lg:grid-cols-2">
        <Card>
          <div className="text-sm font-semibold">工程与生成参数</div>
          <div className="mt-4 grid gap-3">
            <Input
              label="工程名称"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例如：秋风词（练习版）"
            />
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="速度（BPM）"
                value={tempo}
                onChange={(e) => setTempo(e.target.value)}
                inputMode="numeric"
              />
              <Input
                label="拍号"
                value={timeSig}
                onChange={(e) => setTimeSig(e.target.value)}
                placeholder="例如：4/4"
              />
            </div>
            <Input
              label="古琴定弦/调弦"
              value={tuning}
              onChange={(e) => setTuning(e.target.value)}
              placeholder="例如：正调 / 慢三 / 紧五"
            />
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Badge tone={parseResult.ok ? "ok" : "danger"}>
                {parseResult.ok ? "可继续" : "需修正"}
              </Badge>
              <span className="text-xs text-muted">{parseResult.message}</span>
            </div>
          </div>
          <div className="mt-4 rounded-xl border border-border bg-panel2 p-3 text-xs text-muted">
            这页最终会做：字段完整性、时值合法性、调性可解析等校验；参数变更触发生成候选方案但不丢锁定字段。
          </div>
        </Card>

        <Card className="flex flex-col">
          <div className="text-sm font-semibold">简谱输入（JSON 占位）</div>
          <div className="mt-3 flex-1">
            <Textarea
              value={rawJson}
              onChange={(e) => setRawJson(e.target.value)}
              className="h-[440px] font-mono text-xs"
              ariaLabel="简谱JSON"
            />
          </div>
          <div className="mt-3 flex items-center justify-between">
            <Button
              variant="secondary"
              onClick={() =>
                setRawJson(
                  JSON.stringify(
                    {
                      schema: "guqin-auto-jianpu@0.1",
                      meta: { title, tempo: Number(tempo), timeSignature: timeSig },
                      tuning,
                      notes: [],
                    },
                    null,
                    2
                  )
                )
              }
            >
              用当前参数重写meta
            </Button>
            <Button variant="ghost">上传文件（未实现）</Button>
          </div>
        </Card>
      </div>
    </PageShell>
  );
}

