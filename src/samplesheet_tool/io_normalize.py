# io_normalize.py
# enforce column names + normalize index sequences to uppercase
# 

# src/samplesheet_tool/io_normalize.py
from __future__ import annotations

import re
import pandas as pd

from samplesheet_tool.config import (
    COL_LANE, COL_SAMPLE_ID, COL_PROJECT_ID, 
    COL_I7, COL_I5, COL_I7_ID, COL_I5_ID,
    REQUIRED_CANONICAL_COLS, 
    LANE_RANGE
)

from samplesheet_tool.utils import normalize_seq


def check_required_columns(df: pd.DataFrame) -> None:
    missing = REQUIRED_CANONICAL_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"Missing required columns in input: {sorted(missing)}. "
            f"Found columns: {list(df.columns)}"
        )


def _norm_id(x) -> str:
    """convert missing index ids to ''. """
    if pd.isna(x):
        return ""
    v = str(x).strip()
    return "" if v.lower() == "nan" else v


def normalize_minimal(df: pd.DataFrame) -> pd.DataFrame:
    """
    Minimal normalization after strict schema check:
    - strip strings for IDs and sample/project
    - uppercase/strip sequences if present
    No renaming, no guessing.
    """
    check_required_columns(df)
    out = df.copy()

    # We keep these names fixed based on config's REQUIRED_CANONICAL_COLS
    # (do not rename)
    for col in [COL_SAMPLE_ID, COL_PROJECT_ID]:
        out[col] = out[col].astype(str).str.strip()

    # lane: strict int
    out[COL_LANE] = out[COL_LANE].astype(int)

    # index ids: preserve blanks as ""
    out[COL_I7_ID] = out[COL_I7_ID].map(_norm_id)
    out[COL_I5_ID] = out[COL_I5_ID].map(_norm_id)

    # index sequences: uppercase / strip spaces
    out[COL_I7] = out[COL_I7].map(normalize_seq)
    out[COL_I5] = out[COL_I5].map(normalize_seq)

    return out


def expand_lanes(df: pd.DataFrame, lane_col: str = COL_LANE) -> pd.DataFrame:
    """multi-lane in one row -> expand to one row per lane, e.g. 1,2,4 -> three rows"""
    if lane_col not in df.columns:
        raise ValueError(f"Missing required column: {lane_col}")

    s = df[lane_col].astype(str).str.strip()

    # reject empty / nan-like
    if (s.eq("") | s.str.lower().eq("nan")).any():
        bad = df.index[s.eq("") | s.str.lower().eq("nan")].tolist()
        raise ValueError(f"lane is empty/NaN at row(s): {bad[:20]}" + (" ..." if len(bad) > 20 else ""))

    # strict format check: only digits 1-8 separated by comma/space (no trailing separators)
    # Examples allowed: "1", "1,2", "1, 2  4"
    #   (?: ) -> group without capturing
    #   (?: ...)* -> non-capturing group, repeated zero or more times
    pattern = r"^[1-8](?:[,\s]+[1-8])*$"
    bad_fmt = ~s.str.match(pattern)
    if bad_fmt.any():
        bad = df.loc[bad_fmt, lane_col].head(10).tolist()
        raise ValueError(f"Invalid lane format. Expected like '1' or '1,2,4' (1-8 only). Bad examples: {bad}")

    # split -> explode
    lanes = s.str.split(r"[,\s]+", regex=True)

    out = df.copy()
    out[lane_col] = lanes
    out = out.explode(lane_col, ignore_index=True)

    # convert to int
    out[lane_col] = out[lane_col].astype(int)

    # duplicates within original row? (e.g. "1,1,2") is already blocked by regex? actually regex allows it.
    # so we explicitly detect duplicates per original row before explode:
    # easiest: compute per-row duplication before explode
    # We'll do it using the list series 'lanes' we already have.
    dup_mask = lanes.apply(lambda xs: len(xs) != len(set(xs)))
    if dup_mask.any():
        bad_rows = df.index[dup_mask].tolist()
        raise ValueError(f"Duplicate lane numbers within lane cell at row(s): {bad_rows[:20]}" + (" ..." if len(bad_rows) > 20 else ""))

    return out

