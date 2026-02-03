# state.py
# control run state
# 

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Literal, Tuple, Any
import json
from pathlib import Path
from datetime import datetime


SAMPLE_UID_SEP = "::"

class LaneStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


MessageLevel = Literal["error", "warning"]

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


IndexMappingType = Literal["dual", "single"]

@dataclass
class IndexTables:
    """Merged global mapping tables (one per type)."""
    dual: Dict[str, Dict[str, str]] = field(default_factory=dict)  # index_id -> {"i7":..., "i5":...}
    single: Dict[str, str] = field(default_factory=dict)           # index_id -> sequence

    def stats(self) -> Dict[str, int]:
        return {"dual_ids": len(self.dual), "single_ids": len(self.single)}


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


@dataclass
class RunState:
    # Index mapping tables (merged global tables, one per type)
    index_tables: IndexTables = field(default_factory=IndexTables)
    indexes_panel_collapsed: bool = True
    indexes_mapping_type: IndexMappingType = "dual" # dropdown selection in Indexes Panel

    # Messages panel (Errors/Warnings only; persistent)
    messages: List[Message] = field(default_factory=list)

    # Project panel
    projects: Dict[str, Project] = field(default_factory=dict)
    selected_project_id: Optional[str] = None

    # Lane panel
    lanes: Dict[int, Lane] = field(default_factory=lambda: {i: Lane(i) for i in range(1, 9)})

    # Assignment table
    # assignments[sample_uid][lane_id] = planned_reads_m
    assignments: Dict[str, Dict[int, int]] = field(default_factory=dict)

    # Samples panel
    samples_rows_per_page: int = 50 # number of samples to show in table
    # store selected sample_uids (UI selection)
    selected_sample_uids: List[str] = field(default_factory=list)

    # ---------- persistence ----------
    def to_dict(self) -> dict:
        return {
            "index_tables": asdict(self.index_tables), 
            "indexes_panel_collapsed": self.indexes_panel_collapsed,
            "indexes_mapping_type": self.indexes_mapping_type,
            "messages": [asdict(m) for m in self.messages], 
            "selected_project_id": self.selected_project_id,
            "projects": {pid: asdict(p) for pid, p in self.projects.items()},
            "lanes": {str(lid): asdict(l) for lid, l in self.lanes.items()},
            "samples_rows_per_page": self.samples_rows_per_page,
            "selected_sample_uids": self.selected_sample_uids,
            "assignments": {
                uid: {str(lid): int(v) for lid, v in per_lane.items()} for uid, per_lane in (self.assignments or {}).items()
            },
        }

    @staticmethod
    def from_dict(d: dict) -> "RunState":
        rs = RunState()

        # index tables + indexes panel state
        it = d.get("index_tables") or {}
        rs.index_tables = IndexTables(
            dual = it.get("dual") or {},
            single = it.get("single") or {}, 
        )
        rs.indexes_panel_collapsed = bool(d.get("indexes_panel_collapsed", True))
        rs.indexes_mapping_type = d.get("indexes_mapping_type", "dual")

        # messages
        rs.messages = [Message(**m) for m in (d.get("messages") or [])]
        
        # projects
        rs.selected_project_id = d.get("selected_project_id")

        rs.projects = {}
        for pid, pdata in (d.get("projects") or {}).items():
            samples = [Sample(**s) for s in pdata.get("samples", [])]
            rs.projects[pid] = Project(
                project_id=pid, 
                samples=samples, 
                library_type=pdata.get("library_type"), 
                index_type=pdata.get("index_type", "dual"), 
            )

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

        # ensure 1-8 exist
        for i in range(1, 9):
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
            for lane in rs.lanes.values():
                lane.sample_uids = []
                lane.project_ids = []
            for uid, per_lane in rs.assignments.items():
                pid, _sid = split_sample_uid(uid)
                for lid in per_lane.keys():
                    lane = rs.lanes.get(int(lid))
                    if not lane:
                        continue
                    if uid not in lane.sample_uids:
                        lane.sample_uids.append(uid)
                    if pid and pid not in lane.project_ids:
                        lane.project_ids.append(pid)

        # samples panel: rows per page
        rs.samples_rows_per_page = int(d.get("samples_rows_per_page", 50))
        rs.selected_sample_uids = list(d.get("selected_sample_uids", []))

        return rs


def default_store_dir() -> Path:
    # internal tool: under user home directory, can be changed other directories later
    #base = Path.home() / ".samplesheet_tool_ui"
    base = Path("/gc11-data/analysis/taz2008/.samplesheet_tool_ui")
    #base = Path("/Users/freshtuo/Work/.samplesheet_tool_ui")
    base.mkdir(parents=True, exist_ok=True)
    return base


def save_plan(state: RunState, path: Optional[Path] = None) -> Path:
    store = default_store_dir()
    if path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = store / f"plan_{ts}.json"
    path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    return path


def load_plan(path: Path) -> RunState:
    d = json.loads(path.read_text(encoding="utf-8"))
    return RunState.from_dict(d)


# -------------------------
# index preset persistence
# -------------------------

def index_preset_path() -> Path:
    # get JSON file storing index preset
    return default_store_dir() / "index_preset.json"

def save_index_preset(state: RunState) -> None:
    """Persist merged index tables (dual + single)."""
    path = index_preset_path()
    payload = {
        "dual": state.index_tables.dual,
        "single": state.index_tables.single,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

def load_index_preset(state: RunState) -> None:
    """Load merged index tables if preset exists."""
    path = index_preset_path()
    if not path.exists():
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        state.index_tables.dual = data.get("dual", {})
        state.index_tables.single = data.get("single", {})
    except Exception:
        # fail silently; preset is optional
        pass


def make_sample_uid(project_id: str, sample_id: str) -> str:
    return f"{project_id}{SAMPLE_UID_SEP}{sample_id}"

def split_sample_uid(sample_uid: str) -> Tuple[str, str]:
    if SAMPLE_UID_SEP in sample_uid:
        pid, sid = sample_uid.split(SAMPLE_UID_SEP, 1)
        return pid, sid
    return "", sample_uid

