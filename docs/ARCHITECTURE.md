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
- shared `indexes.json`: shared imported index sets plus flattened lookup tables
- shared `projects/*.json`: one shared project per file

### 3.5 Shared Index JSON Shape

`indexes.json` is the shared source-of-truth for indexes.
It stores both the imported set-level data and the flattened lookup tables used by the rest of the app.

Top-level fields:
- `updated_at`
- `updated_by`
- `index_sets.dual`
- `index_sets.single`
- `flattened_indexes.dual`
- `flattened_indexes.single`

Each imported index set stores:
- `set_id`: stable internal identifier used for remove actions
- `name`: user-provided unique set name
- `rows`: the original imported rows for that set
- `uploaded_at`
- `uploaded_by`

Example:

```json
{
  "updated_at": "2026-03-23T18:42:10Z",
  "updated_by": "alice",
  "index_sets": {
    "dual": [
      {
        "set_id": "9a4d3d24df8f4e8ca9d8f3d1d2a7b6c1",
        "name": "GRCF_dual_march2026",
        "rows": [
          {
            "index_id": "D701",
            "i7": "ATTACTCG",
            "i5": "TATAGCCT"
          },
          {
            "index_id": "D702",
            "i7": "TCCGGAGA",
            "i5": "ATAGAGGC"
          }
        ],
        "uploaded_at": "2026-03-23T18:42:10Z",
        "uploaded_by": "alice"
      }
    ],
    "single": [
      {
        "set_id": "1b9e91f17a0c4eb7b9f0a1e4d5c6f789",
        "name": "GRCF_single_test",
        "rows": [
          {
            "index_id": "S501",
            "sequence": "TATAGCCT"
          },
          {
            "index_id": "S502",
            "sequence": "ATAGAGGC"
          }
        ],
        "uploaded_at": "2026-03-23T18:50:02Z",
        "uploaded_by": "bob"
      }
    ]
  },
  "flattened_indexes": {
    "dual": {
      "D701": {
        "i7": "ATTACTCG",
        "i5": "TATAGCCT"
      },
      "D702": {
        "i7": "TCCGGAGA",
        "i5": "ATAGAGGC"
      }
    },
    "single": {
      "S501": "TATAGCCT",
      "S502": "ATAGAGGC"
    }
  }
}
```

### 3.6 Shared Project JSON Shape

Each shared project lives in its own file under `projects/`.
It stores the imported sample metadata plus shared save metadata.

Top-level fields:
- `project_id`
- `samples`
- `library_type`
- `index_type`
- `sequencing_type`
- `updated_at`
- `updated_by`

Example:

```json
{
  "project_id": "PROJECT_A",
  "samples": [
    {
      "sample_id": "SAMPLE_001",
      "project_id": "PROJECT_A",
      "i7_id": "D701",
      "i7_seq": "ATTACTCG",
      "i5_id": "D501",
      "i5_seq": "TATAGCCT",
      "required_reads_m": 50
    },
    {
      "sample_id": "SAMPLE_002",
      "project_id": "PROJECT_A",
      "i7_id": "D702",
      "i7_seq": "TCCGGAGA",
      "i5_id": "D502",
      "i5_seq": "ATAGAGGC",
      "required_reads_m": 75
    }
  ],
  "library_type": "Amplicon",
  "index_type": "dual",
  "sequencing_type": "PE101",
  "updated_at": "2026-03-23T19:05:11.123456Z",
  "updated_by": "alice"
}
```

### 3.7 Local Plan JSON Shape

A saved plan is local-only and stores the current planning snapshot, not the shared catalog contents.
It keeps enough UI state to restore the planning session consistently.

Top-level fields:
- `indexes_panel_collapsed`
- `indexes_mapping_type`
- `selected_index_set_type`
- `selected_index_set_id`
- `selected_project_id`
- `messages`
- `lanes`
- `assignments`
- `runtime`

Example:

```json
{
  "indexes_panel_collapsed": true,
  "indexes_mapping_type": "dual",
  "selected_index_set_type": "dual",
  "selected_index_set_id": "9a4d3d24df8f4e8ca9d8f3d1d2a7b6c1",
  "selected_project_id": "PROJECT_A",
  "messages": [
    {
      "level": "warning",
      "text": "Lane 1 is near capacity",
      "source": "lane_validation",
      "lane": 1,
      "project_id": null,
      "sample_id": null,
      "ts": "2026-03-23 15:07:42"
    }
  ],
  "lanes": {
    "1": {
      "lane_id": 1,
      "sample_uids": ["PROJECT_A::SAMPLE_001"],
      "project_ids": ["PROJECT_A"],
      "status": "warning",
      "headline": "Near capacity",
      "details": ["Used reads are close to lane capacity"]
    }
  },
  "selected_sample_uids": ["PROJECT_A::SAMPLE_001"],
  "samples_rows_per_page": 50,
  "assignments": {
    "PROJECT_A::SAMPLE_001": {
      "1": 50
    }
  },
  "runtime": {
    "flowcell_type": "10B",
    "n_lanes": 8,
    "lane_capacity_m": 1250,
    "read1_len": 101,
    "read2_len": 101
  }
}
```

### 3.8 In-memory Shared Catalog Shape

`RunState.catalog` is the in-memory representation of the shared catalog and combines both index and project data.
It is not persisted directly as one file, but it is the structure views and actions work with at runtime.

Key fields:
- `index_sets`
- `index_tables`
- `projects`
- `project_updated_at`
- `indexes_updated_at`
- `indexes_updated_by`
- `last_loaded_at`

---

## 4. UI Structure (What is a Panel vs Dialog vs Mechanism)

### 4.1 Persistent Panels (always visible)

- **Index Panel**: import/manage named index sets; flattened lookup tables are rebuilt for project auto-fill
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
Shared imported index sets
        ↓
Build flattened shared index lookups
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

### 7.3 Index Set Import and Removal

Importing an index table:
- requires a unique user-facing set name
- stores one `IndexSet` under `index_sets.single` or `index_sets.dual`
- rebuilds `flattened_indexes`
- atomically rewrites shared `indexes.json`

Removing an index set:
- targets the stable `set_id`, not the display name
- reloads the latest shared `indexes.json`
- removes the chosen set if it still exists
- rebuilds `flattened_indexes`
- atomically rewrites shared `indexes.json`

Conflict rules:
- same `index_id` with identical mapping across sets is allowed
- same `index_id` with different mapping across sets is rejected
- importing the same set name twice is rejected
- removing an already-removed set becomes a refresh/warning case, not a crash

### 7.4 Load Plan Restores Runtime

`load_plan` restores runtime snapshot (flowcell/lanes/capacity/read lengths) before restoring assignments.
This prevents mismatch (e.g. 8-lane plan loaded under 2-lane runtime).

### 7.5 Read Length Changes

Read lengths are runtime. If changed after assignments:

- lane-local checks may still pass
- final validation/export must use the updated read lengths
- best practice: re-run validation before export

---

### 7.6 Collaboration Model

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

#### What makes multi-user use safe

Safety comes from separating **shared catalog data** from **local planning state**:
- users share indexes and projects
- users do **not** share lane assignments, local plans, validation messages, or export outputs
- one user's planning changes do not overwrite another user's lane work

Shared writes are also designed to avoid partial files:
- shared `indexes.json` is written by saving a complete replacement file and then atomically replacing the old file
- shared project files are written one project per file, so updating one project does not rewrite all projects
- readers either see the old complete file or the new complete file, not a half-written JSON file

Read/update behavior is intentionally conservative:
- index set import/remove reloads the latest shared `indexes.json` before writing
- project remove reloads the shared catalog again if the target project was already deleted
- background polling refreshes in-memory shared state so users eventually converge to the same shared view
- if a dialog is open, destructive full redraws are deferred until the modal flow finishes

#### What we guarantee

The collaboration model is designed to guarantee these properties:
- no partial shared JSON files from normal app writes
- no crash if another user already removed the same project or index set
- no direct cross-user overwrite of local lane assignments, local plans, or outputs
- no ambiguous shared index lookup: conflicting `index_id` to sequence mappings are rejected during index merge

#### What we do not guarantee

This is **not** a transactional multi-user database.
In extreme timing races, users should expect last-writer-wins behavior for some shared operations.

Examples:
- if two users import different index sets at nearly the same time, the app reloads before write and uses atomic replace, but the final shared file still depends on which write lands last
- if two users try to remove the same index set, one succeeds and the other sees a refresh/warning case instead of a crash
- if two users edit the same shared project file independently outside the app, the app can only react to the final file that exists on disk
- if one user removes a project that another user has already assigned locally to lanes, those local assignments remain until the second user removes or fixes them

#### Expected behavior in extreme cases

When race conditions happen, the expected outcome is graceful recovery rather than strict locking:
- a user may see a shared refresh notice after another user's change
- a remove action may become a no-op with a warning because the target is already gone
- local lane assignments may temporarily reference a shared project that no longer exists
- validation/export should then surface that missing-project problem clearly
- manual `Refresh Shared` is always available if a user wants to force immediate resync

Practical expectation:
- collaboration is safe and predictable for a small group sharing indexes and projects
- it is not intended to support high-frequency concurrent editing of the exact same shared records

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
