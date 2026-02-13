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

