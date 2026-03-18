# 📘 SampleSheet Tool – User Guide

This document describes how to use the SampleSheet Tool UI for sequencing lane planning and SampleSheet export.

For installation instructions, see [README.md](../README.md).

## 1️⃣ Application Overview

SampleSheet Tool is a UI-based sequencing planning system that allows you to:

- Configure run environment (flowcell, lanes, read length)

- Share indexes and imported projects through a shared folder

- Import index mapping tables (dual or single)

- Import project sample metadata

- Assign samples to lanes

- Validate lane and run integrity

- Export SampleSheet files

- Save and reload planning snapshots (Plans)

Important distinction:
- shared: indexes and projects
- local per user: lane assignments, messages, validation state, saved plans, outputs

The application runs via:

```bash
python -m samplesheet_tool.ui
```

## 2️⃣ UI Layout Structure

The interface is divided into:

```text
Toolbar
------------------------------
| Index    | Samples | Lanes |              
|----------|         |       |
| Projects |         |       |
|----------|         |       |
| Messages |         |       |
------------------------------
```

The layout has:
- Left column: Indexes / Projects / Messages
- Center column: Samples
- Right column: Lanes

## 3️⃣ Persistent Panels (Always Visible)
These are not dialogs — they are permanent parts of the layout.

### 🧩 3.1 Index Panel
Used to manage index mapping tables.

Indexes are shared through the configured shared catalog folder, so other users can see them after refreshing.

**Import Mapping Table**

You can import index tables in two mapping modes:

**🔹 Dual Mapping Mode**

Use when each index ID corresponds to:

```text
index_id → i7 sequence + i5 sequence
```

File must contain:
- index_id
- i7 sequence
- i5 sequence

This is typical for dual-index kits.

**🔹 Single Mapping Mode**

Use when each index ID corresponds to:

```text
index_id → sequence
```

File must contain:
- index_id
- sequence

This is used when:
- only one index is defined
- or index is resolved independently

⚠️ Note:

This “single vs dual mapping” refers to index table structure —
it is NOT the same as sequencing type.

### 📁 3.2 Projects Panel

Used to:
- Import project sample files (CSV/TSV)
- Select active project
- Remove project from panel

Projects shown here come from the shared catalog folder.

When importing a project you define:
- Project ID
- Index type (dual/single)
- Library type
- Sequencing type
- Default required reads per sample

Project removal:
- Removes it from the shared catalog
- Does NOT automatically modify lane assignments

### 🧪 3.3 Samples Panel

Displays samples of the selected project.

Columns depend on project index type:

Dual-index project:
- sample_id
- i7_index_id
- i7_index_seq
- i5_index_id
- i5_index_seq
- required_reads_m (optional)

Single-index project:
- sample_id
- i7_index_id
- i7_index_seq
- required_reads_m (optional)

You can:
- Select multiple samples
- Add selected samples to one or more lanes
- Specify planned reads per sample per lane

### 🛣 3.4 Lane Panel
Displays lane planning summary.

Each lane shows:
- Status dot
- Used reads / Capacity
- Progress bar
- #projects
- #samples

Lane Status Colors

| Status | Meaning |
|---|---|
| 🟢 Green  | Valid |
| 🟠 Orange  | Warning |
| 🔴 Red | Error |

Errors block export.

You can:
- Remove specific project from lane, this will remove all samples related to this project
- Clear entire lane

### 📢 3.5 Messages Panel
Centralized validation and system messages.

Shows:
- Validation errors
- Warnings

Supports:
- Search filter
- Lane filter
- Project filter
- Clear index import messages

All validation results appear here.

## 4️⃣ Dialog-Based Views (Modal)

These are not panels — they open as pop-up dialogs.

### ⚙ 4.1 Settings Dialog

Used to configure runtime:
- Flowcell type (1.5B / 10B / 25B)
- Number of lanes
- Reads per lane capacity
- Read1 length
- Read2 length
- Output directory
- Shared Catalog Folder
- User Name (optional)
- Max saved plans

Changing settings:
- Clears lane assignments
- Keeps shared projects in the shared catalog

Notes:
- All collaborating users should set the same `Shared Catalog Folder`.
- If you switch to a different shared folder, copy `indexes.json` and the `projects/` folder there if you want to keep the existing shared data.

Settings are saved to:
```text
~/.samplesheet_tool_ui/config.json
```

### 📊 4.2 Summary Dialog
Provides three summary levels:

#### 1️⃣ Sample Summary (Most Important)

Shows per-sample allocation:

```text
| Project | Sample | Required | Allocated | Remaining | Status |
```

Status colors:

| Status | Meaning |
|---|---|
| ✓ OK | Exactly allocated |
| ▲ Under | Under-allocated |
| ● Over | Over-allocated |

This is the primary planning feedback table.

#### 2️⃣ Assignment Detail

Shows:

```text
Project → Sample → Lane → Allocated reads
```

Used for debugging distribution.

#### 3️⃣ Project Summary

Shows:
```text
Project → #Samples → Total allocated → Lanes used
```

High-level overview.

### 📂 4.3 Plan Management

Plans store:
- Runtime snapshot
- Lane assignments
- Messages
- UI selection state

Loading a plan restores:
- Flowcell
- Lane count
- Capacity
- Read lengths

Plans do not own the shared project catalog. The app reloads shared projects/indexes from the configured shared folder.

This guarantees reproducibility.

Plans stored in:
```text
~/.samplesheet_tool_ui/plans/
```

### 🔄 4.4 Refresh Shared Catalog

Use the `Refresh Shared` toolbar button when another user has imported or removed indexes/projects.

Refresh behavior:
- reloads shared `indexes.json`
- reloads shared `projects/*.json`
- keeps your local lane assignments unchanged
- if your selected project was deleted, the app selects the first available project

If your local lane plan still references a deleted shared project:
- validation shows an error
- export is blocked until the lane assignments are fixed

## 5️⃣ Validation Model

Validation has two layers:

### Lane-local Validation

Triggered when:
- Assigning samples
- Removing assignments
- Clearing lane

Checks:
- Lane capacity overflow
- Duplicate indexes in lane
- Duplicate samples in lane

Updates:
- Lane status dot
- Messages panel

### Final Global Validation

Triggered when:
- Clicking Validate
- Before Export

Checks:
- Cross-lane conflicts
- Run-level errors
- Export format requirements

Export is blocked if:
- Any lane is 🔴 Red
- Final validation produces error

## 6️⃣ Export SampleSheet

Export requires:
- Valid plan
- No lane-level errors
- No global errors
- Shared project metadata still present

You choose:
- Output directory
- File prefix

The tool supports exporting two different formats.
- BaseSpace Sequence Plan
    - Samples are grouped by sequencing type.
    - Each sequencing type will generate one separate file.
    - Each file represents one sequencing plan.

- IEM SampleSheet
    - A single file is generated.
    - The file contains all samples from all lanes.
    - Each row represents: Lane + Sample

Files are written to:
```text
output_dir/prefix.**
```

## 7️⃣ Recommended Workflow

1. Open Settings
2. Import index table
3. Import project(s)
4. Assign samples to lanes
5. Fix red lane errors
6. Check Sample Summary
7. Run Validate
8. Export

## 8️⃣ Directory Structure

```text
~/.samplesheet_tool/
│
├── config.json
├── plans/
├── temp/
└── outputs/
```
