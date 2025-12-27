"""
后端 workspace（文件夹）管理：项目、revision、delta。

约定（backend/workspace 下）：

每个项目一个目录：

backend/workspace/{project_id}/
  project.json
  revisions/
    R000001.musicxml
    R000002.musicxml
    ...
  deltas/
    D000001.json
    D000002.json
    ...

说明：
- 当前阶段使用文件夹管理，未来可迁移到 sqlite（元数据与索引），但文件结构保持可迁移性。
- 每次编辑产生一个新 revision（完整快照），同时记录一份 delta（操作级别）。
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import examples_dir, workspace_root


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _read_json(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, obj: dict[str, Any]) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class ProjectTuning:
    """项目调弦配置（绝对音高，便于 stage1 查表/枚举）。"""

    name: str
    open_pitches_midi: tuple[int, ...]  # len=7, string 1..7
    transpose_semitones: int = 0

    @staticmethod
    def default_demo() -> "ProjectTuning":
        # 参考常见示例：g, a, c d e g a（用 MIDI 近似表达）
        return ProjectTuning(name="demo_g_a_c_d_e_g_a", open_pitches_midi=(55, 57, 60, 62, 64, 67, 69), transpose_semitones=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "open_pitches_midi": list(self.open_pitches_midi),
            "transpose_semitones": int(self.transpose_semitones),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "ProjectTuning":
        if not d:
            return cls.default_demo()
        name = str(d.get("name") or "custom")
        open_pitches = d.get("open_pitches_midi")
        if not isinstance(open_pitches, list) or len(open_pitches) != 7:
            raise ValueError("tuning.open_pitches_midi 必须是长度为 7 的数组")
        open_pitches_t = tuple(int(x) for x in open_pitches)
        transpose = int(d.get("transpose_semitones") or 0)
        return cls(name=name, open_pitches_midi=open_pitches_t, transpose_semitones=transpose)


@dataclass(frozen=True)
class ProjectMeta:
    project_id: str
    name: str
    created_at: str
    updated_at: str
    current_revision: str
    tuning: ProjectTuning


def generate_project_id() -> str:
    return "P" + secrets.token_hex(8)


def project_dir(project_id: str) -> Path:
    return workspace_root() / project_id


def project_meta_path(project_id: str) -> Path:
    return project_dir(project_id) / "project.json"


def revisions_dir(project_id: str) -> Path:
    return project_dir(project_id) / "revisions"


def deltas_dir(project_id: str) -> Path:
    return project_dir(project_id) / "deltas"


def ensure_project_dirs(project_id: str) -> None:
    _ensure_dir(project_dir(project_id))
    _ensure_dir(revisions_dir(project_id))
    _ensure_dir(deltas_dir(project_id))


def list_projects() -> list[ProjectMeta]:
    root = workspace_root()
    _ensure_dir(root)
    out: list[ProjectMeta] = []
    for p in sorted(root.iterdir()):
        if not p.is_dir():
            continue
        meta_p = p / "project.json"
        if not meta_p.exists():
            continue
        d = _read_json(meta_p)
        out.append(
            ProjectMeta(
                project_id=d["project_id"],
                name=d["name"],
                created_at=d["created_at"],
                updated_at=str(d.get("updated_at") or d["created_at"]),
                current_revision=d["current_revision"],
                tuning=ProjectTuning.from_dict(d.get("tuning")),
            )
        )
    return out


def load_project_meta(project_id: str) -> ProjectMeta:
    d = _read_json(project_meta_path(project_id))
    return ProjectMeta(
        project_id=d["project_id"],
        name=d["name"],
        created_at=d["created_at"],
        updated_at=str(d.get("updated_at") or d["created_at"]),
        current_revision=d["current_revision"],
        tuning=ProjectTuning.from_dict(d.get("tuning")),
    )


def save_project_meta(meta: ProjectMeta) -> None:
    _write_json(
        project_meta_path(meta.project_id),
        {
            "project_id": meta.project_id,
            "name": meta.name,
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
            "current_revision": meta.current_revision,
            "tuning": meta.tuning.to_dict(),
        },
    )


def next_revision_id(prev_revision: str | None) -> str:
    if prev_revision is None:
        return "R000001"
    if not prev_revision.startswith("R"):
        raise ValueError(f"非法 revision：{prev_revision}")
    n = int(prev_revision[1:])
    return f"R{n+1:06d}"


def next_delta_id(prev_delta: str | None) -> str:
    if prev_delta is None:
        return "D000001"
    if not prev_delta.startswith("D"):
        raise ValueError(f"非法 delta：{prev_delta}")
    n = int(prev_delta[1:])
    return f"D{n+1:06d}"


def _latest_id_in_dir(dir_path: Path, prefix: str, suffix: str) -> str | None:
    if not dir_path.exists():
        return None
    best: tuple[int, str] | None = None
    for p in dir_path.glob(f"{prefix}*{suffix}"):
        name = p.name
        if not name.startswith(prefix) or not name.endswith(suffix):
            continue
        mid = name[len(prefix) : -len(suffix)]
        if not mid.isdigit():
            continue
        n = int(mid)
        if best is None or n > best[0]:
            best = (n, f"{prefix}{mid}")
    return best[1] if best else None


def create_project_from_example(*, name: str, example_filename: str, tuning: ProjectTuning | None = None) -> ProjectMeta:
    ex_path = examples_dir() / example_filename
    if not ex_path.exists():
        raise FileNotFoundError(str(ex_path))

    project_id = generate_project_id()
    ensure_project_dirs(project_id)

    revision = next_revision_id(None)
    rev_path = revisions_dir(project_id) / f"{revision}.musicxml"
    rev_path.write_bytes(ex_path.read_bytes())

    now = _utc_now_iso()
    meta = ProjectMeta(
        project_id=project_id,
        name=name,
        created_at=now,
        updated_at=now,
        current_revision=revision,
        tuning=tuning or ProjectTuning.default_demo(),
    )
    save_project_meta(meta)
    return meta


def load_revision_bytes(project_id: str, revision: str) -> bytes:
    p = revisions_dir(project_id) / f"{revision}.musicxml"
    if not p.exists():
        raise FileNotFoundError(str(p))
    return p.read_bytes()


def save_new_revision(*, project_id: str, base_revision: str, musicxml_bytes: bytes, delta_ops: list[dict[str, Any]], message: str | None) -> ProjectMeta:
    meta = load_project_meta(project_id)
    if meta.current_revision != base_revision:
        raise ValueError(f"revision 冲突：current={meta.current_revision} base={base_revision}")

    prev_delta = _latest_id_in_dir(deltas_dir(project_id), "D", ".json")
    new_delta = next_delta_id(prev_delta)
    delta_path = deltas_dir(project_id) / f"{new_delta}.json"
    _write_json(
        delta_path,
        {
            "delta_id": new_delta,
            "created_at": _utc_now_iso(),
            "base_revision": base_revision,
            "message": message,
            "ops": delta_ops,
        },
    )

    new_revision = next_revision_id(base_revision)
    rev_path = revisions_dir(project_id) / f"{new_revision}.musicxml"
    rev_path.write_bytes(musicxml_bytes)

    new_meta = ProjectMeta(
        project_id=meta.project_id,
        name=meta.name,
        created_at=meta.created_at,
        updated_at=_utc_now_iso(),
        current_revision=new_revision,
        tuning=meta.tuning,
    )
    save_project_meta(new_meta)
    return new_meta
