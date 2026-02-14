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

The application UI consists of:

### A. Persistent Panels

These are always visible in the main interface:

#### 1️⃣ Index Panel

  - Import index tables
  - Manage index presets
  - Auto-fill missing index values

#### 2️⃣ Project Panel
  - Import project metadata
  - View project list
  - Remove projects

#### 3️⃣ Sample Panel
  - Displays sample-level details for selected project
  - Review index and allocation information

#### 4️⃣ Lane Panel
  - Assign projects to lanes
  - View lane capacity usage
  - See lane validation status indicators

#### 5️⃣ Messages Panel
  - Displays warnings and errors
  - Displays validation results
  - Displays system messages

All validation feedback is pushed here.

### B. Dialog-Based Views

These are modal dialogs triggered by user actions.

#### Settings Dialog

Used to configure runtime parameters.

#### Summary Dialog

Provides multi-level allocation summaries:
  - Run-level
  - Project-level
  - Sample-level

#### Plan Management Dialog

Load or manage saved plans.

### C. Validation Mechanism (Background System)

Validation is not a UI panel.

It is a background logic system that:
  - Runs lane-local checks
  - Runs global final validation
  - Updates lane status indicators
  - Pushes messages to Messages Panel

Validation does not open a separate window.

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

- Runtime snapshot
- Projects
- Samples
- Lane assignments
- Validation state (if applicable)
- Index references (as needed)

Loading a plan restores its runtime environment automatically.

## 🧱 Installation
Requirements

- Python 3.9+

- pip

### Clone Repository
```bash
git clone https://github.com/freshtuo/samplesheet-tool.git
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
pip install .
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
outputs/
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

- Detailed Usage Manual can be found [here](docs/ARCHITECTURE.md)

## 🔖 Versioning

Version is managed in:
```markdown
pyproject.toml
```

Application version is dynamically retrieved via:
```python
importlib.metadata.version("samplesheet-tool")
```

