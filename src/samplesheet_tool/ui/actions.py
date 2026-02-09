# actions.py
# response to actions
# 

from __future__ import annotations

from typing import List, Optional, Iterable, Set, Dict, Tuple
from nicegui import ui
from pathlib import Path

from collections import defaultdict

import pandas as pd

from samplesheet_tool.ui.state import (
    RunState, 
    LaneStatus, 
    Project, 
    Sample, 
    Message, MessageLevel, 
    ValidationResult, 
    IndexMappingType, 
    save_plan, load_plan, default_store_dir, 
    make_sample_uid, split_sample_uid, 
    save_index_preset
)

from samplesheet_tool.ui.project_io import import_project_from_file

from samplesheet_tool.config import (
    COL_LANE, COL_SAMPLE_ID, COL_PROJECT_ID, COL_I7_ID, COL_I5_ID, COL_I7, COL_I5, DEFAULT_LANE_CAPACITY_M
)

from samplesheet_tool.io_normalize import check_required_columns, normalize_minimal
from samplesheet_tool.validate import validate_all

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

def rebuild_lanes_from_assignments(state: RunState) -> None:
    """Sync lane.sample_uids and lane.project_ids from state.assignments (truth)."""
    for lane in state.lanes.values():
        lane.sample_uids = []
        lane.project_ids = []

    for uid, per_lane in state.assignments.items():
        pid, _sid = split_sample_uid(uid)
        for lid in per_lane.keys():
            lane = state.lanes.get(int(lid))
            if not lane:
                continue
            if uid not in lane.sample_uids:
                lane.sample_uids.append(uid)
            if pid and pid not in lane.project_ids:
                lane.project_ids.append(pid)


def lane_local_validate(state: RunState, lane_id: int) -> None:
    """
    Lane-local validation.

    Only checks conditions that can be determined within a single lane:
      - duplicate sample_id
      - duplicate index
      - reads overflow

    Lane Panel shows summary only;
    Messages Panel holds detailed messages.
    """
    # Clear previous lane validation messages for this lane
    state.messages = [
        m for m in state.messages 
        if not (m.source == "lane_validation" and m.lane == lane_id)
    ]

    # fetch lane object
    lane = state.lanes[lane_id]

    # default reset (will be upgraded if any issue found)
    lane.status = LaneStatus.OK
    lane.headline = ""
    lane.details = []

    # --------------------------------------------------
    # Rule 1: duplicate sample_id within the lane -> ERROR
    # --------------------------------------------------
    seen_samples: Set[str] = set()
    dup_samples: Set[str] = set()

    for uid in lane.sample_uids:
        _, sid = split_sample_uid(uid)
        if sid in seen_samples:
            dup_samples.add(sid)
        else:
            seen_samples.add(sid)

    if dup_samples:
        lane.status = LaneStatus.ERROR
        lane.headline = f"Duplicate sample_id ({len(dup_samples)})"
        lane.details = [] # keep lane clean, details go to Messages panel

        for sid in sorted(dup_samples):
            push_message(
                state,
                "error",
                f"Duplicate sample_id in lane {lane_id}: {sid}",
                source="lane_validation",
                lane=lane_id,
                sample_id=sid,
            )

        # fatal for this lane; no need to continue checking others
        return

    # --------------------------------------------------
    # Rule 2: duplicate index within the lane -> ERROR
    # --------------------------------------------------
    seen_indexes: Set[tuple] = set()
    dup_indexes: Set[tuple] = set()

    for uid in lane.sample_uids:
        pid, sid = split_sample_uid(uid)
        proj = state.projects.get(pid)
        if not proj:
            continue

        sample = next(
            (s for s in proj.samples if s.sample_id == sid), 
            None, 
        )
        if not sample:
            continue

        # index key: (i7, i5) or just (i7,) depending on data model
        idx_key = (sample.i7_seq, sample.i5_seq)

        if idx_key in seen_indexes:
            dup_indexes.add(idx_key)
        else:
            seen_indexes.add(idx_key)

    if dup_indexes:
        lane.status = LaneStatus.ERROR
        lane.headline = f"Duplicate index ({len(dup_indexes)})"

        for idx in sorted(dup_indexes):
            push_message(
                state,
                "error",
                f"Duplicate index in lane {lane_id}: i7={idx[0]}, i5={idx[1]}",
                source="lane_validation",
                lane=lane_id,
            )

        # fatal for this lane; no need to continue checking others
        return

    # --------------------------------------------------
    # Rule 3: reads overflow -> ERROR
    # --------------------------------------------------
    used = sum(
        state.assignments.get(uid, {}).get(lane_id, 0)
        for uid in lane.sample_uids
    )
    if used > DEFAULT_LANE_CAPACITY_M:
        lane.status = LaneStatus.ERROR
        lane.headline = f"Reads overflow ({used} > {DEFAULT_LANE_CAPACITY_M} M)"

        push_message(
            state, 
            "error",
            f"Lane {lane_id} exceeds capacity: {used} > {DEFAULT_LANE_CAPACITY_M} M",
            source="lane_validation",
            lane=lane_id,
        )

        return

    # --------------------------------------------------
    # If we reach here, lane is clean
    # --------------------------------------------------
    lane.status = LaneStatus.OK
    lane.headline = ""
    lane.details = []


def assign_samples_to_lanes(
    state: RunState,
    sample_uids: List[str],
    lane_ids: List[int],
    planned_reads_m: int,
) -> None:
    """
    Phase1:
    - store assignment reads at state.assignments[sample_uid][lane_id] = planned_reads_m
    - sync lane.sample_uids/project_ids (cache)
    - autosave plan
    """
    if not sample_uids or not lane_ids:
        return
    if planned_reads_m is None or int(planned_reads_m) <= 0:
        raise ValueError("planned_reads_m must be > 0")

    pr = int(planned_reads_m)
    for uid in sample_uids:
        state.assignments.setdefault(uid, {})
        for lid in lane_ids:
            state.assignments[uid][int(lid)] = pr

    rebuild_lanes_from_assignments(state)

    # keep existing lane mock validation for now
    for lid in lane_ids:
        lane_local_validate(state, int(lid))

    save_plan(state)


def remove_project_from_lane(state: RunState, lane_id: int, project_id: str) -> None:
    # remove assignments in this lane for samples belonging to project
    lane_id = int(lane_id)
    to_del: List[str] = []
    for uid, per_lane in state.assignments.items():
        pid, _sid = split_sample_uid(uid)
        if pid != project_id:
            continue
        if lane_id in per_lane:
            del per_lane[lane_id]
        if not per_lane:
            to_del.append(uid)

    for uid in to_del:
        del state.assignments[uid]

    rebuild_lanes_from_assignments(state)
    lane_local_validate(state, lane_id)
    save_plan(state)


def clear_lane(state: RunState, lane_id: int) -> None:
    # remove all projects from a lane, empty it!
    lane_id = int(lane_id)

    # remove all assignments pointing to this lane
    to_del: List[str] = []
    for uid, per_lane in state.assignments.items():
        if lane_id in per_lane:
            del per_lane[lane_id]
        if not per_lane:
            to_del.append(uid)

    for uid in to_del:
        del state.assignments[uid]

    rebuild_lanes_from_assignments(state)
    lane_local_validate(state, lane_id)
    save_plan(state)


# -------------------------
# Project / Sample summary
# -------------------------

def get_projects_in_plan(state: RunState) -> set[str]:
    """Return project_ids that actually appear in the current sequencing plan."""
    projects = set()
    for uid in state.assignments.keys():
        pid, _ = split_sample_uid(uid)
        if pid:
            projects.add(pid)
    return projects


def build_sample_summary_rows(state: RunState, project_filter: str = "All"):
    """
    project × sample
        required / allocated / remaining / status / lanes
    based ONLY on current plan (assignments).
    """
    rows = []

    # collect all (project, sample) pairs that appear in assignments
    sample_map = {}  # (pid, sid) -> {lane: reads}
    for uid, per_lane in state.assignments.items():
        pid, sid = split_sample_uid(uid)
        if not pid:
            continue
        sample_map.setdefault((pid, sid), {})
        for lane_id, reads in per_lane.items():
            sample_map[(pid, sid)][lane_id] = int(reads)

    for (pid, sid), per_lane in sample_map.items():
        if project_filter != "All" and pid != project_filter:
            continue

        # lookup required_reads from project metadata (catalog only)
        proj = state.projects.get(pid)
        sample = None
        if proj:
            sample = next((s for s in proj.samples if s.sample_id == sid), None)

        required = int(sample.required_reads_m) if sample and sample.required_reads_m else 0
        allocated = sum(per_lane.values())
        raw_remaining = required - allocated
        remaining = max(raw_remaining, 0) # raw_remaining < 0 indicates no more additional reads required.

        if raw_remaining == 0:
            status = "OK"
        elif raw_remaining > 0:
            status = "Under"
        else:
            status = "Over"

        lanes = ",".join(str(l) for l in sorted(per_lane.keys()))

        rows.append({
            "key": f"{pid}::{sid}", 
            "project": pid,
            "sample": sid,
            "required": required,
            "allocated": allocated,
            "remaining": remaining,
            "status": status,
            "lanes": lanes,
        })

    return rows


def build_assignment_detail_rows(state: RunState, project_filter: str = "All"):
    """
    project × sample x lane
        planned_reads_m
    based ONLY on current plan (assignments).
    """
    rows = []

    for uid, per_lane in state.assignments.items():
        pid, sid = split_sample_uid(uid)
        if project_filter != "All" and pid != project_filter:
            continue

        for lane_id, reads in per_lane.items():
            rows.append({
                "key": f"{pid}::{sid}::lane{lane_id}",
                "project": pid,
                "sample": sid,
                "lane": lane_id,
                "planned_reads": int(reads),
            })

    return rows


def build_project_summary_rows(state: RunState, project_filter: str = "All"):
    """
    project
        n_samples / total_reads_m / lanes
    based ONLY on current plan (assignments).
    """
    proj_reads = defaultdict(int)
    proj_samples = defaultdict(set)
    proj_lanes = defaultdict(set)

    for uid, per_lane in state.assignments.items():
        pid, sid = split_sample_uid(uid)
        if project_filter != "All" and pid != project_filter:
            continue

        proj_samples[pid].add(sid)
        for lane_id, reads in per_lane.items():
            proj_reads[pid] += int(reads)
            proj_lanes[pid].add(lane_id)

    rows = []
    for pid in sorted(proj_samples.keys()):
        rows.append({
            "key": pid,
            "project": pid,
            "n_samples": len(proj_samples[pid]),
            "total_allocated_reads": proj_reads[pid],
            "lanes": ",".join(str(x) for x in sorted(proj_lanes[pid])),
        })
    return rows


# ============================================================
# Validation & Export
# ============================================================

PROBLEM_LEVEL_TO_LANE_STATUS = {
    "ERROR": LaneStatus.ERROR,
    "WARN": LaneStatus.WARNING,
    "INFO": LaneStatus.OK, 
}

class PlanIntegrityError(RuntimeError):
    """Raised when lanes reference projects/samples removed from state.projects."""
    pass


def _iter_plan_samples(state: RunState):
    """
    Yield (lane_id, project_id, sample_id, Sample|None).
    lanes -> assignments are already synced (assumed true).
    """
    for lane_id, lane in state.lanes.items():
        for uid in lane.sample_uids:
            pid, sid = split_sample_uid(uid)
            proj = state.projects.get(pid)
            sample = None
            if proj is not None:
                sample = next((s for s in proj.samples if s.sample_id == sid), None)
            yield lane_id, pid, sid, sample


def ensure_plan_integrity_or_raise(state: RunState) -> None:
    """
    If any lane references a project/sample not present in Projects panel, raise.
    For case: removing project from projects panel does NOT mutate lanes, so samplesheet build would fail.
    """
    missing_projects = set()
    missing_samples = []  # list of (lane_id, pid, sid)

    for lane_id, pid, sid, sample in _iter_plan_samples(state):
        if pid not in state.projects:
            missing_projects.add(pid)
            missing_samples.append((lane_id, pid, sid))
            continue
        if sample is None:
            missing_samples.append((lane_id, pid, sid))

    if missing_projects or missing_samples:
        msg = (
            "Lane plan references a project/sample that is missing from Projects panel. "
            "Project may have been removed. Please re-import the project to proceed.\n"
        )
        if missing_projects:
            msg += f"Missing project_ids: {sorted(missing_projects)}\n"
        if missing_samples:
            preview = missing_samples[:20]
            msg += "Missing samples (lane, project, sample) examples: " + ", ".join(
                f"({l},{p},{s})" for l, p, s in preview
            )
            if len(missing_samples) > 20:
                msg += f" ... (+{len(missing_samples)-20} more)"
        raise PlanIntegrityError(msg)


def build_samplesheet_df_from_lanes(state: RunState) -> pd.DataFrame:
    """
    Build canonical samplesheet dataframe using lanes as the truth source.
    Uses project metadata to fill index ids/sequences (because lanes only store uid).
    No required_reads logic; no optimization; no auto-fix.
    """
    ensure_plan_integrity_or_raise(state)

    rows = []
    for lane_id, pid, sid, sample in _iter_plan_samples(state):
        # after integrity check, sample should exist
        assert sample is not None

        rows.append({
            COL_LANE: int(lane_id),
            COL_PROJECT_ID: pid,
            COL_SAMPLE_ID: sid,
            COL_I7_ID: sample.i7_id or "",
            COL_I5_ID: sample.i5_id or "",
            COL_I7: sample.i7_seq or "",
            COL_I5: sample.i5_seq or "",
        })

    df = pd.DataFrame(rows, columns=[
        COL_LANE, COL_PROJECT_ID, COL_SAMPLE_ID, COL_I7_ID, COL_I5_ID, COL_I7, COL_I5
    ])

    # even if empty, keep schema
    if df.empty:
        return df

    # schema check + minimal normalization (uppercase seq, strip IDs, lane int)
    check_required_columns(df)
    return normalize_minimal(df)


def cli_validate_samplesheet_file(samplesheet_file: Path) -> ValidationResult:
    """
    CLI is the only judge. This is a small adapter calling existing CLI validate logic.
    """
    df = pd.read_csv(samplesheet_file)
    df = normalize_minimal(df)
    summary = validate_all(df)  # returns ValidationSummary(problems, lane_barcode_mismatches)

    return ValidationResult(
        problems=summary.problems, 
        lane_barcode_mismatches=summary.lane_barcode_mismatches, 
    )


def apply_validation_result_to_lanes(
    state: RunState,
    vr: ValidationResult,
) -> None:
    """
    Final validation is authoritative.
    It may override lane.status set by lane_local_validate.
    Only upgrades risk; never downgrade lane_local_validate results.
    """
    # barcode mismatch -> WARNING
    #   make sure WARNING does NOT override ERROR (never downgrade!!)
    for lid, n in vr.lane_barcode_mismatches.items():
        if n == 0 and lid in state.lanes and state.lanes[lid].status != LaneStatus.ERROR:
            state.lanes[lid].status = LaneStatus.WARNING
    
    # problems override (ERROR > WARNING)
    for p in vr.problems:
        if p.lane is None:
            # run-level problem
            # push_message, no chane on lane.status
            continue

        lane = state.lanes.get(p.lane)
        if not lane:
            continue

        if p.level == "ERROR":
            lane.status = LaneStatus.ERROR
        elif p.level == "WARN" and lane.status != LaneStatus.ERROR:
            lane.status = LaneStatus.WARNING


def infer_project_id_for_problem(
    state: RunState, 
    p: Problem, 
) -> Optional[str]:
    """
    Return:
      - project_id if uniquely identifiable
      - "ambiguous" if multiple projects match
      - None if cannot infer
    """
    if not p.lane or not p.sample_id:
        return None

    lane = state.lanes.get(p.lane)
    if not lane:
        return None

    projects = set()
    for uid in lane.sample_uids:
        pid, sid = split_sample_uid(uid)
        if sid == p.sample_id:
            projects.add(pid)

    if len(projects) == 1:
        return next(iter(projects))
    if len(projects) > 1:
        return "ambiguous"

    return None


def validate_current_plan(state: RunState) -> ValidationResult:
    """
    UI Validate behavior:
      - clear messages panel
      - build samplesheet from lanes
      - write temp CSV
      - call CLI validate(temp_file)
      - write errors/warnings to messages
      - cache to state.validation_result
    """
    # strict: validation clears messages panel
    state.messages.clear()

    try:
        df = build_samplesheet_df_from_lanes(state)
    except PlanIntegrityError as e:
        # write message + cache failed result
        push_message(state, "error", str(e), source="validation")
        res = ValidationResult(errors=[str(e)], warnings=[])
        state.validation_result = res
        save_plan(state)
        return res

    tmp = default_store_dir() / "_tmp_samplesheet_for_validation.csv"
    df.to_csv(tmp, index=False)

    res = cli_validate_samplesheet_file(tmp)

    # update lane status based on validation_result
    apply_validation_result_to_lanes(state, res)

    # check if there's any run-level errors, i.e. lane info missing
    state.has_run_level_error = any(
        p.level == "ERROR" and p.lane is None
        for p in res.problems
    )

    # push validation results to Messages panel
    for p in res.problems:
        # infer project_id based on sample_id
        # return unique project_id or "ambiguous"
        project_id = infer_project_id_for_problem(state, p)

        # push to Messages panel
        push_message(
            state, 
            level=PROBLEM_LEVEL_TO_LANE_STATUS[p.level], 
            text=p.message, 
            source="validation", 
            lane=p.lane, 
            project_id=project_id, 
            sample_id=p.sample_id, 
        )

    state.validation_result = res
    save_plan(state)
    return res


def export_samplesheet(state: RunState) -> Path:
    """
    Export always assumes caller already gated by validation.
    Still re-check plan integrity to avoid crash.
    """
    df = build_samplesheet_df_from_lanes(state)

    out_dir = default_store_dir()
    ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"samplesheet_{ts}.csv"
    df.to_csv(out_path, index=False)

    # validation meta info
    res = state.validation_result

    meta = {
        "ok": res.ok, 
        "errors": res.errors, 
        "warning": res.warnings, 
        "lane_barcode_mismatches": res.lane_barcode_mismatches, 
    }

    meta_path = out_path.with_suffix(".validation.json")
    meta_path.write_text(json.dumps(meta, indent=2))

    return out_path


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

