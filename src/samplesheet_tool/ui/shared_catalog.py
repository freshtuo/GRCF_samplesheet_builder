from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4
import re

from samplesheet_tool.ui.state import IndexTables, Project, Sample, SharedCatalog


def _utc_now_iso() -> str:
    """Return a compact UTC timestamp for shared catalog metadata."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def shared_indexes_path(shared_dir: Path) -> Path:
    """Path to the shared indexes JSON file."""
    return shared_dir / "indexes.json"


def shared_projects_dir(shared_dir: Path) -> Path:
    """Directory containing one JSON file per shared project."""
    return shared_dir / "projects"


def shared_project_path(shared_dir: Path, project_id: str) -> Path:
    """Path for a single shared project file."""
    return shared_projects_dir(shared_dir) / f"{project_id}.json"


def read_json_file(path: Path) -> Any:
    """Read and decode a UTF-8 JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_tmp_label(value: str | None) -> str:
    """Convert an optional label into a filesystem-safe temp-file fragment."""
    text = (value or "").strip()
    if not text:
        return "unknown"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return safe or "unknown"


def atomic_write_json(path: Path, payload: Any, *, user_name: str | None = None) -> Path:
    """Write JSON via a unique temp file then replace the target to avoid partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    user_tag = _safe_tmp_label(user_name)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    tmp = path.with_name(f"{path.name}.{user_tag}.{ts}.{uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def _project_to_payload(project: Project, *, user_name: str | None = None) -> dict[str, Any]:
    """Serialize a Project plus shared-catalog metadata fields."""
    payload = asdict(project)
    payload["updated_at"] = _utc_now_iso()
    if user_name:
        payload["updated_by"] = user_name
    return payload


def _project_from_payload(data: dict[str, Any]) -> Project:
    """Build an in-memory Project from a shared project JSON payload."""
    samples = [Sample(**sample) for sample in data.get("samples", [])]
    return Project(
        project_id=str(data.get("project_id", "")).strip(),
        samples=samples,
        library_type=data.get("library_type"),
        index_type=data.get("index_type", "dual"),
        sequencing_type=data.get("sequencing_type", ""),
    )


def load_shared_catalog(shared_dir: Path | None) -> SharedCatalog:
    """Load shared indexes and project files from the configured shared directory."""
    catalog = SharedCatalog()
    if shared_dir is None:
        return catalog

    indexes_path = shared_indexes_path(shared_dir)
    if indexes_path.exists():
        data = read_json_file(indexes_path)
        catalog.index_tables.dual = dict(data.get("dual", {}))
        catalog.index_tables.single = dict(data.get("single", {}))
        catalog.indexes_updated_at = data.get("updated_at")
        catalog.indexes_updated_by = data.get("updated_by")

    projects_dir = shared_projects_dir(shared_dir)
    if projects_dir.exists():
        for path in sorted(projects_dir.glob("*.json")):
            data = read_json_file(path)
            project = _project_from_payload(data)
            if not project.project_id:
                continue
            catalog.projects[project.project_id] = project
            catalog.project_updated_at[project.project_id] = str(data.get("updated_at", "") or "")

    catalog.last_loaded_at = _utc_now_iso()
    return catalog


def save_shared_indexes(
    shared_dir: Path,
    index_tables: IndexTables,
    *,
    user_name: str | None = None,
) -> Path:
    """Persist the merged shared index tables to indexes.json."""
    payload: dict[str, Any] = {
        "updated_at": _utc_now_iso(),
        "dual": index_tables.dual,
        "single": index_tables.single,
    }
    if user_name:
        payload["updated_by"] = user_name
    return atomic_write_json(
        shared_indexes_path(shared_dir),
        payload,
        user_name=user_name,
    )


def save_shared_project(
    shared_dir: Path,
    project: Project,
    *,
    user_name: str | None = None,
) -> Path:
    """Persist one project to its own shared JSON file."""
    return atomic_write_json(
        shared_project_path(shared_dir, project.project_id),
        _project_to_payload(project, user_name=user_name),
        user_name=user_name,
    )


def delete_shared_project(shared_dir: Path, project_id: str) -> bool:
    """Delete one shared project file; return False if it is already gone."""
    path = shared_project_path(shared_dir, project_id)
    if not path.exists():
        return False
    path.unlink()
    return True
