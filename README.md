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


