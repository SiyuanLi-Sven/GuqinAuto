"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type OsmdViewerProps = {
  musicxml: string;
  className?: string;
  onError?: (err: unknown) => void;
};

export function OsmdViewer(props: OsmdViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  const normalizedXml = useMemo(() => props.musicxml.trim(), [props.musicxml]);

  useEffect(() => {
    let disposed = false;

    async function run() {
      setRenderError(null);
      const el = containerRef.current;
      if (!el) return;
      if (!normalizedXml) return;

      el.innerHTML = "";

      try {
        const mod = await import("opensheetmusicdisplay");
        if (disposed) return;

        const osmd = new mod.OpenSheetMusicDisplay(el, {
          autoResize: true,
          drawingParameters: "compact",
          drawTitle: false,
        });

        await osmd.load(normalizedXml);
        if (disposed) return;
        await osmd.render();
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setRenderError(msg);
        props.onError?.(err);
      }
    }

    run();
    return () => {
      disposed = true;
    };
  }, [normalizedXml, props]);

  if (!normalizedXml) {
    return (
      <div className={props.className}>
        <div className="rounded-xl border border-border bg-panel2 p-3 text-xs text-muted">
          未提供 MusicXML。
        </div>
      </div>
    );
  }

  return (
    <div className={props.className}>
      {renderError ? (
        <div className="rounded-xl border border-danger/30 bg-panel2 p-3 text-xs text-muted">
          OSMD 渲染失败：{renderError}
        </div>
      ) : null}
      <div ref={containerRef} className="overflow-auto rounded-xl bg-panel" />
    </div>
  );
}

