"use client";

import { EditorShell } from "@/components/editor/editor-shell";
import { useSearchParams } from "next/navigation";

export default function EditorPage() {
  const sp = useSearchParams();
  const projectId = sp.get("projectId");
  return <EditorShell projectId={projectId} />;
}
