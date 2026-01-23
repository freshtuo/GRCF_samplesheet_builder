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

