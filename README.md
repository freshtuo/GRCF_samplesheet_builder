# 📦 SampleSheet Tool

A UI-based tool for planning and exporting sequencing SampleSheets.

Designed for structured lane planning, validation, and reproducible run configuration management.

## 🔍 Overview

SampleSheet Tool helps users:

- Configure sequencing run settings (flowcell, lanes, read length)

- Import project sample metadata

- Assign samples to lanes

- Validate lane-level and run-level constraints

- Export standardized SampleSheet files

- Save and reload planning snapshots (Plans)

The system ensures:

- Deterministic validation logic

- Runtime snapshot persistence in saved plans

- Cross-platform compatibility

- Structured export organization

## 🖥 UI Panels

The interface consists of several main panels:

### 1️⃣ Settings Panel

Configure runtime parameters:

- Flowcell type (1.5B / 10B / 25B)

- Number of lanes

- Lane capacity

- Read 1 / Read 2 length

- Output directory

Changing flowcell settings clears lane assignments (new run planning assumed).

### 2️⃣ Project Panel

- Import project metadata (CSV)

- View project-level summary

- Remove projects (does not automatically remove from lanes)

### 3️⃣ Lane Panel

- Assign projects to lanes

- View per-lane read allocation

- See lane-level validation status (green/yellow/red)

### 4️⃣ Validation Panel

Two-level validation:

- Lane-local validation (per lane)

- Final global validation (cross-lane checks)

Export is blocked if validation fails.

## 🚀 Basic Workflow

1. Configure runtime settings.

2. Import project file.

3. Assign projects to lanes.

4. Resolve any lane errors (red indicators).

5. Run final validation.

6. Export SampleSheet.

7. Optionally save plan for later reuse.

## 💾 Plan Persistence

Each saved plan stores:

- Lane assignments

- Project layout

- Runtime snapshot (flowcell, lanes, read lengths)

Loading a plan restores its runtime environment automatically.

## 🧱 Installation
Requirements

- Python 3.9+

- pip

### Clone Repository
```bash
git clone https://github.com/your-organization/samplesheet-tool.git
cd samplesheet-tool
```
### Create Virtual Environment (Recommended)
#### Windows:
```bash
python -m venv venv
venv\Scripts\activate
```
#### macOS / Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```
### Install
```bash
pip install -e .
```
## ▶ Run the Application
```bash
python -m samplesheet_tool.ui
```

The application will launch in your browser.

## 🗂 Directory Structure

The application uses a fixed base directory:
```markdown
~/.samplesheet_tool/
```

Structure:
```markdown
config.json
plans/
temp/
outputs/
```

Exports are written to:
```markdown
outputs/run_YYYYMMDD_HHMMSS/
```
## 🐞 Reporting Issues

If you encounter a bug:

1. Check that validation errors are resolved.

2. Confirm your runtime settings.

3. Provide:

  - Application version

  - OS (Windows/macOS/Linux)

  - Steps to reproduce

  - Relevant error message

Please report issues via:

- GitHub Issues (recommended)

- Or contact the project maintainer

## 📘 Documentation

- Developer Architecture → docs/ARCHITECTURE.md

- Detailed Usage Manual → docs/MANUAL.md (if created)

## 🔖 Versioning

Version is managed in:
```markdown
pyproject.toml
```

Application version is dynamically retrieved via:
```python
importlib.metadata.version("samplesheet-tool")
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


