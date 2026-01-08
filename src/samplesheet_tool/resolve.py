# resolve.py
# index ID -> index sequence resolver
# 

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

from samplesheet_tool.config import (
    COL_I7, COL_I5, COL_I7_ID, COL_I5_ID,
    COL_LANE, COL_SAMPLE_ID
)
from samplesheet_tool.utils import Problem, normalize_seq


@dataclass(frozen=True)
class ResolveResult:
    df: pd.DataFrame
    problems: List[Problem]


def resolve_indexes(
    df: pd.DataFrame,
    *,
    i7_lookup: Dict[str, str],
    i5_lookup: Dict[str, str],
    pair_lookup: Optional[Dict[str, Tuple[str, str]]] = None,
    lane_col: str = COL_LANE,
    sample_id_col: str = COL_SAMPLE_ID,
    i7_id_col: str = COL_I7_ID,
    i5_id_col: str = COL_I5_ID,
    i7_seq_col: str = COL_I7,
    i5_seq_col: str = COL_I5,
) -> ResolveResult:
    """
    Fill missing i7/i5 sequences based on i7_id/i5_id.

    Resolution rules (strict, deterministic):
      1) If i7 & i5 sequences are present (non-empty): keep (normalized).
      2) Else resolve independently:
           i7 = i7_lookup[i7_id], i5 = i5_lookup[i5_id]
      3) Else if pair_lookup is provided and i7_id == i5_id and that ID exists in pair_lookup:
           fill both from pair_lookup (10x-style paired ID).
      4) Otherwise: ERROR.

    Sequences are normalized (strip + upper) when written.
    """
    out = df.copy()
    problems: List[Problem] = []

    # Normalize any existing sequences
    out[i7_seq_col] = out[i7_seq_col].map(normalize_seq)
    out[i5_seq_col] = out[i5_seq_col].map(normalize_seq)

    # Normalize IDs
    out[i7_id_col] = out[i7_id_col].astype(str).str.strip()
    out[i5_id_col] = out[i5_id_col].astype(str).str.strip()

    for idx, r in out.iterrows():
        lane = int(r[lane_col]) if lane_col in out.columns else None
        sid = str(r[sample_id_col]).strip() if sample_id_col in out.columns else None
        
        # index sequence
        i7_seq = r[i7_seq_col]
        i5_seq = r[i5_seq_col]
        
        # index id
        i7_id = str(r[i7_id_col]).strip()
        i5_id = str(r[i5_id_col]).strip()
        # --- Treat blank strings as missing ---
        i7_id = "" if (not i7_id or i7_id.lower() == "nan") else i7_id
        i5_id = "" if (not i5_id or i5_id.lower() == "nan") else i5_id

        # Case 1: sequences already present
        if i7_seq and i5_seq:
            continue

        # Case 2: paired lookup (10x style)
        # --- both i7 and i5 ids present and identical ---
        if i7_id and i5_id and (i7_id == i5_id):
            if not pair_lookup:
                problems.append(
                    Problem(
                        "ERROR", "PAIR_TABLE_NOT_PROVIDED",
                        "Paired index IDs provided (i7_id==i5_id), but no paired index table was loaded.",
                        lane=lane, sample_id=sid
                    )
                )
                continue
            if i7_id not in pair_lookup:
                problems.append(
                    Problem(
                        "ERROR", "PAIR_ID_NOT_FOUND",
                        f"paired Index_ID '{i7_id}' not found in paired index table.",
                        lane=lane, sample_id=sid
                    )
                )
                continue

            seq_i7, seq_i5 = pair_lookup[i7_id]
            out.at[idx, i7_seq_col] = normalize_seq(seq_i7)
            out.at[idx, i5_seq_col] = normalize_seq(seq_i5)
            continue  # done with this row

        # Case 3: independent resolution (Illumina TruSeq/Nextera style)
        # --- Resolve i7 if needed (required) ---
        if not i7_seq:
            if not i7_id:
                problems.append(
                    Problem(
                        "ERROR", "I7_MISSING",
                        "Missing i7 sequence and i7_id is empty.",
                        lane=lane, sample_id=sid
                    )
                )
            elif i7_id not in i7_lookup:
                problems.append(
                    Problem(
                        "ERROR", "I7_ID_NOT_FOUND",
                        f"i7_id '{i7_id}' not found in i7 index table.",
                        lane=lane, sample_id=sid
                    )
                )
            else:
                out.at[idx, i7_seq_col] = normalize_seq(i7_lookup[i7_id])
        # --- Resolve i5 if needed ---
        if not i5_seq and i5_id:
            if i5_id not in i5_lookup:
                problems.append(
                    Problem(
                        "ERROR", "I5_ID_NOT_FOUND",
                        f"i5_id '{i5_id}' not found in i5 index table.",
                        lane=lane, sample_id=sid
                    )
                )
            else:
                out.at[idx, i5_seq_col] = normalize_seq(i5_lookup[i5_id])

        # Final: require i7 sequence to exist after attempts
        if not out.at[idx, i7_seq_col]:
            problems.append(
                Problem(
                    "ERROR", "I7_SEQUENCE_NOT_RESOLVED",
                    "Could not resolve i7 sequence (required).",
                    lane=lane, sample_id=sid
                )
            )
        
    # Final normalization pass (cheap)
    out[i7_seq_col] = out[i7_seq_col].map(normalize_seq)
    out[i5_seq_col] = out[i5_seq_col].map(normalize_seq)

    return ResolveResult(df=out, problems=problems)

