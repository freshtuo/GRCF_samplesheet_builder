# 📘 SampleSheet Tool – User Guide

This document describes how to use the SampleSheet Tool UI for sequencing lane planning and SampleSheet export.

For installation instructions, see [README.md](../README.md).

## 1️⃣ Application Overview

SampleSheet Tool is a UI-based sequencing planning system that allows you to:

- Configure run environment (flowcell, lanes, read length)

- Share imported index sets and projects through a shared folder

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
Used to manage shared imported index sets.

Indexes are shared through the configured shared catalog folder, so other users can see them after refreshing.
The app also checks for shared catalog changes in the background.

**Import Mapping Table**

When importing an index table, you must provide:
- Mapping type (`dual` or `single`)
- A unique index set name
- Column-role mapping for the uploaded file

Each import becomes one named index set in shared `indexes.json`.
The app then rebuilds the flattened shared lookup tables used during project import and auto-fill.

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

**Manage Index Sets**

The Indexes panel also includes a `Manage Index Sets` dialog.
There you can:
- switch between `dual` and `single` imported sets
- inspect one imported set at a time
- view uploader, upload time, and row count
- remove one imported set if it was added by mistake

Removing an index set rebuilds the shared flattened lookup tables automatically.
If another user already removed the same set, the app refreshes and shows a warning instead of failing.

### 📁 3.2 Projects Panel

Used to:
- Import project sample files (CSV/TSV)
- Select active project
- Remove the active project from the panel
- Open `Manage Projects` to review and remove multiple shared projects

Projects shown here come from the shared catalog folder.
If another user adds, removes, or replaces a project file with the same `project_id`, the app can detect that change and refresh the project UI automatically.

When importing a project you define:
- Project ID
- Index type (dual/single)
- Library type
- Sequencing type
- Default required reads per sample

Project removal:
- Removes it from the shared catalog
- Does NOT automatically modify lane assignments

Manage Projects dialog:
- Shows a sortable table of shared projects
- Displays project metadata in separate columns instead of one combined label
- Includes import metadata such as `imported_at` and `imported_by`
- Supports searching by project metadata, including index type and imported-by
- Supports selecting multiple projects and removing them in one confirmed action
- Handles already-deleted projects gracefully in multi-user cases

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

If selected sample-lane pairs already exist, the new assignment overwrites those existing planned reads.
The UI shows a notification when that happens.

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
- Remove one or more selected projects from a lane; this removes all samples related to those projects from that lane
- Clear entire lane

Lane-only edits refresh the lane-related UI locally, so the right-hand lane view should stay near the lane you are working on instead of jumping back to the top.

### 📢 3.5 Messages Panel
Centralized validation and system messages.

Shows:
- Validation errors
- Warnings

Supports:
- Search filter
- Lane filter
- Project filter
- Compact paginated monitor in the main layout
- `Detailed View` dialog for the full message table
- Clear index import messages in the detailed dialog

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
- On Windows web sessions, type or paste Output/Shared folder paths manually. Native folder pickers are intentionally disabled there because they can interrupt the web UI connection.

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

Supports filtering by:
- Project
- Lane

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

Use the `Refresh Shared` toolbar button when you want to force an immediate reload of indexes/projects.

Refresh behavior:
- reloads shared `indexes.json`
- reloads shared `projects/*.json`
- refreshes imported index sets and flattened index lookups
- keeps your local lane assignments unchanged
- if your selected project was deleted, the app selects the first available project

Automatic refresh behavior:
- the app polls the shared catalog in the background
- index updates are applied in memory without a full UI redraw
- project add/remove/content changes trigger a UI refresh when the app is in a safe steady state
- if a modal dialog is open, the refresh waits until the dialog is closed
- if shared catalog access fails, the app keeps the last loaded in-memory snapshot and shows a warning banner

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
