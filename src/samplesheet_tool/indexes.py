# indexes.py
# index loaders: Load index ID <--> sequence mapping table
# 

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple, Optional, Iterable, List
import pandas as pd

from samplesheet_tool.utils import normalize_seq


def load_single_index_table(
    path: str | Path,
    *,
    id_col: str,
    seq_col: str,
) -> pd.DataFrame:
    """
    Load a single-index table (Illumina-style), one ID -> one sequence.
    Returns canonical columns: Index_ID, Index_Seq
    """
    path = Path(path)
    df = pd.read_csv(path)

    missing = {id_col, seq_col} - set(df.columns)
    if missing:
        raise ValueError(f"{path}: index table missing columns: {sorted(missing)}")

    out = pd.DataFrame({
        "Index_ID": df[id_col].astype(str).str.strip(),
        "Index_Seq": df[seq_col].map(normalize_seq),
    })

    # drop blank IDs (missing IDs)
    out = out[out["Index_ID"].astype(str).str.len() > 0].copy()

    # missing sequences?
    bad = out["Index_Seq"].isna()
    if bad.any():
        bad_ids = out.loc[bad, "Index_ID"].astype(str).unique().tolist()
        raise ValueError(
            f"Index table {path}: missing Index_Seq for Index_ID(s): {', '.join(bad_ids[:20])}"
            + (" ..." if len(bad_ids) > 20 else "")
        )

    # duplication check on Index ID
    dup = out["Index_ID"].duplicated(keep=False)
    if dup.any():
        dup_ids = out.loc[dup, "Index_ID"].astype(str).unique().tolist()
        raise ValueError(
            f"Index table {path}: duplicate Index_ID(s): {', '.join(dup_ids[:20])}"
            + (" ..." if len(dup_ids) > 20 else "")
        )

    # duplication check on Index sequence
    dup = out["Index_Seq"].duplicated(keep=False)
    if dup.any():
        dup_seqs = out.loc[dup, "Index_Seq"].astype(str).unique().tolist()
        raise ValueError(
            f"Index table {path}: duplicate Index_Seq(s): {', '.join(dup_seqs[:20])}"
            + (" ..." if len(dup_seqs) > 20 else "")
        )

    return out


def build_single_lookup(df: pd.DataFrame) -> Dict[str, str]:
    """{Index_ID -> Index_Seq}"""
    return {r["Index_ID"]: r["Index_Seq"] for _, r in df.iterrows()}


def load_paired_index_table(
    path: str | Path,
    *,
    pair_id_col: str = "Index_ID",
    i7_col: str = "Index_I7",
    i5_col: str = "Index_I5",
) -> pd.DataFrame:
    """
    Load a paired-index table (10x-style), one ID -> (i7_seq, i5_seq).
    Returns canonical columns: Pair_ID, Index_I7, Index_I5
    """
    path = Path(path)
    df = pd.read_csv(path)

    missing = {pair_id_col, i7_col, i5_col} - set(df.columns)
    if missing:
        raise ValueError(f"{path}: paired index table missing columns: {sorted(missing)}")

    out = pd.DataFrame({
        "Pair_ID": df[pair_id_col].astype(str).str.strip(),
        "Index_I7": df[i7_col].map(normalize_seq),
        "Index_I5": df[i5_col].map(normalize_seq),
    })

    # drop blank IDs
    out = out[out["Pair_ID"].astype(str).str.len() > 0].copy()

    # missing index IDs
    bad = out["Index_I7"].isna() | out["Index_I5"].isna()
    if bad.any():
        bad_ids = out.loc[bad, "Pair_ID"].astype(str).unique().tolist()
        raise ValueError(
            f"Paired index table {path}: missing Index_I7/Index_I5 for Pair_ID(s): {', '.join(bad_ids[:20])}"
            + (" ..." if len(bad_ids) > 20 else "")
        )

    # duplicated index IDs
    if out["Pair_ID"].duplicated().any():
        dups = out.loc[out["Pair_ID"].duplicated(keep=False), "Pair_ID"].unique().tolist()
        raise ValueError(f"{path}: duplicate Pair_ID values: {dups[:10]}{'...' if len(dups)>10 else ''}")

    return out


def build_pair_lookup(df: pd.DataFrame) -> Dict[str, Tuple[str, str]]:
    """{Pair_ID -> (i7_seq, i5_seq)}"""
    return {r["Pair_ID"]: (r["Index_I7"], r["Index_I5"]) for _, r in df.iterrows()}

def merge_single_lookups(lookups: Iterable[Dict[str, str]]) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    for lk in lookups:
        for k, v in lk.items():
            if k in merged and merged[k] != v:
                raise ValueError(f"Index ID collision for '{k}': '{merged[k]}' vs '{v}'")
            merged[k] = v
    return merged


def merge_pair_lookups(lookups: Iterable[Dict[str, Tuple[str, str]]]) -> Dict[str, Tuple[str, str]]:
    merged: Dict[str, Tuple[str, str]] = {}
    for lk in lookups:
        for k, v in lk.items():
            if k in merged and merged[k] != v:
                raise ValueError(f"Paired Index_ID collision for '{k}': {merged[k]} vs {v}")
            merged[k] = v
    return merged

