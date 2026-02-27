# 📦 SampleSheet Tool – Developer Architecture & Usage Guide

This document describes the internal architecture and design rules of the SampleSheet Tool
(UI-first). For installation and quick usage, see `README.md`.

---

## 1. Goals

- **Single source of truth**: UI and actions operate on `RunState` only.
- **Reproducibility**: Saved plans include a **runtime snapshot** (flowcell/lanes/read lengths/capacity).
- **Deterministic validation**: Split validation into lane-local vs final global validation with clear
  responsibility boundaries and stable status resolution rules.
- **Structured storage**: fixed base dir under user home, with `plans/`, `temp/`, `outputs/`.

## 2. Key Concepts

### 2.1 Runtime
Runtime describes the planning environment. It includes:
- `flowcell_type` (e.g. 1.5B / 10B / 25B)
- `n_lanes`
- `lane_capacity_m` (reads per lane, in millions)
- `read1_len`, `read2_len`
- `output_dir` (optional override)
- `max_plans`

Runtime defaults come from `config.json` and can be edited via **Settings dialog**.

### 2.2 Plan

A Plan is a **complete snapshot** of a planned run:

- runtime snapshot (for reproducibility)
- projects + samples (imported metadata)
- lane assignments
- relevant index table references (if needed for restoration)
- optional validation snapshot (messages/status)

**Rule**: `load_plan` restores runtime from the plan snapshot to prevent mismatches.

### 2.3 RunState (Single Source of Truth)

`RunState` represents the current in-memory state of the UI:

- runtime fields
- loaded index tables/presets
- projects and samples
- lane assignments and lane status
- messages

UI and actions should **only read/write `RunState`**.

---

## 3. Storage Model and Directory Layout

### 3.1 Base Directory (Fixed)
Base directory is fixed and cross-platform:

- `Path.home() / ".samplesheet_tool"`

This avoids bootstrap problems and is stable on Windows/macOS/Linux.

### 3.2 On-disk Layout

```markdown
~/.samplesheet_tool/
│
├── config.json        # runtime defaults (optional)
├── index_preset.json  # saved index presets (optional)
├── plans/             # saved plans (reproducible snapshots)
├── temp/              # transient intermediates (safe to delete)
└── outputs/           # exports
```

### 3.3 Persistence Responsibilities

- `config.json`: runtime defaults (saved from Settings dialog)
- `plans/*.json`: per-run snapshots (runtime + assignments + samples)
- `temp/`: upload/import scratch space; safe to clear
- `outputs/`: final deliverables

---

## 4. UI Structure (What is a Panel vs Dialog vs Mechanism)

### 4.1 Persistent Panels (always visible)

- **Index Panel**: import/manage index tables; used to fill missing indexes during project import
- **Project Panel**: import/remove projects (removal does not auto-remove lane assignments)
- **Sample Panel**: shows samples for selected project; inspect indexes/reads/etc.
- **Lane Panel**: assign/remove projects/samples to lanes; shows lane status indicator
- **Messages Panel**: warnings/errors/info pushed by validation and actions

### 4.2 Dialog-Based Views (modal)

- **Settings dialog**: edits runtime (flowcell, lanes, capacity, read lengths, output_dir)
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
Index tables/presets
        ↓
Project import (CSV)

- normalize columns

- resolve index IDs → sequences (if possible)

- fill missing indexes using index presets (optional)

- sample-level sanity checks
        ↓
RunState.projects / RunState.samples
```

### 5.2 Planning (UI Interaction)

```markdown
Define Runtime Settings
        ↓
Assign Projects to Lanes
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

- Save plan: serialize runtime snapshot + projects/samples + lane assignments
- Load plan: restore runtime snapshot first, rebuild lanes, then restore assignments, refresh UI

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
- removes it from the project list
- **does not automatically remove already-assigned items from lanes**
- lane content is only changed via Lane Panel actions

### 7.3 Load Plan Restores Runtime

`load_plan` restores runtime snapshot (flowcell/lanes/capacity/read lengths) before restoring assignments.
This prevents mismatch (e.g. 8-lane plan loaded under 2-lane runtime).

### 7.4 Read Length Changes

Read lengths are runtime. If changed after assignments:

- lane-local checks may still pass
- final validation/export must use the updated read lengths
- best practice: re-run validation before export

---

## 8. Export Model

### Export Requires Project/Sample Metadata (Do Not Remove Before Export)

Exporting a SampleSheet requires **project/sample metadata** loaded from the Project/Sample panels.

- The export renderer builds rows from the imported project + sample records.
- If a project is removed from the Project Panel before export, its sample metadata may no longer be available,
  which can lead to missing entries or incomplete output.

**Practical rule:** ensure required projects/samples remain loaded until export is completed.

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

