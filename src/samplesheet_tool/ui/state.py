# state.py
# control run state
# 

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Literal, Tuple, Any

import json
import csv
import io

from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

from samplesheet_tool.utils import Problem
from samplesheet_tool.ui.runtime_config import default_config


SAMPLE_UID_SEP = "::"

class LaneStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"

class PlanIntegrityError(RuntimeError):
    """Raised when lanes reference projects/samples removed from the shared catalog."""
    pass

MessageLevel = Literal["error", "warning"]


def default_store_dir() -> Path:
    """Return the default local directory used to store UI data files."""
    # internal tool: under user home directory, can be changed other directories later
    base = Path.home() / ".samplesheet_tool_ui"
    base.mkdir(parents=True, exist_ok=True)
    return base


@dataclass
class Message:
    """
    A persistent message shown in the Messages Panel.
    Keep this small and structured so we can filter/search.
    """
    level: MessageLevel
    text: str
    source: str = "" # e.g. index_import / project_import / lane_validation
    lane: Optional[int] = None
    project_id: Optional[str] = None
    sample_id: Optional[str] = None
    ts: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@dataclass(frozen=True)
class ValidationResult:
    """Result returned by CLI validation."""
    problems: List[Problem] = field(default_factory=list)
    lane_barcode_mismatches: Dict[int, int] = field(default_factory=dict)

    @property
    def errors(self) -> List[Problem]:
        """Return validation problems flagged as errors."""
        return [p for p in self.problems if p.level == "ERROR"]

    @property
    def warnings(self) -> List[Problem]:
        """Return validation problems flagged as warnings."""
        return [p for p in self.problems if p.level == "WARN"]

    @property
    def ok(self) -> bool:
        """Report whether validation completed without any errors."""
        return len(self.errors) == 0


IndexMappingType = Literal["dual", "single"]

@dataclass
class IndexTables:
    """Merged global mapping tables (one per type)."""
    dual: Dict[str, Dict[str, str]] = field(default_factory=dict)  # index_id -> {"i7":..., "i5":...}
    single: Dict[str, str] = field(default_factory=dict)           # index_id -> sequence

    def stats(self) -> Dict[str, int]:
        """Return simple counts for the currently loaded index tables."""
        return {"dual_ids": len(self.dual), "single_ids": len(self.single)}


@dataclass
class SharedCatalog:
    """Shared indexes and shared projects loaded from the team folder."""
    index_tables: IndexTables = field(default_factory=IndexTables)
    projects: Dict[str, "Project"] = field(default_factory=dict)
    last_loaded_at: Optional[str] = None
    indexes_updated_at: Optional[str] = None
    indexes_updated_by: Optional[str] = None


@dataclass
class Sample:
    sample_id: str
    project_id: str

    # index info
    i7_id: Optional[str] = None
    i7_seq: Optional[str] = None
    i5_id: Optional[str] = None
    i5_seq: Optional[str] = None

    # required reads per sample (M)
    required_reads_m: Optional[int] = None


@dataclass
class Project:
    project_id: str
    samples: List[Sample] = field(default_factory=list)
    library_type: Optional[str] = None
    index_type: Literal["single", "dual"] = "dual"
    sequencing_type: str = ""

    @property
    def n_samples(self) -> int:
        """Number of samples in the project"""
        return len(self.samples)

    @property
    def total_required_reads_m(self) -> Optional[int]:
        """
        Calculate the total number of required reads for this project 
        i.e. sum required reads across all samples
        """
        vals = [s.required_reads_m for s in self.samples if s.required_reads_m is not None]
        return sum(vals) if vals else None


@dataclass
class Lane:
    lane_id: int

    # Store unique per-sample key to disambiguate same sample_id in different projects
    # Format: "{project_id}::{sample_id}"
    sample_uids: List[str] = field(default_factory=list)

    # convenience summary (unique project_ids in this lane)
    project_ids: List[str] = field(default_factory=list)

    # Land status (whether or not passing initial check
    status: LaneStatus = LaneStatus.OK
    headline: str = ""
    details: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class SampleSheetRow:
    lane: int
    project_id: str
    sample_id: str
    i7_id: str
    i7_seq: str
    i5_id: str
    i5_seq: str
    sequencing_type: str


class BaseRenderer:
    def render(self, rows: list[SampleSheetRow]) -> str:
        """Convert samplesheet rows into a concrete export format."""
        raise NotImplementedError


class BaseSpaceRenderer(BaseRenderer):
    def render(self, rows: list[SampleSheetRow]) -> str:
        """Render rows in the BaseSpace-compatible CSV format."""
        buf = io.StringIO()
        writer = csv.writer(
            buf, 
            lineterminator="\n",
            quoting=csv.QUOTE_MINIMAL, # automatically add quote to strings containing comma
        )

        # header
        writer.writerow([
            "Lane",
            "Sample_ID",
            "Index",
            "Index2",
            "BarcodeMismatchesIndex1",
            "BarcodeMismatchesIndex2",
            "Sample_Project",
            "Description",
        ])
        
        merged = defaultdict(lambda: {
            "lanes": set(), 
            "row": None, 
        })

        # merge by (project_id, sample_id)
        for r in rows:
            # set key
            key = (r.project_id, r.sample_id)

            # merge lanes
            merged[key]["lanes"].add(r.lane)

            # double check, make sure identical project/sample should share the same sequencing type, otherwise raise an exception
            if merged[key]["row"] and merged[key]["row"].sequencing_type != r.sequencing_type:
                raise PlanIntegrityError(
                    f"Inconsistent sequencing_type for {r.project_id}/{r.sample_id}"
                )
            
            # store 'shared' information
            merged[key]["row"] = r # last one is fine; other fields identical

        for key in sorted(merged.keys()):
            item = merged[key]
            r = item["row"]
            lane_str = ",".join(str(l) for l in sorted(item["lanes"]))

            writer.writerow([
                lane_str, 
                r.sample_id,
                r.i7_seq,
                r.i5_seq or "", # in case single-index, no i5 index
                '1',            # for now, set mismatches to 1 since we still use BaseSpace sequencing planner
                '1',            # for now, set mismatches to 1 since we still use BaseSpace sequencing planner
                r.project_id,
                r.sequencing_type, 
            ])

        return buf.getvalue()


class IEMRenderer(BaseRenderer):
    def __init__(
        self, 
        *, 
        read1: int = 101, 
        read2: int = 101, 
        instrument: str = "NovaSeq", 
        chemistry: str = "Amplicon", 
    ):
        """Store IEM header settings used when rendering output."""
        self.read1 = read1
        self.read2 = read2
        self.instrument = instrument
        self.chemistry = chemistry

    def render(self, rows: list[SampleSheetRow]) -> str:
        """Render rows in the Illumina Experiment Manager CSV format."""
        lines: list[str] = []

        # -------- Header --------
        lines.append("[Header],,,,,,,,,,,")
        lines.append("IEMFileVersion,5,,,,,,,,,,")
        lines.append(f"Date,{date.today().strftime('%m/%d/%Y')},,,,,,,,,,")
        lines.append("Workflow,GenerateFASTQ,,,,,,,,,,")
        lines.append("Application,NovaSeq_FASTQ_Only,,,,,,,,,,")
        lines.append(f"Instrument_Type,{self.instrument},,,,,,,,,,")
        lines.append(f"Chemistry,{self.chemistry},,,,,,,,,,")
        lines.append(",,,,,,,,,,,")

        # -------- Reads --------
        lines.append("[Reads],,,,,,,,,,,")
        lines.append(f"{self.read1},,,,,,,,,,,")
        lines.append(f"{self.read2},,,,,,,,,,,")
        lines.append(",,,,,,,,,,,")

        # -------- Settings --------
        lines.append("[Settings],,,,,,,,,,,")
        lines.append(",,,,,,,,,,,")

        # -------- Data --------
        lines.append("[Data],,,,,,,,,,,")
        lines.append("Lane,Sample_ID,Sample_Name,Sample_Plate,Sample_Well,Index_Plate_Well,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project,Description")

        for r in rows:
            lines.append(
                ",".join([
                    str(r.lane), 
                    r.sample_id,
                    "",             # Sample_Name
                    "",             # Sample_Plate
                    "",             # Sample_Well
                    "",             # Index_Plate_Well
                    r.i7_id or "",
                    r.i7_seq,
                    r.i5_id or "",  # in case single-index, no i5 index
                    r.i5_seq or "", # in case single-index, no i5 index
                    r.project_id,
                    r.sequencing_type,
                ])
            )

        return "\n".join(lines) + "\n"


@dataclass
class RunState:
    catalog: SharedCatalog = field(default_factory=SharedCatalog)
    indexes_panel_collapsed: bool = True
    indexes_mapping_type: IndexMappingType = "dual" # dropdown selection in Indexes Panel

    # Messages panel (Errors/Warnings only; persistent)
    messages: List[Message] = field(default_factory=list)

    # Validation cache (None = never validated or invalidated)
    validation_result: Optional[ValidationResult] = None

    # App-level startup warning shown outside the Messages panel
    startup_warning: Optional[str] = None

    # Project panel
    selected_project_id: Optional[str] = None

    # Lane panel (over-written in __post_init_)
    lanes: Dict[int, Lane] = field(default_factory=lambda: {i: Lane(i) for i in range(1, 9)})

    # Assignment table
    # assignments[sample_uid][lane_id] = planned_reads_m
    assignments: Dict[str, Dict[int, int]] = field(default_factory=dict)

    # Run level error
    has_run_level_error: bool = False

    # Samples panel
    samples_rows_per_page: int = 50 # number of samples to show in table
    # store selected sample_uids (UI selection)
    selected_sample_uids: List[str] = field(default_factory=list)

    # ---------- runtime environment (UI-first) ----------
    flowcell_type: str = "10B"
    n_lanes: int = 8
    lane_capacity_m: int = 1250
    read1_len: int = 101
    read2_len: int = 101

    base_dir: Path = field(default_factory=default_store_dir)
    plan_dir: Path = field(init=False)
    temp_dir: Path = field(init=False)
    output_dir: Path = field(init=False)
    max_plans: int = 25
    shared_catalog_dir: Optional[Path] = None
    user_name: str = ""

    def __post_init__(self):
        """Initialize derived directories and normalize the lane map."""
        # resolve directories under base_dir
        self.plan_dir = self.base_dir / "plans"
        self.temp_dir = self.base_dir / "temp"
        self.output_dir = self.base_dir / "outputs"

        self.plan_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # ensure lanes dict matches n_lanes
        self.lanes = {i: Lane(i) for i in range(1, int(self.n_lanes) + 1)}

    def apply_runtime_config(self, cfg) -> None:
        """
        Apply runtime config (flowcell, lanes, capacity, read length)
        """
        self.flowcell_type = cfg.flowcell_type
        self.n_lanes = int(cfg.n_lanes)
        self.lane_capacity_m = int(cfg.lane_capacity_m)

        if cfg.output_dir:
            self.output_dir = Path(cfg.output_dir)
        else:
            self.output_dir = self.base_dir / "outputs"

        raw_shared_dir = (getattr(cfg, "shared_catalog_dir", None) or "").strip()
        self.shared_catalog_dir = Path(raw_shared_dir) if raw_shared_dir else None
        self.user_name = (getattr(cfg, "user_name", "") or "").strip()

        self.read1_len = int(cfg.read1_len)
        self.read2_len = int(cfg.read2_len)

        self.max_plans = int(cfg.max_plans)

        # rebuild lanes cleanly
        self.lanes = {i: Lane(i) for i in range(1, int(self.n_lanes) + 1)}

    def rebuild_lanes_from_assignments(self) -> None:
        """
        rebuild lane.sample_uids/project_ids from assignments (gold truth)
        similar to the same-name function in actions.py
        """
        for lane in self.lanes.values():
            lane.sample_uids = []
            lane.project_ids = []
        for uid, per_lane in self.assignments.items():
            pid, _sid = split_sample_uid(uid)
            for lid in per_lane.keys():
                lane = self.lanes.get(int(lid))
                if not lane:
                    continue
                if uid not in lane.sample_uids:
                    lane.sample_uids.append(uid)
                if pid and pid not in lane.project_ids:
                    lane.project_ids.append(pid)

    def ensure_valid_project_selection(self) -> None:
        """Keep the selected project valid after refresh/load/remove operations."""
        project_ids = sorted(self.catalog.projects.keys())
        if self.selected_project_id not in project_ids:
            self.selected_project_id = project_ids[0] if project_ids else None
            self.selected_sample_uids.clear()

    # ---------- persistence ----------
    def to_dict(self) -> dict:
        """Serialize the plan-owned state to a JSON-friendly dictionary."""
        return {
            "indexes_panel_collapsed": self.indexes_panel_collapsed,
            "indexes_mapping_type": self.indexes_mapping_type,
            "messages": [asdict(m) for m in self.messages], 
            "selected_project_id": self.selected_project_id,
            "lanes": {str(lid): asdict(l) for lid, l in self.lanes.items()},
            "samples_rows_per_page": self.samples_rows_per_page,
            "selected_sample_uids": self.selected_sample_uids,
            "assignments": {
                uid: {str(lid): int(v) for lid, v in per_lane.items()} for uid, per_lane in (self.assignments or {}).items()
            },
            # save runtime info as part of plan (needed when recovering a plan)
            "runtime": {
                "flowcell_type": self.flowcell_type,
                "n_lanes": self.n_lanes,
                "lane_capacity_m": self.lane_capacity_m,
                "read1_len": self.read1_len,
                "read2_len": self.read2_len
            }
            # no serializaion on validation_result
        }

    @staticmethod
    def from_dict(d: dict) -> "RunState":
        """Build a RunState instance from a saved plan dictionary."""
        rs = RunState()

        # indexes panel state
        rs.indexes_panel_collapsed = bool(d.get("indexes_panel_collapsed", True))
        rs.indexes_mapping_type = d.get("indexes_mapping_type", "dual")

        # messages
        rs.messages = [Message(**m) for m in (d.get("messages") or [])]

        # runtime info
        runtime = d.get("runtime") or {}
        if runtime:
            cfg = default_config()
            for k, v in runtime.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
            rs.apply_runtime_config(cfg)
        
        rs.selected_project_id = d.get("selected_project_id")

        # lanes
        rs.lanes = {}
        for lid_str, ldata in (d.get("lanes") or {}).items():
            lid = int(lid_str)
            lane = Lane(
                lane_id=lid,
                sample_uids=ldata.get("sample_uids", []),
                project_ids=ldata.get("project_ids", []),
                status=LaneStatus(ldata.get("status", LaneStatus.OK)),
                headline=ldata.get("headline", ""),
                details=ldata.get("details", []),
            )
            rs.lanes[lid] = lane

        # ensure lanes exist
        for i in range(1, int(rs.n_lanes) + 1):
            rs.lanes.setdefault(i, Lane(i))

        # assignments
        rs.assignments = {}
        raw_asn = d.get("assignments") or {}
        for uid, per_lane in raw_asn.items():
            rs.assignments[uid] = {int(lid): int(v) for lid, v in (per_lane or {}).items()}
        # for the sake of safety
        # if assignments exist, rebuild lane.sample_uids/project_ids from assignments (gold truth)
        # to avoid future bugs that may be introduced by e.g. update assignments while forgot to update lanes
        if rs.assignments:
            rs.rebuild_lanes_from_assignments()

        # samples panel: rows per page
        rs.samples_rows_per_page = int(d.get("samples_rows_per_page", 50))
        rs.selected_sample_uids = list(d.get("selected_sample_uids", []))

        # validation_result (no serializaion)
        rs.validation_result = None
        rs.ensure_valid_project_selection()
        
        return rs

    def reset_run(self):
        """
        Reset current run state when flowcell / lane structure changes.
        This clears all planning-related data.
        """
        # clear assignments only
        self.assignments.clear()

        # clear validation / messages
        self.messages.clear()
        self.validation_result = None
        self.has_run_level_error = False

        # clear selection
        self.selected_sample_uids.clear()

        # rebuild lanes according to new lane count
        self.lanes = {i: Lane(i) for i in range(1, self.n_lanes + 1)}


def save_plan(state: RunState, path: Optional[Path] = None) -> Path:
    """Write the current plan state to disk and prune older saved plans."""
    store = state.plan_dir

    if path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = store / f"plan_{ts}.json"
    path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")

    # clean up old plans
    cleanup_saved_plans(store, state.max_plans)

    return path


def load_plan(path: Path) -> RunState:
    """Load a saved plan file into a new RunState instance."""
    d = json.loads(path.read_text(encoding="utf-8"))
    return RunState.from_dict(d)


def cleanup_saved_plans(store_dir: Path, keep_n: int) -> None:
    """
    Keep only the newest MAX_SAVED_PLANS plan files in store_dir.
    """
    if not store_dir.exists():
        return

    plans = sorted(
        store_dir.glob("plan_*.json"),
        key=lambda p: p.stat().st_mtime, 
        reverse=True, 
    )

    for p in plans[keep_n:]:
        try:
            p.unlink()
        except Exception:
            pass


def make_sample_uid(project_id: str, sample_id: str) -> str:
    """Build the stable project/sample key used inside planning state."""
    return f"{project_id}{SAMPLE_UID_SEP}{sample_id}"

def split_sample_uid(sample_uid: str) -> Tuple[str, str]:
    """Split a sample UID back into project_id and sample_id parts."""
    if SAMPLE_UID_SEP in sample_uid:
        pid, sid = sample_uid.split(SAMPLE_UID_SEP, 1)
        return pid, sid
    return "", sample_uid
