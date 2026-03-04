# 📘 SampleSheet Tool – User Guide

This document describes how to use the SampleSheet Tool UI for sequencing lane planning and SampleSheet export.

For installation instructions, see [README.md](README.md).

## 1️⃣ Application Overview

SampleSheet Tool is a UI-based sequencing planning system that allows you to:

- Configure run environment (flowcell, lanes, read length)

- Import index mapping tables (dual or single)

- Import project sample metadata

- Assign samples to lanes

- Validate lane and run integrity

- Export SampleSheet files

- Save and reload planning snapshots (Plans)

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

** Import Mapping Table **

You can import index tables in two mapping modes:

** 🔹 Dual Mapping Mode **

Use when each index ID corresponds to:

```text
index_id → i7 sequence + i5 sequence
```

File must contain:
- index_id
- i7
- i5

This is typical for dual-index kits.

** 🔹 Single Mapping Mode **

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





