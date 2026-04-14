# project_io.py
# import project from file
# 

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal
from pathlib import Path
import re
import pandas as pd

from samplesheet_tool.ui.state import Project, Sample
from samplesheet_tool.ui.reads import coerce_reads_m
from samplesheet_tool.utils import normalize_seq
from samplesheet_tool.config import SAMPLE_ID_ALLOWED


@dataclass
class ProjectImportError(Exception):
    """Structured, user-facing import error for expected project file problems."""
    code: str
    summary: str
    details: list[str] = field(default_factory=list)
    notify_text: Optional[str] = None

    def __post_init__(self) -> None:
        super().__init__(self.summary)
        if self.notify_text is None:
            self.notify_text = self.summary


# ============================================================
# IO helpers
# ============================================================

def read_project_table(path: Path) -> pd.DataFrame:
    """Read a project table from TSV/TXT/CSV into a DataFrame."""
    suffix = path.suffix.lower()
    if suffix in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t", comment="#")
    if suffix == ".csv":
        return pd.read_csv(path, comment="#")
    raise ValueError(f"Unsupported file type: {path.name}")

# alias column names in project file
_COLUMN_ALIASES = {
    # sample ID
    "Sample ID": "sample_id", 

    # i7 id
    "I7 Index ID (Optional)": "i7_index_id", 

    # i7 seq
    "I7 Index Bases for Sample Sheet (forward orientation)": "i7_index_seq", 

    # i5 id
    "I5 Index ID (Optional)": "i5_index_id", 

    # i5 seq
    "I5 Index Bases for Sample Sheet (forward orientation)": "i5_index_seq"
}

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize project-table column names to the app's internal schema."""
    df = df.copy()

    renamed = {}
    for col in df.columns:
        renamed[col] = _COLUMN_ALIASES.get(col, col)

    df = df.rename(columns=renamed)

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


# ============================================================
# Pre-check helpers (schema / presence only)
# ============================================================

def check_sample_id_schema(df: pd.DataFrame) -> None:
    """Ensure the sample_id column exists row-by-row without missing values."""
    if df["sample_id"].isna().any():
        rows = df.index[df["sample_id"].isna()].tolist()[:5]
        raise ProjectImportError(
            code="missing_sample_id",
            summary="Some rows are missing sample IDs.",
            details=[f"Row {row + 1} is missing a sample ID." for row in rows],
            notify_text="Import failed. Some rows are missing sample IDs.",
        )


def check_index_presence(df: pd.DataFrame, prefix: str) -> None:
    """Require at least an index ID or sequence for each i7/i5 row."""
    id_col = f"{prefix}_index_id"
    seq_col = f"{prefix}_index_seq"

    bad = (
        df[id_col].fillna("").astype(str).str.strip().eq("")
        & df[seq_col].fillna("").astype(str).str.strip().eq("")
    )
    if bad.any():
        rows = df.index[bad].tolist()[:5]
        raise ProjectImportError(
            code=f"missing_{prefix}_index",
            summary=f"Some rows are missing {prefix.upper()} index information.",
            details=[f"Row {row + 1} is missing both {prefix.upper()} index ID and sequence." for row in rows],
            notify_text=f"Import failed. Some rows are missing {prefix.upper()} index information.",
        )


def check_required_reads(df: pd.DataFrame) -> None:
    """Validate that required_reads_m values are numeric and non-negative."""
    if "required_reads_m" not in df.columns:
        return

    df["required_reads_m"] = pd.to_numeric(
        df["required_reads_m"], errors="raise"
    )

    bad = df["required_reads_m"] < 0
    if bad.any():
        rows = df.index[bad].tolist()[:5]
        raise ProjectImportError(
            code="invalid_required_reads",
            summary="Some required read values are negative.",
            details=[f"Row {row + 1} has required_reads_m < 0." for row in rows],
            notify_text="Import failed. Some required read values are negative.",
        )


def resolve_default_required_reads_per_sample(
    *, 
    n_samples: int, 
    required_reads_mode: Literal["per_sample", "per_project"], 
    default_required_reads_m: Optional[float], 
) -> Optional[float]:
    """
    Convert dialog input to per-sample required reads (M). 
    Keep storage uniform for downstream logic.
    """
    if default_required_reads_m is None:
        return None

    value = coerce_reads_m(default_required_reads_m)
    if value <= 0:
        raise ProjectImportError(
            code="invalid_default_reads",
            summary="Default required reads must be greater than 0.",
            notify_text="Import failed. Default required reads must be greater than 0.",
        )

    if required_reads_mode == "per_sample":
        return value
    elif required_reads_mode == "per_project":
        if n_samples <= 0:
            raise ProjectImportError(
                code="empty_project_file",
                summary="The uploaded project file contains no samples.",
                notify_text="Import failed. The uploaded project file contains no samples.",
            )
        return value / n_samples
    else:
        raise ProjectImportError(
            code="invalid_required_reads_mode",
            summary="The selected required reads mode is not supported.",
            notify_text="Import failed. The selected required reads mode is not supported.",
        )


# ============================================================
# Post-check helpers (after lookup)
# ============================================================

def check_sample_ids(df: pd.DataFrame) -> None:
    """Validate sample_id format and uniqueness within one project file."""
    pat = re.compile(SAMPLE_ID_ALLOWED)

    bad_mask = ~df["sample_id"].astype(str).str.match(pat)
    if bad_mask.any():
        bad_ids = df.loc[bad_mask, "sample_id"].astype(str).unique().tolist()
        examples = []
        for sid in bad_ids[:5]:
            bad_chars = sorted({ch for ch in sid if not re.fullmatch(r"[A-Za-z0-9._-]", ch)})
            rendered = [repr(ch)[1:-1] if ch != " " else "space" for ch in bad_chars]
            examples.append(f"'{sid}' contains {', '.join(rendered)}")
        raise ProjectImportError(
            code="invalid_sample_id",
            summary=(
                "Some sample IDs contain unsupported characters. "
                "Allowed characters are letters, numbers, dot (.), underscore (_), and hyphen (-)."
            ),
            details=examples,
            notify_text="Import failed. Some sample IDs contain unsupported characters.",
        )

    if df["sample_id"].duplicated().any():
        dups = df.loc[df["sample_id"].duplicated(), "sample_id"].unique().tolist()
        raise ProjectImportError(
            code="duplicate_sample_id",
            summary="Some sample IDs appear more than once in the uploaded project file.",
            details=[f"Duplicate sample ID: {value!r}" for value in dups[:5]],
            notify_text="Import failed. Some sample IDs are duplicated.",
        )


def check_index_seq_uniqueness(
    samples: list[Sample],
    index_type: str,
) -> None:
    """Ensure index sequences are unique within the imported project."""
    if index_type == "single":
        seqs = [s.i7_seq for s in samples]
        dup = pd.Series(seqs).duplicated()
        if dup.any():
            bad = list({seqs[i] for i in dup[dup].index})
            raise ProjectImportError(
                code="duplicate_i7_sequence",
                summary="Some i7 index sequences appear more than once in the uploaded project file.",
                details=[f"Duplicate i7 sequence: {value}" for value in bad[:5]],
                notify_text="Import failed. Some i7 index sequences are duplicated.",
            )
    else:
        pairs = [(s.i7_seq, s.i5_seq) for s in samples]
        dup = pd.Series(pairs).duplicated()
        if dup.any():
            bad = list({pairs[i] for i in dup[dup].index})
            raise ProjectImportError(
                code="duplicate_index_pair",
                summary="Some (i7, i5) index pairs appear more than once in the uploaded project file.",
                details=[f"Duplicate pair: {value}" for value in bad[:5]],
                notify_text="Import failed. Some index pairs are duplicated.",
            )


# ============================================================
# Main entry
# ============================================================

def import_project_from_file(
    *,
    state,
    project_id: str,
    index_type: Literal["single", "dual"],
    library_type: Optional[str],
    sequencing_type: Optional[str], 
    file_path: Path,
    default_required_reads_m: Optional[float], 
    required_reads_mode: Literal["per_sample", "per_project"] = "per_sample", 
) -> Project:
    """Read, validate, and convert one project file into a Project object."""

    if index_type not in {"single", "dual"}:
        raise ProjectImportError(
            code="invalid_index_type",
            summary="The selected index type is not supported.",
            notify_text="Import failed. The selected index type is not supported.",
        )

    # ------------------------
    # Read & normalize
    # ------------------------
    df_raw = read_project_table(file_path)
    df = normalize_columns(df_raw)

    # ------------------------------------------------
    # Drop completely empty rows (common in Excel/iLab exports)
    # ------------------------------------------------
    df = df.replace(r'^\s*$', pd.NA, regex=True)
    df = df.dropna(how="all").reset_index(drop=True)

    default_required_reads_per_sample_m = resolve_default_required_reads_per_sample(
        n_samples=len(df), 
        required_reads_mode=required_reads_mode, 
        default_required_reads_m=default_required_reads_m, 
    )

    # ------------------------
    # Schema enforcement
    # ------------------------
    required_cols = {
        "sample_id",
        "i7_index_id",
        "i7_index_seq",
    }
    if index_type == "dual":
        required_cols |= {
            "i5_index_id",
            "i5_index_seq",
        }

    missing = required_cols - set(df.columns)
    if missing:
        missing_cols = sorted(missing)
        raise ProjectImportError(
            code="missing_required_columns",
            summary="The uploaded project file is missing required columns.",
            details=[f"Missing column: {col}" for col in missing_cols],
            notify_text=f"Import failed. Missing required columns: {', '.join(missing_cols)}",
        )

    # ------------------------
    # Pre-checks (schema / presence)
    # ------------------------
    check_sample_id_schema(df)
    check_required_reads(df)
    check_index_presence(df, "i7")
    if index_type == "dual":
        check_index_presence(df, "i5")

    # ------------------------
    # Lookup & build samples
    # ------------------------
    samples: list[Sample] = []

    single_lookup = state.catalog.index_tables.single
    dual_lookup = state.catalog.index_tables.dual

    for _, r in df.iterrows():
        sid = str(r["sample_id"]).strip()

        i7_id = str(r["i7_index_id"]).strip() or None
        i7_seq = normalize_seq(r["i7_index_seq"])

        i5_id = None
        i5_seq = None
        if index_type == "dual":
            i5_id = str(r["i5_index_id"]).strip() or None
            i5_seq = normalize_seq(r["i5_index_seq"])

        if index_type == "single": # single index
            if not i7_seq:
                i7_seq = single_lookup.get(i7_id)
                if not i7_seq:
                    raise ProjectImportError(
                        code="missing_i7_lookup",
                        summary="Some index IDs in the uploaded project file were not found in the loaded index tables.",
                        details=[f"Sample '{sid}' uses unknown i7 index ID {i7_id!r}."],
                        notify_text="Import failed. Some index IDs were not found in the loaded index tables.",
                    )
        else: # dual index
            if i7_seq and i5_seq: # both sequences explicitly provided, keep them, do nothing
                pass
            elif i7_id and i5_id and i7_id == i5_id: # paired lookup
                pair = dual_lookup.get(i7_id)
                if not pair:
                    raise ProjectImportError(
                        code="missing_paired_lookup",
                        summary="Some paired index IDs in the uploaded project file were not found in the loaded index tables.",
                        details=[f"Sample '{sid}' uses unknown paired index ID {i7_id!r}."],
                        notify_text="Import failed. Some paired index IDs were not found in the loaded index tables.",
                    )
                i7_seq = pair["i7"]
                i5_seq = pair["i5"]
            else:
                if not i7_seq:
                    i7_seq = single_lookup.get(i7_id)
                    if not i7_seq:
                        raise ProjectImportError(
                            code="missing_i7_lookup",
                            summary="Some index IDs in the uploaded project file were not found in the loaded index tables.",
                            details=[f"Sample '{sid}' uses unknown i7 index ID {i7_id!r}."],
                            notify_text="Import failed. Some index IDs were not found in the loaded index tables.",
                        )
                if not i5_seq:
                    i5_seq = single_lookup.get(i5_id)
                    if not i5_seq:
                        raise ProjectImportError(
                            code="missing_i5_lookup",
                            summary="Some index IDs in the uploaded project file were not found in the loaded index tables.",
                            details=[f"Sample '{sid}' uses unknown i5 index ID {i5_id!r}."],
                            notify_text="Import failed. Some index IDs were not found in the loaded index tables.",
                        )

        if "required_reads_m" in df.columns and pd.notna(r["required_reads_m"]):
            req = coerce_reads_m(r["required_reads_m"])
        else:
            req = default_required_reads_per_sample_m

        samples.append(
            Sample(
                sample_id=sid,
                project_id=project_id,
                i7_id=i7_id,
                i7_seq=i7_seq,
                i5_id=i5_id,
                i5_seq=i5_seq,
                required_reads_m=req,
            )
        )

    # ------------------------
    # Post-checks (semantic)
    # ------------------------
    check_sample_ids(df)
    check_index_seq_uniqueness(samples, index_type)

    return Project(
        project_id=project_id,
        samples=samples,
        library_type=library_type,
        index_type=index_type,
        sequencing_type=sequencing_type, 
    )
