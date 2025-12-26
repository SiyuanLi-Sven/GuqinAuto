"""
GuqinAuto 后端 API（FastAPI）。

约定：
- 服务端口：7130
- workspace：backend/workspace（文件夹管理多个项目）

API 设计原则：
- 以“事件级编辑（eid）”为核心，前端提交 delta ops，后端应用并生成新 revision。
- 严格校验，宁可失败，不做静默降级。
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .musicxml_profile_v0_2 import EditOp, apply_edit_ops, build_score_view
from .workspace import (
    ProjectMeta,
    create_project_from_example,
    list_projects,
    load_project_meta,
    load_revision_bytes,
    save_new_revision,
)


app = FastAPI(title="GuqinAuto Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1)
    example_filename: str = Field(default="guqin_jzp_profile_v0.2_showcase.musicxml")


class ApplyEditsRequest(BaseModel):
    base_revision: str
    message: str | None = None
    ops: list[dict[str, Any]]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/projects")
def api_list_projects() -> list[dict[str, Any]]:
    return [asdict(p) for p in list_projects()]


@app.post("/projects")
def api_create_project(req: CreateProjectRequest) -> dict[str, Any]:
    meta = create_project_from_example(name=req.name, example_filename=req.example_filename)
    return asdict(meta)


@app.get("/projects/{project_id}")
def api_get_project(project_id: str) -> dict[str, Any]:
    meta = load_project_meta(project_id)
    return asdict(meta)


@app.get("/projects/{project_id}/musicxml")
def api_get_musicxml(project_id: str) -> dict[str, Any]:
    meta = load_project_meta(project_id)
    xml_bytes = load_revision_bytes(project_id, meta.current_revision)
    return {"project_id": project_id, "revision": meta.current_revision, "musicxml": xml_bytes.decode("utf-8")}


@app.get("/projects/{project_id}/score")
def api_get_score(project_id: str) -> dict[str, Any]:
    meta = load_project_meta(project_id)
    xml_bytes = load_revision_bytes(project_id, meta.current_revision)
    view = build_score_view(project_id=project_id, revision=meta.current_revision, musicxml_bytes=xml_bytes)
    return asdict(view)


@app.post("/projects/{project_id}/apply")
def api_apply_edits(project_id: str, req: ApplyEditsRequest) -> dict[str, Any]:
    meta = load_project_meta(project_id)
    if meta.current_revision != req.base_revision:
        raise HTTPException(status_code=409, detail=f"revision 冲突：current={meta.current_revision} base={req.base_revision}")

    xml_bytes = load_revision_bytes(project_id, meta.current_revision)

    try:
        parsed_ops: list[EditOp] = []
        for raw in req.ops:
            if raw.get("op") != "update_guqin_event":
                raise ValueError(f"仅支持 op=update_guqin_event，收到：{raw.get('op')!r}")
            eid = raw.get("eid")
            if not isinstance(eid, str) or not eid:
                raise ValueError("op 缺少 eid")
            changes = raw.get("changes")
            if not isinstance(changes, dict):
                raise ValueError("op 缺少 changes dict")
            parsed_ops.append(EditOp(op="update_guqin_event", eid=eid, changes={str(k): str(v) for k, v in changes.items()}))

        new_xml_bytes = apply_edit_ops(musicxml_bytes=xml_bytes, ops=parsed_ops)
        new_meta = save_new_revision(
            project_id=project_id,
            base_revision=meta.current_revision,
            musicxml_bytes=new_xml_bytes,
            delta_ops=req.ops,
            message=req.message,
        )

        view = build_score_view(project_id=project_id, revision=new_meta.current_revision, musicxml_bytes=new_xml_bytes)
        return {"project": asdict(new_meta), "score": asdict(view)}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

