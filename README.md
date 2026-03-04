# 📦 SampleSheet Tool

A UI-based tool for planning and exporting sequencing SampleSheets.

Designed for structured lane planning, validation, and reproducible run configuration management.

## 🚀 What This Tool Does

- Configure sequencing run settings (flowcell, lanes, read length)

- Import project sample metadata

- Assign samples to lanes

- Validate lane-level and run-level constraints

- Export standardized SampleSheet files

- Save and reload planning snapshots (Plans)

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
## 🖥 Run the Application
```bash
python -m samplesheet_tool.ui
```

The application will launch in your browser.

## 📘 Documentation

📘 Full User Guide → [USER_GUIDE.md](docs/USER_GUIDE.md)

🧠 Developer Architecture → [ARCHITECTURE.md](docs/ARCHITECTURE.md)

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

