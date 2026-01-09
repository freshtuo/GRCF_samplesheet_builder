# actions.py
# response to actions
# 

from __future__ import annotations
from typing import List, Optional, Iterable, Set
from nicegui import ui
from samplesheet_tool.ui.state import RunState, LaneStatus, Project, Sample, save_plan, load_plan
from pathlib import Path


def mock_import_project(state: RunState, project_id: str, n: int = 12) -> None:
    # mock: generate some samples
    samples = []
    for i in range(1, n + 1):
        samples.append(Sample(
            sample_id=f"{project_id}_S{i:03d}",
            project_id=project_id,
            reads_m=50,
            index_id=f"IDX{i:02d}",
        ))
    state.projects[project_id] = Project(project_id=project_id, samples=samples)
    state.selected_project_id = project_id


def lane_recompute_mock(state: RunState, lane_id: int) -> None:
    """Mock lane validation: display red/orange/green + headline/details only."""
    lane = state.lanes[lane_id]
    # simple rule:  > 40 samples -> warning; contain repeating sample_id -> error
    seen: Set[str] = set()
    dups: List[str] = []
    for sid in lane.sample_ids:
        if sid in seen:
            dups.append(sid)
        seen.add(sid)

    if dups:
        lane.status = LaneStatus.ERROR
        lane.headline = "Duplicate sample_id"
        lane.details = [f"dup: {s}" for s in dups[:5]]
    elif len(lane.sample_ids) > 40:
        lane.status = LaneStatus.WARNING
        lane.headline = "High sample count"
        lane.details = [f"samples={len(lane.sample_ids)}"]
    else:
        lane.status = LaneStatus.OK
        lane.headline = ""
        lane.details = []


def add_samples_to_lanes(
    state: RunState,
    sample_ids: List[str],
    lane_ids: List[int],
) -> None:
    # append syntax: remove redundant samples within a lane (automatically)
    if not sample_ids or not lane_ids:
        return

    # sample -> project mapping (find in projects)
    sample_to_project = {}
    for p in state.projects.values():
        for s in p.samples:
            sample_to_project[s.sample_id] = p.project_id

    for lid in lane_ids:
        lane = state.lanes[lid]
        existing = set(lane.sample_ids)
        for sid in sample_ids:
            if sid in existing:
                continue
            lane.sample_ids.append(sid)
            existing.add(sid)
            pid = sample_to_project.get(sid)
            if pid and pid not in lane.project_ids:
                lane.project_ids.append(pid)

        lane_recompute_mock(state, lid)


def remove_project_from_lane(state: RunState, lane_id: int, project_id: str) -> None:
    lane = state.lanes[lane_id]
    if project_id not in lane.project_ids:
        return

    # find samples under the target project
    sample_ids = []
    p = state.projects.get(project_id)
    if p:
        sample_ids = [s.sample_id for s in p.samples]

    lane.sample_ids = [sid for sid in lane.sample_ids if sid not in set(sample_ids)]
    lane.project_ids = [pid for pid in lane.project_ids if pid != project_id]
    lane_recompute_mock(state, lane_id)


def clear_lane(state: RunState, lane_id: int) -> None:
    lane = state.lanes[lane_id]
    lane.sample_ids.clear()
    lane.project_ids.clear()
    lane_recompute_mock(state, lane_id)


def validate_full_mock(state: RunState) -> None:
    # mock: re-compute for all lanes
    for lid in state.lanes:
        lane_recompute_mock(state, lid)


def has_any_data(state: RunState) -> bool:
    if not state.projects:
        return False
    return any(len(l.sample_ids) > 0 for l in state.lanes.values())

def can_export(state: RunState) -> bool:
    if not has_any_data(state):
        return False
    return all(l.status != LaneStatus.ERROR for l in state.lanes.values())

