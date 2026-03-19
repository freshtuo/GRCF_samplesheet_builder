# 📦 SampleSheet Tool – Developer Architecture & Usage Guide

This document describes the internal architecture and design rules of the SampleSheet Tool
(UI-first). For installation and quick usage, see `README.md`.

---

## 1. Goals

- **Single source of truth**: UI and actions operate on `RunState` only.
- **Simple collaboration**: 2-3 users can share indexes and projects through a shared folder without sharing live lane plans.
- **Reproducibility**: Saved plans include a **runtime snapshot** (flowcell/lanes/read lengths/capacity).
- **Deterministic validation**: Split validation into lane-local vs final global validation with clear
  responsibility boundaries and stable status resolution rules.
- **Structured storage**: shared catalog for shared metadata, local workspace for personal planning state.

## 2. Key Concepts

### 2.1 Runtime
Runtime describes the planning environment. It includes:
- `flowcell_type` (e.g. 1.5B / 10B / 25B)
- `n_lanes`
- `lane_capacity_m` (reads per lane, in millions)
- `read1_len`, `read2_len`
- `output_dir` (optional override)
- `max_plans`
- `shared_catalog_dir` (path to shared indexes/projects)
- `user_name` (optional attribution for shared saves)

Runtime defaults come from `config.json` and can be edited via **Settings dialog**.

### 2.2 Plan

A Plan is a **local snapshot** of a planned run:

- runtime snapshot (for reproducibility)
- lane assignments
- selected project/sample UI state
- optional validation snapshot (messages/status)

Shared indexes and shared projects are **not** the authority in plan files. They are loaded from the shared catalog.

**Rule**: `load_plan` restores runtime from the plan snapshot to prevent mismatches, then rebinds the UI to the current shared catalog.

### 2.3 RunState (Single Source of Truth)

`RunState` represents the current in-memory state of the UI:

- runtime fields
- `catalog` for shared indexes and projects
- lane assignments and lane status
- messages
- lightweight UI coordination flags for deferred shared-catalog refresh

UI and actions should **only read/write `RunState`**.

---

## 3. Storage Model and Directory Layout

### 3.1 Local Workspace
Base directory is fixed and cross-platform for per-user data:

- `Path.home() / ".samplesheet_tool_ui"`

This stores each user's local planning state and avoids collisions between collaborators.

### 3.2 Local On-disk Layout

```markdown
~/.samplesheet_tool_ui/
│
├── config.json        # runtime defaults, shared path, user name
├── plans/             # local planning snapshots
├── temp/              # transient intermediates (safe to delete)
└── outputs/           # exports
```

### 3.3 Shared Catalog Layout

```markdown
<shared_catalog_dir>/
│
├── indexes.json
└── projects/
    ├── PROJECT_A.json
    └── PROJECT_B.json
```

### 3.4 Persistence Responsibilities

- local `config.json`: runtime defaults + shared folder path + user name
- local `plans/*.json`: runtime + assignments + local UI state
- `temp/`: upload/import scratch space; safe to clear
- `outputs/`: final deliverables
- shared `indexes.json`: shared index mappings
- shared `projects/*.json`: one shared project per file

---

## 4. UI Structure (What is a Panel vs Dialog vs Mechanism)

### 4.1 Persistent Panels (always visible)

- **Index Panel**: import/manage index tables; used to fill missing indexes during project import
- **Project Panel**: view/import/remove shared projects (removal does not auto-remove local lane assignments)
- **Sample Panel**: shows samples for selected project; inspect indexes/reads/etc.
- **Lane Panel**: assign/remove projects/samples to lanes; shows lane status indicator
- **Messages Panel**: warnings/errors/info pushed by validation and actions

### 4.2 Dialog-Based Views (modal)

- **Settings dialog**: edits runtime (flowcell, lanes, capacity, read lengths, output_dir, shared_catalog_dir, user_name)
  - On Windows web sessions, folder paths are entered manually; native Tk folder pickers are disabled because they can block the NiceGUI connection.
- **Summary dialog**: aggregated view of current assignments (run/project/sample levels)

### 4.3 Validation Mechanism (not a panel)

Validation is a background logic system that:

- updates lane status indicators
- pushes messages into Messages Panel
- blocks export if errors exist

---

## 5. Data Flow

### 5.1 Import

```markdown
Shared indexes
        ↓
Project import (CSV)

- normalize columns

- resolve index IDs → sequences (if possible)

- fill missing indexes using shared index catalog (optional)

- sample-level sanity checks
        ↓
Shared catalog projects
```

### 5.2 Planning (UI Interaction)

```markdown
Define Runtime Settings
        ↓
Load / auto-refresh shared catalog if needed
        ↓
Assign shared projects to local lanes
        ↓
Lane-local Validation within each lane
        ↓
Lane status updated + messages pushed
Final Validation across lanes (Lane status updated + messages pushed)
```

### 5.3 Final Validation + Export

```markdown
User triggers Validate / Export
        ↓
Final Validation across lanes (global)
        ↓
If ERROR → block export
Else → export into state.output_dir
```

### 5.4 Plan Save/Load

- Save plan: serialize runtime snapshot + local assignments + local UI state
- Load plan: restore runtime snapshot first, rebuild lanes, restore assignments, then use the current shared catalog

Plans are automatically saved when things get changed.

---

## 6. Validation Architecture

Validation is split into two stages.

### 6.1 Lane-local Validation
Runs:
- on assign/remove/clear lane
- on allocation changes within a lane

Checks (examples):
- duplicate sample IDs within lane
- duplicate index sequences within lane
- lane capacity overflow

Output:
- lane status indicator update
- messages appended to Messages Panel

### 6.2 Final Global Validation
Runs:
- on Validate button and/or immediately before Export

Checks (examples):
- cross-lane sample ID conflicts
- export format requirements
- run-level conflicts not tied to a single lane

Output:
- run-level messages (and optionally run-level status)
- may escalate lane status (see priority rules below)
- blocks export if errors exist

### 6.3 Lane Status Resolution Priority (Do Override Lane-local Errors)

Lane-local errors persist. Final validation cannot clear lane-local errors

Lane status resolution rules:

| Lane-local Status | Final Validation Result | Final Lane Status | Notes |
|---|---|---|---|
| OK | OK | 🟢  Green | Fully valid |
| OK | WARNING | 🟡  Yellow | Final validation adds risk |
| OK | ERROR | 🔴 Red | Final validation escalates |
| WARNING | OK | 🟡  Yellow | Lane-local warning persists |
| WARNING | WARNING | 🟡  Yellow | Same severity |
| WARNING | ERROR | 🔴 Red | Escalated by final validation |
| ERROR | any | 🔴 Red | Lane-local hard error is never downgraded |

Additional rule:
- Run-level errors not associated with a specific lane do **not** downgrade lanes; they block export and are shown in Messages Panel.

---

## 7. Behavioral Rules and Edge Cases

### 7.1 Changing Flowcell / Lane Configuration

When runtime changes affecting lane shape:
- `flowcell_type`, `n_lanes`, `lane_capacity_m`

System assumes a new run planning session:
- **clear lane assignments**
- reset lane status/messages related to assignments
- **do not delete imported projects/samples**

### 7.2 Project Removal vs Lane Assignments

Removing a project from Project Panel:
- removes it from the shared catalog
- **does not automatically remove already-assigned items from lanes**
- lane content is only changed via Lane Panel actions

If another user deleted the same project already:
- refresh shared catalog
- keep local lane assignments unchanged
- report missing shared project during validation/export if still referenced

### 7.3 Load Plan Restores Runtime

`load_plan` restores runtime snapshot (flowcell/lanes/capacity/read lengths) before restoring assignments.
This prevents mismatch (e.g. 8-lane plan loaded under 2-lane runtime).

### 7.4 Read Length Changes

Read lengths are runtime. If changed after assignments:

- lane-local checks may still pass
- final validation/export must use the updated read lengths
- best practice: re-run validation before export

---

### 7.5 Collaboration Model

Collaboration is intentionally simple:
- 2-3 users point the app to the same `shared_catalog_dir`
- shared data: indexes and projects
- local-only data: lane assignments, validation/messages, local plans, outputs
- the app also polls the shared catalog in the background
- index-only changes update in memory without forcing a full page redraw
- project add/remove/content changes trigger a deferred-safe UI refresh
- the `Refresh Shared` toolbar button remains available for immediate manual reload
- duplicate project IDs are rejected
- removing an already-deleted project becomes a refresh case, not a crash

The app does **not** implement real-time shared lane planning. It uses lightweight polling plus safe deferred redraws instead.

---

## 8. Export Model

### Export Requires Project/Sample Metadata (Do Not Remove Before Export)

Exporting a SampleSheet requires **project/sample metadata** loaded from the Project/Sample panels.

- The export renderer builds rows from the imported project + sample records.
- If a shared project is removed before export, local lane assignments may still reference it.
  In that case validation/export should fail clearly until the user removes or fixes those assignments.

**Practical rule:** ensure required shared projects still exist before export is completed.

Export output location:
- `state.output_dir`

Export should use runtime values from `RunState`:
- `read1_len`, `read2_len`
- lane count/capacity
- any export-format requirements

Export is blocked if:
- any lane is in ERROR, or
- final validation produces ERROR

---

## 9. Module Map (Repository Layout)

```markdown
GRCF_samplesheet_builder/
├── README.md
├── pyproject.toml
├── LICENSE
│
├── docs/
│   └── ARCHITECTURE.md
│
├── data/
│   └── indexes/                       # built-in example / reference index tables
│       ├── Dual_Index_Kit_NN_Set_A.csv
│       ├── i5_illumina.csv
│       └── i7_illumina.csv
│
├── src/
│   └── samplesheet_tool/
│       ├── __init__.py
│       ├── __main__.py                # CLI entry point
│       ├── config.py                  # CLI defaults / thresholds (some are also used in UI)
│       ├── context.py                 # shared context model (CLI-side)
│       ├── indexes.py                 # index loading helpers
│       ├── io_normalize.py            # input normalization (header rename, etc.)
│       ├── resolve.py                 # index ID → index sequence resolver
│       ├── validate.py                # core validation logic (sample/index checks)
│       ├── utils.py                   # shared helpers
│       │
│       └── ui/
│           ├── __init__.py
│           ├── __main__.py            # UI entry point (python -m samplesheet_tool.ui)
│           ├── app.py                 # UI bootstrap, state init, build views
│           ├── views.py               # NiceGUI layout + dialogs (Settings/Summary/Plan)
│           ├── actions.py             # UI actions: mutate RunState, validate, export, plan save/load
│           ├── state.py               # RunState, lanes, plan persistence, path mgmt
│           ├── runtime_config.py      # runtime config load/save (config.json)
│           └── project_io.py          # project import/export utilities (UI side)
│
└── tests/
    ├── data/                          # small test inputs
    ├── run_test.sh
    └── make_test_data.sh
```

## 10. Related Documentation

- User guide / workflow: `README.md`
- If you want a detailed usage guide: `docs/ARCHITECTURE.md` (optional)
