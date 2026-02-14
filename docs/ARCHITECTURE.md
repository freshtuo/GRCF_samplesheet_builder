# 📦 SampleSheet Tool – Architecture & Usage Guide

## 1. Overview

SampleSheet Tool is a UI-first application for planning and exporting sequencing runs.

The workflow is designed around:

- Runtime configuration

- Lane assignment

- Validation

- Export

- Plan persistence

## 2. High-Level Workflow

```markdown
Define Runtime Settings
        ↓
Import Projects / Index Tables
        ↓
Assign Projects to Lanes
        ↓
Lane-local Validation
        ↓
Final Validation
        ↓
Export SampleSheet
        ↓
(Optional) Save Plan
```

## 3. Directory Structure

The base directory is fixed and cross-platform:

```markdown
~/.samplesheet_tool/
│
├── config.json
├── plans/
├── temp/
└── outputs/
```

Base directory is determined by:

```python
Path.home() / ".samplesheet_tool"
```

This works on:

- Windows

- macOS

- Linux

## 4. Runtime vs Plan
### 4.1 Runtime

Represents the current execution environment:

- flowcell_type

- n_lanes

- lane_capacity_m

- read1_len

- read2_len

- output_dir

- max_plans

Runtime is loaded from:

```markdown
config.json
```

### 4.2 Plan

Represents a snapshot of:

- Lane assignments

- Projects

- Validation results

- Runtime snapshot

Each plan stores:

```json
{
  "runtime": {
    "flowcell_type": "10B",
    "n_lanes": 8,
    "lane_capacity_m": 1250,
    "read1_len": 100,
    "read2_len": 100
  }
}
```

This guarantees reproducibility.

## 5. Validation System

Validation is split into two levels.

### 5.1 Lane-Local Validation

Triggered when:

- Assign project to lane

- Remove project from lane

- Clear lane

- Modify allocation

Checks:

- Index conflicts

- Duplicate samples

- Lane capacity overflow

- Reads balancing consistency

Status indicator:

```markdown
| Status | Meaning |
|--------|---------|
|🟢  Green | Valid |
|🟡 Yelloww | Warning|
|🔴 Red	| Blocking error |
```
Lane-local validation is lane-specific only.

### 5.2 Final Validation

Triggered when:

- User clicks "Validate"

- Before Export

Checks:

- Cross-lane conflicts

- Export format requirements

- Global consistency

Final validation:

- Does NOT override lane-local errors

- May add global errors

### 5.3 Error Persistence Policy

Rules:

1. Lane-local errors persist.

2. Final validation cannot clear lane-local errors.

3.  Export blocked if:

  - Any lane has blocking error

  - Global validation fails

## 6. Behavioral Rules
### 6.1 Changing Flowcell / Lane Settings

When changing:

- flowcell_type

- n_lanes

- lane_capacity

System assumes new run planning:

- Clears lane assignments

- Resets validation state

- Keeps imported projects

### 6.2 Loading a Plan

When loading:

1. Restore runtime snapshot.

2. Rebuild lanes.

3. Restore assignments.

4. Refresh UI.

Plan runtime overrides current runtime.

### 6.3 Deleting Projects

Removing a project from Project panel:

- Does NOT automatically remove it from lanes.

- Lane panel must be updated manually.

## 7. Export Logic

Exports to:

```markdown
state.output_dir/run_YYYYMMDD_HHMMSS/
```

Read lengths used:

```markdown
state.read1_len
state.read2_len
```

Export blocked if validation fails.

## 8. Edge Case Handling
### 8.1 Flowcell Change After Planning

Changing flowcell:

- Clears all assignments.

- Requires re-planning.

### 8.2 Loading Plan with Different Runtime

Loading plan restores its runtime snapshot.

No mismatch possible.

### 8.3 Deleting Projects After Assignment

Lane assignments remain until explicitly cleared.

### 8.4 Read Length Changes

Read length is runtime-dependent.

If changed after planning:

- Plan should be saved or revalidated.

## 9. Installation

This tool works on:

- Windows

- macOS

- Linux

### 9.1 Requirements

- Python 3.9+

- pip

###9.2 Clone Repository

```bash
git clone https://github.com/yourname/samplesheet-tool.git
cd samplesheet-tool
```

### 9.3 Create Virtual Environment (Recommended)

```python
python -m venv venv
```

Activate:

#### Windows:
```bash
venv\Scripts\activate
```
####macOS / Linux:
```bash
source venv/bin/activate
```

### 9.4 Install in Editable Mode
```python
pip install -e .
```
###9.5 Run UI
```python
python -m samplesheet_tool.ui
```

## 10. Versioning

Version is managed in:
```markdown
pyproject.toml
```

Application reads version dynamically via:

```python
importlib.metadata.version("samplesheet-tool")
```

Release workflow:

```bash
git tag -a v0.2.0 -m "Stable release"
git push origin v0.2.0
```

# GRCF_samplesheet_builder

Organize samples for a sequencing run, and prepare samplesheet file

1. Overall Logic Flow:

```text
Index Mapping Tables
        ↓
(Project Import)
  - read sample file
  - minimal normalize
  - resolve index sequences
  - basic sample-level validation
        ↓
RunState.projects (samples with index sequences)
        ↓
(UI interaction)
  assign samples → lanes
        ↓
(Lane Pre-check)
  - lane-local conflicts
  - hamming / mixing warnings
        ↓
RunState.lanes.status + messages
        ↓
(Final Validation – CLI)
  - build canonical df from RunState
  - validate_all (global truth)
        ↓
if ERROR → block export
else → export SampleSheet + Plan summary

config:

base_dir
    ↓
RunState
    ↓
load config.json
    ↓
apply to state
    ↓
load index preset
    ↓
render UI
```

2. Folder structure:

```text
samplesheet-tool/
│
├── README.md
├── pyproject.toml
├── .gitignore
│
├── data/
│   └── indexes/
│       └── tenx_dual_index_NN_setA.csv
│
├── src/
│   └── samplesheet_tool/
│       ├── __init__.py
│       ├── __main__.py        # CLI entry point
│       ├── context.py         # RunContext (shared state)
│       ├── io_basespace.py    # read/write BaseSpace template
│       ├── resolve.py         # index ID -> index sequence resolver
│       ├── validate.py        # sample ID & index checks
│       ├── indexes.py         # index loaders
│       ├── config.py          # defaults & thresholds
│       ├── utils.py           # helpers (lanes, hamming, parsing)
│       └── io_normalize.py    # rename headers
│
└── tests/                     # test codes

intermediate & default output folder

~/.samplesheet_tool/
│
├── config.json
│
├── plans/
│   ├── plan_20260210_120001.json
│
├── temp/
│   ├── validate/
│   ├── import/
│
├── outputs/
│   ├── 20260210_run1/
│       ├── samplesheet_iem.csv
│       ├── samplesheet_basespace.csv
│
└── index_preset.json
```

3. Logic:

## Lane Status Resolution Priority

Lane status (`lane.status`) is determined by two validation stages with clear responsibilities.

### Validation Stages

- **Lane-local validation** (`lane_local_validate`)
  - Fast, per-lane checks
  - Does NOT consider other lanes
  - Runs on every lane mutation

- **Final validation** (CLI-based)
  - Run-level and sequencing-level checks
  - May add additional warnings or errors
  - Does NOT override lane-local hard errors

---

### Lane Status Resolution Rules

| Lane-local Status | Final Validation Result | Final Lane Status | Explanation |
|------------------|-------------------------|-------------------|-------------|
| OK | No issues | OK | Fully valid |
| OK | WARNING (e.g. barcode mismatch = 0) | WARNING | Final validation adds risk |
| OK | ERROR (lane-specific) | ERROR | Final validation escalates |
| WARNING | No issues | WARNING | Lane-local warning remains |
| WARNING | WARNING | WARNING | Same severity |
| WARNING | ERROR | ERROR | Escalated by final validation |
| ERROR | Any result | ERROR | Lane-local hard error is never downgraded |

---

### Notes

- Lane-local validation checks:
  - Duplicate `sample_id` within a lane
  - Duplicate index within a lane
  - Lane read count exceeding capacity

- Final validation checks:
  - Index distance / barcode mismatch
  - Cross-lane or run-level constraints

- Run-level errors (not associated with a specific lane) do **not** modify any lane status.
  They are displayed as a separate **run-level error indicator** in the UI and block export.


