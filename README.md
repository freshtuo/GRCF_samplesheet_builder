# 📦 SampleSheet Tool

A UI-based tool for planning and exporting sequencing SampleSheets.

Designed for structured lane planning, validation, reproducible run configuration management, and lightweight team collaboration through a shared catalog folder.

## 🚀 What This Tool Does

- Configure sequencing run settings (flowcell, lanes, read length)

- Share imported index sets and projects across 2-3 users through a shared folder

- Automatically detect shared catalog updates in the background and refresh index/project UI when needed

- Import project sample metadata

- Assign samples to lanes

- Manage shared projects in a sortable dialog with batch removal

- Review messages in both a compact monitor and a detailed dialog view

- Validate lane-level and run-level constraints

- Export standardized SampleSheet files

- Save and reload planning snapshots (Plans)

- Keep sequencing plans private per user while reusing the same shared project catalog

- Refresh lane-related UI locally so edits do not bounce the user back to the top lanes

## 🧱 Installation
Requirements

- Python 3.9+

- pip

### Clone Repository
```bash
git clone https://github.com/freshtuo/GRCF_samplesheet_builder.git
cd GRCF_samplesheet_builder
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
pip install .
```

### Upgrade Note
If you are installing a new version over an older local setup, remove old local UI config files before starting the app when formats are not backward compatible.

Typical files to remove are:
- `~/.samplesheet_tool_ui/config.json`
- `~/.samplesheet_tool_ui/index_preset.json` if you still have that legacy file from an older version

This lets the app rebuild fresh local settings for the new version.

## 🖥 Run the Application
```bash
python -m samplesheet_tool.ui
```

The application will launch in your browser.

## 📘 Documentation

📘 Full User Guide → [USER_GUIDE.md](docs/USER_GUIDE.md)

🧠 Developer Architecture → [ARCHITECTURE.md](docs/ARCHITECTURE.md)

## 🗂 Storage Model

The application now uses two storage locations.

Local per-user workspace:

```markdown
~/.samplesheet_tool_ui/
```

Structure:
```markdown
config.json
plans/
temp/
outputs/
```

Shared catalog folder configured in the Settings dialog:

```markdown
<shared_catalog_dir>/
├── indexes.json
└── projects/
    ├── PROJECT_A.json
    └── PROJECT_B.json
```

Notes:
- `config.json`, plans, temp files, outputs, lane assignments, and validation state stay local per user.
- `indexes.json` and `projects/*.json` are shared across users.
- `indexes.json` now stores imported `index_sets` plus `flattened_indexes` used for auto-fill.
- Importing an index table requires a unique index set name; users can later inspect and remove one imported set at a time from the Indexes panel.
- If you change the shared catalog folder, copy existing shared files to the new location if you want to keep using them.
- The app polls the shared catalog in the background. Index updates are applied quietly in memory; project changes trigger a safe UI refresh when no modal dialog is open.
- If shared catalog access fails, the app can continue using the last loaded in-memory snapshot and will show a warning banner.
- On Windows web sessions, enter Output/Shared folder paths manually in Settings. Native Tk folder pickers are disabled there because they can interrupt the browser connection.

Exports are written to the local `outputs/` directory unless changed in Settings.
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
