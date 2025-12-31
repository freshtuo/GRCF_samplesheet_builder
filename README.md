# GRCF_samplesheet_builder
Organize samples for a sequencing run, and prepare samplesheet file

1. Folder structure:

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
│       ├── resolve.py         # index ID → sequence resolution
│       ├── validate.py        # sample ID & index checks
│       ├── tenx_indexes.py    # 10x index loaders
│       ├── config.py          # defaults & thresholds
│       └── utils.py           # helpers (lanes, hamming, parsing)
│
└── tests/                     # optional for now
```

