# project_io.py
# import project from file
# 

from __future__ import annotations

from typing import Optional, Literal
from pathlib import Path
import re
import pandas as pd

from samplesheet_tool.ui.state import Project, Sample
from samplesheet_tool.utils import normalize_seq
from samplesheet_tool.config import SAMPLE_ID_ALLOWED


# ============================================================
# IO helpers
# ============================================================

def read_project_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t", comment="#")
    if suffix == ".csv":
        return pd.read_csv(path, comment="#")
    raise ValueError(f"Unsupported file type: {path.name}")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


# ============================================================
# Pre-check helpers (schema / presence only)
# ============================================================

def check_sample_id_schema(df: pd.DataFrame) -> None:
    if df["sample_id"].isna().any():
        rows = df.index[df["sample_id"].isna()].tolist()[:5]
        raise ValueError(f"sample_id is missing at rows {rows}")


def check_index_presence(df: pd.DataFrame, prefix: str) -> None:
    id_col = f"{prefix}_index_id"
    seq_col = f"{prefix}_index_seq"

    bad = (
        df[id_col].fillna("").astype(str).str.strip().eq("")
        & df[seq_col].fillna("").astype(str).str.strip().eq("")
    )
    if bad.any():
        rows = df.index[bad].tolist()[:5]
        raise ValueError(
            f"{prefix.upper()} index: both ID and SEQ missing (rows: {rows})"
        )


def check_required_reads(df: pd.DataFrame) -> None:
    if "required_reads_m" not in df.columns:
        return

    df["required_reads_m"] = pd.to_numeric(
        df["required_reads_m"], errors="raise"
    )

    bad = df["required_reads_m"] < 0
    if bad.any():
        rows = df.index[bad].tolist()[:5]
        raise ValueError(f"required_reads_m must be >= 0 (rows: {rows})")


# ============================================================
# Post-check helpers (after lookup)
# ============================================================

def check_sample_ids(df: pd.DataFrame) -> None:
    pat = re.compile(SAMPLE_ID_ALLOWED)

    bad_mask = ~df["sample_id"].astype(str).str.match(pat)
    if bad_mask.any():
        bad_ids = df.loc[bad_mask, "sample_id"].astype(str).unique().tolist()
        raise ValueError(
            f"Invalid sample_id(s): {bad_ids[:5]} "
            f"(allowed regex: {SAMPLE_ID_ALLOWED})"
        )

    if df["sample_id"].duplicated().any():
        dups = df.loc[df["sample_id"].duplicated(), "sample_id"].unique().tolist()
        raise ValueError(f"Duplicate sample_id within project: {dups[:5]}")


def check_index_seq_uniqueness(
    samples: list[Sample],
    index_type: str,
) -> None:
    if index_type == "single":
        seqs = [s.i7_seq for s in samples]
        dup = pd.Series(seqs).duplicated()
        if dup.any():
            bad = list({seqs[i] for i in dup[dup].index})
            raise ValueError(f"Duplicate i7 index sequence detected: {bad[:5]}")
    else:
        pairs = [(s.i7_seq, s.i5_seq) for s in samples]
        dup = pd.Series(pairs).duplicated()
        if dup.any():
            bad = list({pairs[i] for i in dup[dup].index})
            raise ValueError(
                f"Duplicate (i7,i5) index pair detected: {bad[:5]}"
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
    default_required_reads_m: Optional[int],
) -> Project:

    if index_type not in {"single", "dual"}:
        raise ValueError(f"Invalid index_type: {index_type}")

    # ------------------------
    # Read & normalize
    # ------------------------
    df_raw = read_project_table(file_path)
    df = normalize_columns(df_raw)

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
        raise ValueError(f"Missing required column(s): {sorted(missing)}")

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

    single_lookup = state.index_tables.single
    dual_lookup = state.index_tables.dual

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
                    raise ValueError(f"{sid}: i7 index ID '{i7_id}' not found")
        else: # dual index
            if i7_seq and i5_seq: # both sequences explicitly provided, keep them, do nothing
                pass
            elif i7_id and i5_id and i7_id == i5_id: # paired lookup
                pair = dual_lookup.get(i7_id)
                if not pair:
                    raise ValueError(f"{sid}: paired index ID '{i7_id}' not found")
                i7_seq = pair["i7"]
                i5_seq = pair["i5"]
            else:
                if not i7_seq:
                    i7_seq = single_lookup.get(i7_id)
                    if not i7_seq:
                        raise ValueError(f"{sid}: i7 index ID '{i7_id}' not found")
                if not i5_seq:
                    i5_seq = single_lookup.get(i5_id)
                    if not i5_seq:
                        raise ValueError(f"{sid}: i5 index ID '{i5_id}' not found")

        if "required_reads_m" in df.columns and pd.notna(r["required_reads_m"]):
            req = int(r["required_reads_m"])
        else:
            req = default_required_reads_m

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

