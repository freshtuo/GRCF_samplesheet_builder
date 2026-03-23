from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4
import re

from samplesheet_tool.ui.state import IndexSet, IndexSets, IndexTables, Project, Sample, SharedCatalog


def utc_now_iso() -> str:
    """Return a compact UTC timestamp for shared catalog metadata."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    payload["updated_at"] = utc_now_iso()
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


def build_flattened_index_tables(index_sets: IndexSets) -> IndexTables:
    """Flatten imported index sets into the lookup tables used by the rest of the app."""
    tables = IndexTables()

    for index_set in index_sets.dual:
        for row in index_set.rows:
            index_id = str(row.get("index_id", "")).strip()
            rec = {
                "i7": str(row.get("i7", "")).strip(),
                "i5": str(row.get("i5", "")).strip(),
            }
            if not index_id:
                continue
            existing = tables.dual.get(index_id)
            if existing and existing != rec:
                raise ValueError(
                    f"Conflicting dual mapping for index_id '{index_id}' across imported index sets"
                )
            tables.dual[index_id] = rec

    for index_set in index_sets.single:
        for row in index_set.rows:
            index_id = str(row.get("index_id", "")).strip()
            seq = str(row.get("sequence", "")).strip()
            if not index_id:
                continue
            existing = tables.single.get(index_id)
            if existing and existing != seq:
                raise ValueError(
                    f"Conflicting single mapping for index_id '{index_id}' across imported index sets"
                )
            tables.single[index_id] = seq

    return tables


def _index_set_from_payload(data: dict[str, Any]) -> IndexSet:
    """Build an IndexSet from JSON payload."""
    rows = data.get("rows") or []
    clean_rows = [dict(row) for row in rows if isinstance(row, dict)]
    return IndexSet(
        set_id=str(data.get("set_id", "")).strip(),
        name=str(data.get("name", "")).strip(),
        rows=clean_rows,
        uploaded_at=data.get("uploaded_at"),
        uploaded_by=data.get("uploaded_by"),
    )


def load_shared_catalog(shared_dir: Path | None) -> SharedCatalog:
    """Load shared indexes and project files from the configured shared directory."""
    catalog = SharedCatalog()
    if shared_dir is None:
        return catalog

    indexes_path = shared_indexes_path(shared_dir)
    if indexes_path.exists():
        data = read_json_file(indexes_path)
        raw_sets = data.get("index_sets") or {}
        catalog.index_sets.dual = [
            _index_set_from_payload(item)
            for item in raw_sets.get("dual", [])
            if isinstance(item, dict)
        ]
        catalog.index_sets.single = [
            _index_set_from_payload(item)
            for item in raw_sets.get("single", [])
            if isinstance(item, dict)
        ]

        raw_flattened = data.get("flattened_indexes") or {}
        if raw_flattened:
            catalog.index_tables.dual = dict(raw_flattened.get("dual", {}))
            catalog.index_tables.single = dict(raw_flattened.get("single", {}))
        else:
            catalog.index_tables = build_flattened_index_tables(catalog.index_sets)

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
            catalog.project_updated_by[project.project_id] = str(data.get("updated_by", "") or "")

    catalog.last_loaded_at = utc_now_iso()
    return catalog


def save_shared_indexes(
    shared_dir: Path,
    index_sets: IndexSets,
    index_tables: IndexTables,
    *,
    user_name: str | None = None,
) -> Path:
    """Persist imported index sets plus flattened lookup tables to indexes.json."""
    payload: dict[str, Any] = {
        "updated_at": utc_now_iso(),
        "index_sets": {
            "dual": [asdict(item) for item in index_sets.dual],
            "single": [asdict(item) for item in index_sets.single],
        },
        "flattened_indexes": {
            "dual": index_tables.dual,
            "single": index_tables.single,
        },
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
