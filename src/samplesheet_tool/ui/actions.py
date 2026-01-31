# actions.py
# response to actions
# 

from __future__ import annotations

from typing import List, Optional, Iterable, Set, Dict, Tuple
from nicegui import ui
from pathlib import Path

from samplesheet_tool.ui.state import (
    RunState, 
    LaneStatus, 
    Project, 
    Sample, 
    Message, MessageLevel, 
    IndexMappingType, 
    save_plan, load_plan,
    make_sample_uid, split_sample_uid, 
    save_index_preset
)

from samplesheet_tool.ui.project_io import import_project_from_file

# -------------------------
# Messages (persistent)
# -------------------------

def push_message(
    state: RunState, 
    level: MessageLevel, 
    text: str, 
    *,
    source: str = "", 
    lane: Optional[int] = None, 
    project_id: Optional[str] = None, 
    sample_id: Optional[str] = None, 
) -> None:
    """Push a new message"""
    state.messages.append(
        Message(
            level = level, 
            text = text, 
            source = source, 
            lane = lane, 
            project_id = project_id, 
            sample_id = sample_id, 
        )
    )

def clear_messages(state: RunState, *, source: Optional[str] = None) -> None:
    """Clear messages (optionally only for a given source)."""
    if source is None:
        state.messages.clear()
        return
    state.messages = [m for m in state.messages if m.source != source]

# -------------------------
# Index mapping import (mock, but follows spec rules)
# -------------------------

def import_mapping_table_from_text(
    state: RunState, 
    mapping_type: IndexMappingType, 
    raw_text: str,
    *,
    filename: str = "(uploaded)", 
    delimiter: Optional[str] = None,
) -> bool:
    """Import a mapping table from uploaded text.

    Atomic per-file (spec-compliant):
      - duplicate index_id with same sequences -> WARNING, keep existing
      - duplicate index_id with different sequences -> ERROR, do NOT merge anything
      - format/required columns errors -> ERROR, do NOT merge anything

    MVP parsing: CSV/TSV with a header row.
      - dual: index_id, i7, i5
      - single: index_id, sequence
    """
    # Keep messages persistent, but clear previous index-import messages to reduce noise during iterative testing.
    clear_messages(state, source="index_import")

    text = (raw_text or "").strip()
    if not text:
        push_message(state, "error", f"Index import failed: empty file ({filename})", source="index_import")
        return False

    # Infer delimiter
    if delimiter is None:
        first = text.splitlines()[0]
        delimiter = "\t" if "\t" in first else ","

    lines = [ln for ln in text.splitlines() if ln.strip()]
    header = [h.strip() for h in lines[0].split(delimiter)]

    def idx_of(col: str) -> int:
        return header.index(col) if col in header else -1

    required = ["index_id", "i7", "i5"] if mapping_type == "dual" else ["index_id", "sequence"]
    missing = [c for c in required if idx_of(c) < 0]
    if missing:
        push_message(
            state,
            "error",
            f"Index import failed ({filename}): missing column(s): {', '.join(missing)}",
            source="index_import",
        )
        return False

    # Parse rows
    parsed: List[Tuple[str, Dict[str, str]]] = []
    for ln_no, ln in enumerate(lines[1:], start=2):
        parts = [p.strip() for p in ln.split(delimiter)]
        if len(parts) < len(header):
            push_message(state, "error", f"Index import failed ({filename}): line {ln_no} has too few columns", source="index_import")
            return False

        index_id = parts[idx_of("index_id")]
        if not index_id:
            push_message(state, "error", f"Index import failed ({filename}): line {ln_no} missing index_id", source="index_import")
            return False

        if mapping_type == "dual":
            i7 = parts[idx_of("i7")]
            i5 = parts[idx_of("i5")]
            if not i7 or not i5:
                push_message(state, "error", f"Index import failed ({filename}): line {ln_no} missing i7/i5", source="index_import")
                return False
            parsed.append((index_id, {"i7": i7, "i5": i5}))
        else:
            seq = parts[idx_of("sequence")]
            if not seq:
                push_message(state, "error", f"Index import failed ({filename}): line {ln_no} missing sequence", source="index_import")
                return False
            parsed.append((index_id, {"sequence": seq}))

    # Validate conflicts BEFORE mutating state (atomic)
    if mapping_type == "dual":
        existing = state.index_tables.dual
        for index_id, rec in parsed:
            if index_id in existing and existing[index_id] != rec:
                push_message(
                    state,
                    "error",
                    f"Index import failed ({filename}): index_id '{index_id}' conflicts with existing mapping",
                    source="index_import",
                )
                return False
    else:
        existing = state.index_tables.single
        for index_id, rec in parsed:
            seq = rec["sequence"]
            if index_id in existing and existing[index_id] != seq:
                push_message(
                    state,
                    "error",
                    f"Index import failed ({filename}): index_id '{index_id}' conflicts with existing mapping",
                    source="index_import",
                )
                return False

    # Merge
    dup_n = 0
    add_n = 0
    if mapping_type == "dual":
        for index_id, rec in parsed:
            if index_id in state.index_tables.dual:
                dup_n += 1
                continue
            state.index_tables.dual[index_id] = rec
            add_n += 1
    else:
        for index_id, rec in parsed:
            seq = rec["sequence"]
            if index_id in state.index_tables.single:
                dup_n += 1
                continue
            state.index_tables.single[index_id] = seq
            add_n += 1

    if dup_n:
        push_message(
            state,
            "warning",
            f"Index import warning ({filename}): {dup_n} duplicate ID(s) already present (kept existing)",
            source="index_import",
        )

    # persist merged index tables as preset
    save_index_preset(state)

    ui.notify(f"Loaded mapping table: +{add_n} IDs ({mapping_type})", type="positive")
    return True


# -------------------------
# Project import
# -------------------------

def import_project(
    *,
    state: RunState,
    project_id: str,
    index_type: str,
    library_type: Optional[str],
    file_path: Path,
    default_required_reads_m: Optional[int],
) -> Project:
    """
    Atomic project import:
    - parse + validate file
    - commit into RunState
    """
    proj = import_project_from_file(
        state=state,
        project_id=project_id,
        index_type=index_type,
        library_type=library_type,
        file_path=file_path,
        default_required_reads_m=default_required_reads_m,
    )

    state.projects[project_id] = proj
    state.selected_project_id = project_id

    save_plan(state)
    
    return proj

def remove_project(state: RunState, project_id: str) -> None:
    if project_id not in state.projects:
        return

    ## remove from lanes
    #for lane in state.lanes.values():
    #    lane.sample_uids = [
    #        uid for uid in lane.sample_uids if split_sample_uid(uid)[0] != project_id
    #    ]
    #    lane.project_ids = [
    #        pid for pid in lane.project_ids if pid != project_id
    #    ]

    del state.projects[project_id]

    if state.selected_project_id == project_id:
        state.selected_project_id = next(iter(state.projects), None)

    save_plan(state)


# -------------------------
# Lane operations + mock validation
# -------------------------

def lane_recompute_mock(state: RunState, lane_id: int) -> None:
    """Mock lane validation.

    UI spec: Lane Panel shows summary only; Messages Panel holds details.
    We therefore:
      - set lane.status + lane.headline (summary)
      - write duplicate details as messages (lane_validation)
    """
    # Clear previous lane validation messages for this lane
    state.messages = [m for m in state.messages if not (m.source == "lane_validation" and m.lane == lane_id)]

    lane = state.lanes[lane_id]

    # simple rule A: duplicate sample_id within a lane --> ERROR
    seen: Set[str] = set()
    dups: List[str] = []
    sample_ids = [split_sample_uid(x)[1] for x in lane.sample_uids]
    for sid in sample_ids:
        if sid in seen:
            dups.append(sid)
        seen.add(sid)

    # simple rule B:  > 40 samples -> warning
    too_many = len(lane.sample_uids) > 40

    if dups:
        lane.status = LaneStatus.ERROR
        lane.headline = f"Duplicate sample_id ({len(dups)})"
        lane.details = [] # keep lane clean, details go to Messages panel
        for sid in dups[:50]:
            push_message(
                state,
                "error",
                f"Duplicate sample_id in lane {lane_id}: {sid}",
                source="lane_validation",
                lane=lane_id,
                sample_id=sid,
            )
        return

    if too_many:
        lane.status = LaneStatus.WARNING
        lane.headline = f"High sample count (samples={len(lane.sample_uids)})"
        lane.details = []
        push_message(
            state,
            "warning",
            f"Lane {lane_id} has a high sample count: {len(lane.sample_uids)}",
            source="lane_validation",
            lane=lane_id,
        )
        return

    lane.status = LaneStatus.OK
    lane.headline = ""
    lane.details = []


def add_samples_to_lanes(
    state: RunState,
    sample_uids: List[str],
    lane_ids: List[int],
) -> None:
    """
    - Implicit fix: same (project_id, sample_id) already in SAME lane -> skip
    - Same sample across multiple lanes is allowed (increase depth)
    """
    # append syntax: remove redundant samples within a lane (automatically)
    if not sample_uids or not lane_ids:
        return

    for lid in lane_ids:
        lane = state.lanes[lid]
        existing = set(lane.sample_uids)
        for uid in sample_uids:
            if uid in existing:
                continue
            lane.sample_uids.append(uid)
            existing.add(uid)

            pid, _sid = split_sample_uid(uid)
            if pid and pid not in lane.project_ids:
                lane.project_ids.append(pid)

        lane_recompute_mock(state, lid)


def remove_project_from_lane(state: RunState, lane_id: int, project_id: str) -> None:
    lane = state.lanes[lane_id]
    if project_id not in lane.project_ids:
        return

    lane.sample_uids = [uid for uid in lane.sample_uids if split_sample_uid(uid)[0] != project_id]
    lane.project_ids = [pid for pid in lane.project_ids if pid != project_id]
    lane_recompute_mock(state, lane_id)


def clear_lane(state: RunState, lane_id: int) -> None:
    lane = state.lanes[lane_id]
    lane.sample_uids.clear()
    lane.project_ids.clear()
    lane_recompute_mock(state, lane_id)


def validate_full_mock(state: RunState) -> None:
    """
    Final validation (mock) per your rules:
    A) same (project_id, sample_id) across lanes -> allowed
    B) same sample_id across projects -> ERROR
    C) duplicate sample_id within same project -> ERROR
    """
    # mock: re-compute for all lanes
    for lid in state.lanes:
        lane_recompute_mock(state, lid)

    # BUGs includes!!!
    # this is NOT right, the validation should be done within each lane, 
    # not necessarily across all projects, since not all projects are used in lanes
    errors: List[str] = []

    # C
    for pid, proj in state.projects.items():
        seen = set()
        for s in proj.samples:
            if s.sample_id in seen:
                push_message(
                    state,
                    "error",
                    f"Duplicate sample_id within project {pid}: {s.sample_id}.",
                    source="lane_validation",
                    sample_id=s.sample_id,
                    project_id=pid,
                )
                errors.append(f"Duplicate sample_id within project {pid}: {s.sample_id}")
            seen.add(s.sample_id)

    # B
    sid_to_projects: dict[str, set[str]] = {}
    for pid, proj in state.projects.items():
        for s in proj.samples:
            sid_to_projects.setdefault(s.sample_id, set()).add(pid)
    for sid, pset in sid_to_projects.items():
        if len(pset) > 1:
            errors.append(f"sample_id used in multiple projects: {sid} -> {sorted(pset)}")

    if errors:
        # 暂时用“所有 lanes 标红 + details”来呈现全局错误（以后可替换成 Messages panel）
        for lid in state.lanes:
            lane = state.lanes[lid]
            lane.status = LaneStatus.ERROR
            lane.headline = "Sample naming error"
            lane.details = errors[:8]


# -------------------------
# Export gating (mock)
# -------------------------

def has_any_data(state: RunState) -> bool:
    if not state.projects:
        return False
    return any(len(l.sample_uids) > 0 for l in state.lanes.values())

def can_export(state: RunState) -> bool:
    if not has_any_data(state):
        return False
    return all(l.status != LaneStatus.ERROR for l in state.lanes.values())

