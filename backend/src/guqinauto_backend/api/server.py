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
from fastapi import File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..domain.musicxml_profile_v0_2 import EditOp, apply_edit_ops, build_score_view
from ..domain.musicxml_staff1_pitch import PitchValue, Staff1PitchAssignment, apply_staff1_pitch_assignments
from ..domain.jianpu_pitch_compiler import compile_degree_to_pitch, parse_degree
from ..domain.pitch import MusicXmlPitch
from ..engines.position_engine import PositionEngine, PositionEngineOptions
from ..domain.status import compute_status, status_to_dict
from ..infra.workspace import (
    ProjectMeta,
    ProjectTuning,
    create_project_from_example,
    create_project_from_musicxml_bytes,
    list_projects,
    load_project_meta,
    load_revision_bytes,
    save_project_meta,
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
    example_filename: str = Field(default="guqin_jzp_profile_v0.3_mary_had_a_little_lamb_input.musicxml")
    tuning: Stage1Tuning | None = None


class ApplyEditsRequest(BaseModel):
    base_revision: str
    edit_source: str = Field(default="user", pattern="^(user|auto)$")
    message: str | None = None
    ops: list[dict[str, Any]]


class Stage1Tuning(BaseModel):
    name: str | None = None
    open_pitches_midi: list[int] = Field(min_length=7, max_length=7)
    transpose_semitones: int = 0


class Stage1Options(BaseModel):
    temperament: str = Field(default="equal", pattern="^(equal|just)$")
    max_d_semitones: int = Field(default=36, ge=0, le=60)
    include_harmonics: bool = False
    max_harmonic_n: int = Field(default=12, ge=2, le=32)
    max_harmonic_cents_error: float = Field(default=25.0, ge=0.0, le=100.0)
    include_errors: bool = True


class Stage1Request(BaseModel):
    base_revision: str
    tuning: Stage1Tuning | None = None
    options: Stage1Options = Stage1Options()


def _stage1_candidate_to_dict(c: Any) -> dict[str, Any]:
    # PositionCandidate 序列化为 API 结构（保持层次清晰，便于前端消费）。
    technique = c.technique
    if technique == "open":
        source = {"method": "open_string"}
    elif technique == "press":
        source = {"method": "12tet_press"}
    elif technique == "harmonic":
        source = {"method": "natural_harmonic", "harmonic_n": c.harmonic_n}
    else:
        source = {"method": "unknown"}

    pos_source = None
    if technique == "press":
        pos_source = "pos_ratio=12tet; hui_real=table"
    elif technique == "harmonic":
        pos_source = "pos_ratio=k/n; hui_real=interp_from_press_table"

    return {
        "string": c.string,
        "technique": technique,
        "pitch_midi": c.pitch_midi,
        "d_semitones_from_open": c.d_semitones_from_open,
        "pos": {"pos_ratio": c.pos_ratio, "hui_real": c.hui_real, "source": pos_source},
        "temperament": c.temperament,
        "harmonic_n": c.harmonic_n,
        "harmonic_k": c.harmonic_k,
        "cents_error": c.cents_error,
        "source": source,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/projects")
def api_list_projects() -> list[dict[str, Any]]:
    return [asdict(p) for p in list_projects()]


@app.post("/projects")
def api_create_project(req: CreateProjectRequest) -> dict[str, Any]:
    tuning = ProjectTuning.from_dict(req.tuning.model_dump()) if req.tuning is not None else None
    meta = create_project_from_example(name=req.name, example_filename=req.example_filename, tuning=tuning)
    return asdict(meta)


@app.post("/projects/import_musicxml")
async def api_import_musicxml(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
) -> dict[str, Any]:
    """上传 MusicXML 并创建工程（严格校验 Profile，不做隐式补全）。"""

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="上传文件为空")

    # 若未提供 name，则使用文件名（去掉扩展名）作为工程名
    project_name = (name or "").strip()
    if not project_name:
        fn = (file.filename or "").strip()
        if fn.lower().endswith(".musicxml"):
            fn = fn[: -len(".musicxml")]
        elif fn.lower().endswith(".xml"):
            fn = fn[: -len(".xml")]
        project_name = fn or "未命名工程"

    # 学术级：先严格解析/校验，再落盘（避免把不符合 Profile 的工程写进 workspace）
    try:
        _ = build_score_view(project_id="UPLOAD", revision="R000000", musicxml_bytes=raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"MusicXML 不符合当前 Profile（无法解析为事件流）：{e}") from e

    meta = create_project_from_musicxml_bytes(name=project_name, musicxml_bytes=raw)
    xml_bytes = load_revision_bytes(meta.project_id, meta.current_revision)
    view = build_score_view(project_id=meta.project_id, revision=meta.current_revision, musicxml_bytes=xml_bytes)
    return {"project": asdict(meta), "score": asdict(view)}


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
    try:
        view = build_score_view(project_id=project_id, revision=meta.current_revision, musicxml_bytes=xml_bytes)
        return asdict(view)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"MusicXML 不符合当前 Profile（无法解析为事件流）：{e}") from e


@app.get("/projects/{project_id}/status")
def api_get_status(project_id: str) -> dict[str, Any]:
    meta = load_project_meta(project_id)
    xml_bytes = load_revision_bytes(project_id, meta.current_revision)
    try:
        view = build_score_view(project_id=project_id, revision=meta.current_revision, musicxml_bytes=xml_bytes)
        status = compute_status(view, tuning=meta.tuning)
        return {"project": asdict(meta), "status": status_to_dict(status)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"MusicXML 不符合当前 Profile（无法解析为事件流）：{e}") from e


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
            parsed_changes: dict[str, str | None] = {}
            for k, v in changes.items():
                key = str(k)
                if v is None:
                    parsed_changes[key] = None
                else:
                    parsed_changes[key] = str(v)
            parsed_ops.append(EditOp(op="update_guqin_event", eid=eid, changes=parsed_changes))

        # 写回元数据：区分“系统生成初稿(auto)”与“用户改动(user)”
        new_xml_bytes = apply_edit_ops(musicxml_bytes=xml_bytes, ops=parsed_ops, edit_source=req.edit_source)  # type: ignore[arg-type]
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


class ResolvePitchAssignment(BaseModel):
    eid: str = Field(min_length=1)
    slot: str | None = None
    step: str = Field(min_length=1)
    alter: int = 0
    octave: int


class ResolvePitchRequest(BaseModel):
    base_revision: str
    message: str | None = None
    assignments: list[ResolvePitchAssignment] = Field(min_length=1)
    require_pitch_resolved_after: bool = True


@app.post("/projects/{project_id}/resolve_pitch")
def api_resolve_pitch(project_id: str, req: ResolvePitchRequest) -> dict[str, Any]:
    meta = load_project_meta(project_id)
    if meta.current_revision != req.base_revision:
        raise HTTPException(status_code=409, detail=f"revision 冲突：current={meta.current_revision} base={req.base_revision}")

    xml_bytes = load_revision_bytes(project_id, meta.current_revision)

    try:
        assigns = [
            Staff1PitchAssignment(
                eid=a.eid,
                slot=a.slot,
                pitch=PitchValue(step=a.step, alter=a.alter, octave=a.octave),
            )
            for a in req.assignments
        ]
        new_xml_bytes = apply_staff1_pitch_assignments(musicxml_bytes=xml_bytes, assignments=assigns)

        # 若要求 pitch-resolved，则做一次严格诊断
        if req.require_pitch_resolved_after:
            view = build_score_view(project_id=project_id, revision=meta.current_revision, musicxml_bytes=new_xml_bytes)
            st = compute_status(view)
            if not st.pitch_resolved:
                raise ValueError(f"pitch_resolved=False：仍存在未解析 pitch 的事件：{len(st.pitch_issues)}")

        new_meta = save_new_revision(
            project_id=project_id,
            base_revision=meta.current_revision,
            musicxml_bytes=new_xml_bytes,
            delta_ops=[{"op": "resolve_pitch", "assignments": [a.model_dump() for a in req.assignments]}],
            message=req.message,
        )

        view2 = build_score_view(project_id=project_id, revision=new_meta.current_revision, musicxml_bytes=new_xml_bytes)
        return {"project": asdict(new_meta), "score": asdict(view2)}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class TonicPitch(BaseModel):
    step: str = Field(min_length=1)
    alter: int = 0
    octave: int


class CompilePitchFromJianpuRequest(BaseModel):
    base_revision: str
    message: str | None = None
    tonic: TonicPitch
    mode: str = Field(default="major", pattern="^(major|minor)$")
    octave_shift: int = 0
    require_pitch_resolved_after: bool = True


@app.post("/projects/{project_id}/compile_pitch_from_jianpu")
def api_compile_pitch_from_jianpu(project_id: str, req: CompilePitchFromJianpuRequest) -> dict[str, Any]:
    meta = load_project_meta(project_id)
    if meta.current_revision != req.base_revision:
        raise HTTPException(status_code=409, detail=f"revision 冲突：current={meta.current_revision} base={req.base_revision}")

    xml_bytes = load_revision_bytes(project_id, meta.current_revision)
    view = build_score_view(project_id=project_id, revision=meta.current_revision, musicxml_bytes=xml_bytes)

    tonic = MusicXmlPitch(step=req.tonic.step, alter=req.tonic.alter, octave=req.tonic.octave)
    mode = "major" if req.mode == "major" else "minor"

    try:
        assignments: list[Staff1PitchAssignment] = []
        for m in view.measures:
            for e in m.events:
                if len(e.staff1_notes) != 1:
                    raise ValueError(f"compile_pitch_from_jianpu 暂不支持 chord：eid={e.eid} staff1_notes={len(e.staff1_notes)}")
                if e.jianpu_text is None:
                    raise ValueError(f"缺少 jianpu_text（lyric@above），无法编译 pitch：eid={e.eid}")
                degree = parse_degree(e.jianpu_text)
                cp = compile_degree_to_pitch(degree=degree, tonic=tonic, mode=mode, octave_shift=req.octave_shift)
                assignments.append(
                    Staff1PitchAssignment(
                        eid=e.eid,
                        slot=None,
                        pitch=PitchValue(step=cp.step, alter=cp.alter, octave=cp.octave),
                    )
                )

        new_xml_bytes = apply_staff1_pitch_assignments(musicxml_bytes=xml_bytes, assignments=assignments)

        if req.require_pitch_resolved_after:
            view2 = build_score_view(project_id=project_id, revision=meta.current_revision, musicxml_bytes=new_xml_bytes)
            st = compute_status(view2)
            if not st.pitch_resolved:
                raise ValueError(f"pitch_resolved=False：仍存在未解析 pitch 的事件：{len(st.pitch_issues)}")

        new_meta = save_new_revision(
            project_id=project_id,
            base_revision=meta.current_revision,
            musicxml_bytes=new_xml_bytes,
            delta_ops=[
                {
                    "op": "compile_pitch_from_jianpu",
                    "tonic": req.tonic.model_dump(),
                    "mode": req.mode,
                    "octave_shift": req.octave_shift,
                }
            ],
            message=req.message,
        )

        view3 = build_score_view(project_id=project_id, revision=new_meta.current_revision, musicxml_bytes=new_xml_bytes)
        return {"project": asdict(new_meta), "score": asdict(view3)}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class Stage2Lock(BaseModel):
    eid: str = Field(min_length=1)
    fields: dict[str, Any]


class Stage2Preferences(BaseModel):
    shift: float = 1.0
    string_change: float = 0.5
    technique_change: float = 0.2
    harmonic_penalty: float = 0.1
    cents_error: float = 0.01


class Stage2Request(BaseModel):
    base_revision: str
    k: int = Field(default=5, ge=1, le=50)
    tuning: Stage1Tuning | None = None
    stage1_options: Stage1Options = Stage1Options()
    locks: list[Stage2Lock] = []
    preferences: Stage2Preferences = Stage2Preferences()
    apply_mode: str = Field(default="none", pattern="^(none|commit_best)$")
    message: str | None = None


@app.post("/projects/{project_id}/stage1")
def api_stage1(project_id: str, req: Stage1Request) -> dict[str, Any]:
    meta = load_project_meta(project_id)
    if meta.current_revision != req.base_revision:
        raise HTTPException(status_code=409, detail=f"revision 冲突：current={meta.current_revision} base={req.base_revision}")

    xml_bytes = load_revision_bytes(project_id, meta.current_revision)
    try:
        view = build_score_view(project_id=project_id, revision=meta.current_revision, musicxml_bytes=xml_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"MusicXML 不符合当前 Profile（无法解析为事件流）：{e}") from e

    tuning_dict = req.tuning.model_dump() if req.tuning is not None else meta.tuning.to_dict()
    tuning = ProjectTuning.from_dict(tuning_dict)
    engine = PositionEngine(open_pitches_midi=list(tuning.open_pitches_midi), transpose_semitones=tuning.transpose_semitones)
    opt = PositionEngineOptions(
        temperament="equal" if req.options.temperament == "equal" else "just",
        max_d_semitones=req.options.max_d_semitones,
        include_harmonics=req.options.include_harmonics,
        max_harmonic_n=req.options.max_harmonic_n,
        max_harmonic_cents_error=req.options.max_harmonic_cents_error,
    )

    events_out: list[dict[str, Any]] = []
    warnings: list[str] = []
    for m in view.measures:
        for e in m.events:
            if not e.staff1_notes:
                raise HTTPException(status_code=400, detail=f"pitch-unresolved：eid={e.eid}（staff1 缺少音符，无法 stage1）")

            targets: list[dict[str, Any]] = []
            for n in e.staff1_notes:
                slot = n.get("slot")
                p = n.get("pitch")
                if not isinstance(p, dict) or "step" not in p or "octave" not in p:
                    raise HTTPException(status_code=400, detail=f"pitch-unresolved：eid={e.eid} slot={slot!r}（staff1 缺少绝对 pitch，无法 stage1）")

                pitch = MusicXmlPitch(step=str(p["step"]), octave=int(p["octave"]), alter=int(p.get("alter", 0)))
                target_midi = pitch.to_midi()
                try:
                    candidates = engine.enumerate_candidates(pitch_midi=target_midi, options=opt)
                except NotImplementedError as ex:
                    raise HTTPException(status_code=400, detail=str(ex)) from ex
                errors: list[str] = []
                if not candidates:
                    errors.append("no_candidates_for_tuning_or_transpose")
                    warnings.append(f"eid={e.eid} slot={slot!r}: no candidates (consider tuning/transpose/max_d)")

                targets.append(
                    {
                        "slot": slot,
                        "target_pitch": {"midi": target_midi},
                        "candidates": [_stage1_candidate_to_dict(c) for c in candidates],
                        **({"errors": errors} if req.options.include_errors else {}),
                    }
                )

            events_out.append({"eid": e.eid, "targets": targets})

    return {
        "project_id": project_id,
        "revision": meta.current_revision,
        "tuning": tuning.to_dict(),
        "options": req.options.model_dump(),
        "events": events_out,
        "warnings": warnings,
    }


@app.post("/projects/{project_id}/stage2")
def api_stage2(project_id: str, req: Stage2Request) -> dict[str, Any]:
    meta = load_project_meta(project_id)
    if meta.current_revision != req.base_revision:
        raise HTTPException(status_code=409, detail=f"revision 冲突：current={meta.current_revision} base={req.base_revision}")

    # 复用 stage1 的输出结构作为输入图
    stage1 = api_stage1(project_id, Stage1Request(base_revision=req.base_revision, tuning=req.tuning, options=req.stage1_options))

    from ..engines.stage2_optimizer import Lock, Weights, optimize_topk

    locks = [Lock(eid=l.eid, fields=l.fields) for l in req.locks]
    weights = Weights(
        shift=req.preferences.shift,
        string_change=req.preferences.string_change,
        technique_change=req.preferences.technique_change,
        harmonic_penalty=req.preferences.harmonic_penalty,
        cents_error=req.preferences.cents_error,
    )

    try:
        sols = optimize_topk(events=stage1["events"], k=req.k, locks=locks, weights=weights)

        if req.apply_mode == "none":
            return {
                "project_id": project_id,
                "revision": meta.current_revision,
                "tuning": stage1["tuning"],
                "stage1_warnings": stage1.get("warnings", []),
                "stage2": {"k": req.k, "solutions": [s.__dict__ for s in sols]},
            }

        # commit_best：把 Top-1 推荐显式写回 staff2（生成新 revision）
        # 约束（MVP）：
        # - 仅覆盖 user_touched=0 的事件（用户确认过的视为硬约束）
        # - 允许覆盖旧的 auto 真值字段：通过显式删除互斥字段（value=None）保证写回后仍满足 Profile v0.3
        # - chord 写回只支持“staff2 已有结构化形态能承载”的情况：
        #   - form=complex 且 slot=L/R（写入 l_*/r_*）
        #   - form=simple 且 xian 为多弦（写入 pos_ratio_1..N / harmonic_n 等；要求每个 slot technique 一致）
        if req.apply_mode != "commit_best":
            raise HTTPException(status_code=400, detail=f"未知 apply_mode：{req.apply_mode!r}")
        if not sols:
            raise HTTPException(status_code=400, detail="stage2 无可用解，无法 commit_best")

        xml_bytes = load_revision_bytes(project_id, meta.current_revision)
        view = build_score_view(project_id=project_id, revision=meta.current_revision, musicxml_bytes=xml_bytes)
        by_eid = {e.eid: e for m in view.measures for e in m.events}
        sol0 = sols[0]

        SIMPLE_V03_KEYS = {"sound", "pos_ratio", "harmonic_n", "harmonic_k", *[f"pos_ratio_{i}" for i in range(1, 8)]}
        COMPLEX_V03_KEYS = {
            "l_sound",
            "l_pos_ratio",
            "l_harmonic_n",
            "l_harmonic_k",
            "r_sound",
            "r_pos_ratio",
            "r_harmonic_n",
            "r_harmonic_k",
        }

        def _diff_changes(existing_kv: dict[str, str], patch: dict[str, str | None]) -> dict[str, str | None]:
            out: dict[str, str | None] = {}
            for k, v in patch.items():
                if v is None:
                    if k in existing_kv:
                        out[k] = None
                else:
                    if existing_kv.get(k) != v:
                        out[k] = v
            return out

        def choice_to_changes(choice: dict[str, Any], *, existing_kv: dict[str, str]) -> dict[str, str | None]:
            technique = str(choice.get("technique") or "")
            string = int(choice["string"])
            changes: dict[str, str | None] = {"xian": str(string)}

            # 仅当缺省时补齐（避免覆盖已有读法层字段）
            if "form" not in existing_kv:
                changes["form"] = "simple"
            if "lex" not in existing_kv:
                changes["lex"] = "abbr"
            if "xian_finger" not in existing_kv:
                changes["xian_finger"] = "勾"

            # v0.3 真值字段：显式删除不相关字段（允许重复推荐/覆盖 auto 结果，而不会留下脏字段导致 Profile 校验失败）
            for k in SIMPLE_V03_KEYS:
                changes[k] = None

            if technique == "open":
                changes["sound"] = "open"
                return changes

            if technique == "press":
                changes["sound"] = "pressed"
                pos = choice.get("pos") or {}
                pr = pos.get("pos_ratio")
                if not isinstance(pr, (int, float)):
                    raise ValueError(f"press 候选缺少 pos_ratio：{choice!r}")
                changes["pos_ratio"] = str(float(pr))
                return changes

            if technique == "harmonic":
                changes["sound"] = "harmonic"
                hn = choice.get("harmonic_n")
                if not isinstance(hn, int):
                    raise ValueError(f"harmonic 候选缺少 harmonic_n：{choice!r}")
                changes["harmonic_n"] = str(int(hn))
                hk = choice.get("harmonic_k")
                if isinstance(hk, int):
                    changes["harmonic_k"] = str(int(hk))
                # 可选缓存：pos_ratio（k/n），用于显示；不参与 pitch 推导
                pos = choice.get("pos") or {}
                pr = pos.get("pos_ratio")
                if isinstance(pr, (int, float)):
                    changes["pos_ratio"] = str(float(pr))
                return changes

            raise ValueError(f"未知 technique：{technique!r}")

        v03_keys = {
            "sound",
            "pos_ratio",
            "harmonic_n",
            "harmonic_k",
            *[f"pos_ratio_{i}" for i in range(1, 8)],
            "l_sound",
            "l_pos_ratio",
            "l_harmonic_n",
            "l_harmonic_k",
            "r_sound",
            "r_pos_ratio",
            "r_harmonic_n",
            "r_harmonic_k",
        }

        def _sound_fields_from_choice(choice: dict[str, Any], *, prefix: str = "") -> dict[str, str | None]:
            technique = str(choice.get("technique") or "")
            out: dict[str, str | None] = {}
            if prefix in ("l_", "r_"):
                for k in COMPLEX_V03_KEYS:
                    if k.startswith(prefix):
                        out[k] = None
            else:
                for k in SIMPLE_V03_KEYS:
                    out[k] = None

            if technique == "open":
                out[f"{prefix}sound" if prefix else "sound"] = "open"
                return out
            if technique == "press":
                pos = choice.get("pos") or {}
                pr = pos.get("pos_ratio")
                if not isinstance(pr, (int, float)):
                    raise ValueError(f"press 候选缺少 pos_ratio：{choice!r}")
                out[f"{prefix}sound" if prefix else "sound"] = "pressed"
                out[f"{prefix}pos_ratio" if prefix else "pos_ratio"] = str(float(pr))
                return out
            if technique == "harmonic":
                hn = choice.get("harmonic_n")
                if not isinstance(hn, int):
                    raise ValueError(f"harmonic 候选缺少 harmonic_n：{choice!r}")
                out[f"{prefix}sound" if prefix else "sound"] = "harmonic"
                out[f"{prefix}harmonic_n" if prefix else "harmonic_n"] = str(int(hn))
                hk = choice.get("harmonic_k")
                if isinstance(hk, int):
                    out[f"{prefix}harmonic_k" if prefix else "harmonic_k"] = str(int(hk))
                # 可选缓存：pos_ratio（k/n）
                pos = choice.get("pos") or {}
                pr = pos.get("pos_ratio")
                if isinstance(pr, (int, float)):
                    out[f"{prefix}pos_ratio" if prefix else "pos_ratio"] = str(float(pr))
                return out
            raise ValueError(f"未知 technique：{technique!r}")

        def chord_choices_to_changes(choices: list[dict[str, Any]], *, existing_kv: dict[str, str]) -> dict[str, str | None]:
            slot_to_choice: dict[str, dict[str, Any]] = {}
            for it in choices:
                slot = it.get("slot")
                ch = it.get("choice")
                if not isinstance(slot, str) or not slot:
                    raise ValueError(f"stage2 chord choices 含非法 slot：{it!r}")
                if not isinstance(ch, dict):
                    raise ValueError(f"stage2 chord choices 含非法 choice：{it!r}")
                slot_to_choice[slot] = ch

            form = existing_kv.get("form")
            if form == "complex":
                if set(slot_to_choice.keys()) != {"L", "R"}:
                    raise ValueError(f"commit_best: complex 事件要求 slot=L/R，收到：{sorted(slot_to_choice.keys())!r}")
                lc = slot_to_choice["L"]
                rc = slot_to_choice["R"]
                changes: dict[str, str | None] = {
                    "form": "complex",
                    "l_xian": str(int(lc["string"])),
                    "r_xian": str(int(rc["string"])),
                }
                changes.update(_sound_fields_from_choice(lc, prefix="l_"))
                changes.update(_sound_fields_from_choice(rc, prefix="r_"))
                return changes

            if form == "simple":
                # 多弦 simple：slot 必须为 "1..N"，并且每个 slot 的 technique 必须一致（否则无法用一个 sound 表示）。
                slots = sorted(slot_to_choice.keys(), key=lambda s: int(s) if s.isdigit() else 10**9)
                if not slots or any((not s.isdigit() or int(s) <= 0) for s in slots):
                    raise ValueError(f"commit_best: simple 多弦事件要求 slot=1..N，收到：{slots!r}")
                if slots != [str(i) for i in range(1, len(slots) + 1)]:
                    raise ValueError(f"commit_best: simple 多弦事件 slot 必须连续从 1 开始：{slots!r}")

                techniques = {str(slot_to_choice[s].get('technique') or '') for s in slots}
                if len(techniques) != 1:
                    raise ValueError(f"commit_best: simple 多弦事件不支持混合 technique：{sorted(techniques)!r}")
                technique = next(iter(techniques))

                strings = [str(int(slot_to_choice[str(i)]["string"])) for i in range(1, len(slots) + 1)]
                changes: dict[str, str | None] = {"form": "simple", "xian": ",".join(strings)}
                for k in SIMPLE_V03_KEYS:
                    changes[k] = None

                if technique == "open":
                    changes["sound"] = "open"
                    return changes

                if technique == "press":
                    changes["sound"] = "pressed"
                    for i in range(1, len(slots) + 1):
                        pos = slot_to_choice[str(i)].get("pos") or {}
                        pr = pos.get("pos_ratio")
                        if not isinstance(pr, (int, float)):
                            raise ValueError(f"press 候选缺少 pos_ratio：slot={i} choice={slot_to_choice[str(i)]!r}")
                        changes[f"pos_ratio_{i}"] = str(float(pr))
                    return changes

                if technique == "harmonic":
                    changes["sound"] = "harmonic"
                    hns = {slot_to_choice[s].get("harmonic_n") for s in slots}
                    if any(not isinstance(hn, int) for hn in hns):
                        raise ValueError(f"harmonic 候选缺少 harmonic_n：{choices!r}")
                    if len(hns) != 1:
                        raise ValueError(f"commit_best: simple harmonic 多弦要求共享 harmonic_n：{sorted(hns)!r}")
                    changes["harmonic_n"] = str(int(next(iter(hns))))  # type: ignore[arg-type]
                    return changes

                raise ValueError(f"未知 technique：{technique!r}")

            raise ValueError(f"commit_best: chord 写回要求 staff2 form 为 simple/complex，收到：{form!r}")

        ops: list[EditOp] = []
        for a in sol0.assignments:
            eid = str(a.get("eid") or "")
            if not eid:
                raise ValueError("solution assignment 缺少 eid")
            ev = by_eid.get(eid)
            if ev is None:
                raise ValueError(f"solution assignment 引用未知 eid：{eid}")
            if ev.staff2_kv.get("user_touched") == "1":
                continue
            if ev.staff2_kv.get("truth_src") == "user":
                continue

            if "choice" in a:
                choice = a["choice"]
                if not isinstance(choice, dict):
                    raise ValueError(f"solution assignment choice 非 dict：eid={eid}")
                patch = choice_to_changes(choice, existing_kv=ev.staff2_kv)
                diff = _diff_changes(ev.staff2_kv, patch)
                if diff:
                    ops.append(EditOp(op="update_guqin_event", eid=eid, changes=diff))
                continue

            if "choices" in a:
                choices = a["choices"]
                if not isinstance(choices, list):
                    raise ValueError(f"solution assignment choices 非 list：eid={eid}")
                patch = chord_choices_to_changes(choices, existing_kv=ev.staff2_kv)
                diff = _diff_changes(ev.staff2_kv, patch)
                if diff:
                    ops.append(EditOp(op="update_guqin_event", eid=eid, changes=diff))
                continue

            raise ValueError(f"solution assignment 缺少 choice/choices：eid={eid}")

        if not ops:
            return {
                "project_id": project_id,
                "revision": meta.current_revision,
                "tuning": stage1["tuning"],
                "stage1_warnings": stage1.get("warnings", []),
                "stage2": {"k": req.k, "solutions": [s.__dict__ for s in sols]},
                "commit": {"skipped": True, "reason": "no_ops_after_filters_or_no_changes"},
            }

        xml2 = apply_edit_ops(musicxml_bytes=xml_bytes, ops=ops, edit_source="auto")
        delta_ops = [
            {
                "op": "stage2_commit_best",
                "solution_id": sol0.solution_id,
                "k": req.k,
                "written_ops": [{"op": o.op, "eid": o.eid, "changes": o.changes} for o in ops],
            }
        ]
        new_meta = save_new_revision(
            project_id=project_id,
            base_revision=meta.current_revision,
            musicxml_bytes=xml2,
            delta_ops=delta_ops,
            message=req.message or "stage2 commit_best",
        )
        view2 = build_score_view(project_id=project_id, revision=new_meta.current_revision, musicxml_bytes=xml2)
        return {
            "project_id": project_id,
            "revision": meta.current_revision,
            "tuning": stage1["tuning"],
            "stage1_warnings": stage1.get("warnings", []),
            "stage2": {"k": req.k, "solutions": [s.__dict__ for s in sols]},
            "commit": {"project": asdict(new_meta), "score": asdict(view2)},
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/projects/{project_id}/tuning")
def api_get_tuning(project_id: str) -> dict[str, Any]:
    meta = load_project_meta(project_id)
    return meta.tuning.to_dict()


class UpdateTuningRequest(BaseModel):
    tuning: Stage1Tuning


@app.put("/projects/{project_id}/tuning")
def api_put_tuning(project_id: str, req: UpdateTuningRequest) -> dict[str, Any]:
    meta = load_project_meta(project_id)
    new_tuning = ProjectTuning.from_dict(req.tuning.model_dump())
    new_meta = ProjectMeta(
        project_id=meta.project_id,
        name=meta.name,
        created_at=meta.created_at,
        current_revision=meta.current_revision,
        tuning=new_tuning,
    )
    save_project_meta(new_meta)
    return asdict(new_meta)
