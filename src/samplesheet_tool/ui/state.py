# state.py
# control run state
# 

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional
import json
from pathlib import Path
from datetime import datetime


class LaneStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Sample:
    sample_id: str
    project_id: str
    reads_m: Optional[int] = None
    index_id: Optional[str] = None


@dataclass
class Project:
    project_id: str
    samples: List[Sample] = field(default_factory=list)

    @property
    def n_samples(self) -> int:
        return len(self.samples)

    @property
    def total_reads_m(self) -> Optional[int]:
        vals = [s.reads_m for s in self.samples if s.reads_m is not None]
        return sum(vals) if vals else None


@dataclass
class Lane:
    lane_id: int
    sample_ids: List[str] = field(default_factory=list)  # store sample_id only
    project_ids: List[str] = field(default_factory=list)
    status: LaneStatus = LaneStatus.OK
    headline: str = ""
    details: List[str] = field(default_factory=list)


@dataclass
class RunState:
    index_set_name: str = "Illumina (mock)"
    projects: Dict[str, Project] = field(default_factory=dict)
    selected_project_id: Optional[str] = None
    lanes: Dict[int, Lane] = field(default_factory=lambda: {i: Lane(i) for i in range(1, 9)})
    samples_rows_per_page: int = 50 # number of samples to show in table

    # ---------- persistence ----------
    def to_dict(self) -> dict:
        return {
            "index_set_name": self.index_set_name,
            "selected_project_id": self.selected_project_id,
            "projects": {pid: asdict(p) for pid, p in self.projects.items()},
            "lanes": {str(lid): asdict(l) for lid, l in self.lanes.items()},
            "samples_rows_per_page": self.samples_rows_per_page,
        }

    @staticmethod
    def from_dict(d: dict) -> "RunState":
        rs = RunState(index_set_name=d.get("index_set_name", "Illumina (mock)"))
        rs.selected_project_id = d.get("selected_project_id")

        # projects
        rs.projects = {}
        for pid, pdata in (d.get("projects") or {}).items():
            samples = [Sample(**s) for s in pdata.get("samples", [])]
            rs.projects[pid] = Project(project_id=pid, samples=samples)

        # lanes
        rs.lanes = {}
        for lid_str, ldata in (d.get("lanes") or {}).items():
            lid = int(lid_str)
            lane = Lane(
                lane_id=lid,
                sample_ids=ldata.get("sample_ids", []),
                project_ids=ldata.get("project_ids", []),
                status=LaneStatus(ldata.get("status", LaneStatus.OK)),
                headline=ldata.get("headline", ""),
                details=ldata.get("details", []),
            )
            rs.lanes[lid] = lane
        # ensure 1-8 exist
        for i in range(1, 9):
            rs.lanes.setdefault(i, Lane(i))

        # samples panel: rows per page
        rs.samples_rows_per_page = int(d.get("samples_rows_per_page", 50))

        return rs


def default_store_dir() -> Path:
    # internal tool: under user home directory, can be changed other directories later
    #base = Path.home() / ".samplesheet_tool_ui"
    base = Path("/gc11-data/analysis/taz2008/.samplesheet_tool_ui")
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

