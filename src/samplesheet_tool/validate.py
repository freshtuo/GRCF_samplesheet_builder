# validate.py
# sample ID & index checks
# 

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

import pandas as pd

from samplesheet_tool.config import (
    SAMPLE_ID_ALLOWED, 
    DEFAULT_BARCODE_MISMATCHES,
    HAMMING_WARN,
    HAMMING_WARN_TIGHTEN,
    HAMMING_OK_MIN,
    COL_LANE, COL_SAMPLE_ID, COL_PROJECT_ID, COL_I7, COL_I5
)
from samplesheet_tool.utils import Problem, hamming, normalize_seq


# ---------- helpers (lane-level trimming) ----------

def _trim_to_lane_min(seqs: List[str]) -> List[str]:
    """Trim sequences to the lane-wise minimum length (for fair Hamming distance)."""
    ##seqs = [normalize_seq(s) for s in seqs if normalize_seq(s)]
    if not seqs:
        return []
    min_len = min(len(s) for s in seqs)
    return [s[:min_len] for s in seqs]


def _min_pairwise_hamming(seqs: List[str]) -> Optional[int]:
    """Min pairwise Hamming among unique sequences; None if < 2 unique sequences."""
    # seqs must already be same length
    uniq = sorted(set(seqs))
    if len(uniq) < 2:
        return None
    m: Optional[int] = None
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            d = hamming(uniq[i], uniq[j])
            if d is None:
                continue
            m = d if m is None else min(m, d)
    return m


def _min_hamming_between_sets(a: List[str], b: List[str]) -> Optional[int]:
    """
    Minimum Hamming distance between any seq in a and any seq in b.
    Returns None if either set has <1 element.
    """
    if not a or not b:
        return None
    m: Optional[int] = None
    for x in a:
        for y in b:
            d = hamming(x, y)
            if d is None:
                continue
            m = d if m is None else min(m, d)
    return m


def _min_effective_pair_distance(i7_by_row: List[Optional[str]], i5_by_row: List[Optional[str]]) -> Optional[int]:
    """
    For dual-index-only lanes: define a pairwise "effective distance" as:
        d_eff = max(d_i7, d_i5)
    using lane-trimmed i7/i5 sequences.

    Then return min(d_eff) across all sample pairs.
    """
    n = len(i7_by_row)
    if n < 2:
        return None

    m: Optional[int] = None
    for i in range(n):
        for j in range(i + 1, n):
            # any missing sequences?
            if i7_by_row[i] is None or i7_by_row[j] is None or i5_by_row[i] is None or i5_by_row[j] is None:
                continue
            # hamming distance for i7
            d7 = hamming(i7_by_row[i], i7_by_row[j])
            # hamming distance for i5
            d5 = hamming(i5_by_row[i], i5_by_row[j])
            if d7 is None or d5 is None:
                continue
            deff = max(d7, d5)
            m = deff if m is None else min(m, deff)
    return m


@dataclass(frozen=True)
class ValidationSummary:
    problems: List[Problem]
    lane_barcode_mismatches: Dict[int, int]


# ---------- main validations ----------

def validate_sample_ids(
    df: pd.DataFrame,
    *,
    lane_col: str = "lane",
    sample_id_col: str = "sample_id",
    project_id_col: str = "project_id",
) -> List[Problem]:
    """
    Rules:
      - Sample ID chars must match SAMPLE_ID_ALLOWED
      - Uniqueness enforced per lane (same sample can appear in multiple lanes)
      - Additionally: sample_id should not map to multiple project_ids across the run
        (iLab constraint: prevents cross-project collisions)
    """
    probs: List[Problem] = []
    pat = re.compile(SAMPLE_ID_ALLOWED)

    # 1) valid sample ID?
    bad_mask = ~df[sample_id_col].astype(str).apply(lambda x: bool(pat.match(x)))
    if bad_mask.any():
        for _, r in df.loc[bad_mask, [lane_col, sample_id_col]].iterrows():
            probs.append(
                Problem(
                    level="ERROR",
                    code="SAMPLE_ID_INVALID",
                    message=f"Sample ID contains invalid characters. Allowed regex: {SAMPLE_ID_ALLOWED}",
                    lane=int(r[lane_col]),
                    sample_id=str(r[sample_id_col])
                )
            )

    # 2) uniqueness per lane
    for lane, td in df.groupby(lane_col):
        lane = int(lane)
        dup = td[sample_id_col].astype(str).duplicated(keep=False)
        if dup.any():
            for sid in sorted(set(td.loc[dup, sample_id_col].astype(str).tolist())):
                probs.append(
                    Problem(
                        level="ERROR",
                        code="SAMPLE_ID_DUPLICATE_IN_LANE",
                        message=f"Lane {lane}: duplicate sample_id '{sid}' within lane.",
                        lane=lane,
                        sample_id=sid
                    )
                )

    # 3) cross-project collision check:
    # each sample_id should map to a single project_id, NO shared sample_id across projects!
    sid_to_projects = (
        df[[sample_id_col, project_id_col]]
        .astype(str)
        .groupby(sample_id_col)[project_id_col]
        .nunique()
    )
    collided = sid_to_projects[sid_to_projects > 1]
    if not collided.empty:
        bad_sids = collided.index.tolist()
        for sid in bad_sids:
            projects = sorted(df.loc[df[sample_id_col].astype(str) == str(sid), project_id_col].astype(str).unique().tolist())
            probs.append(
                Problem(
                    level="ERROR",
                    code="SAMPLE_ID_PROJECT_COLLISION",
                    message=f"sample_id '{sid}' appears in multiple projects: {', '.join(projects)}",
                    lane=None,
                    sample_id=str(sid)
                )
            )

    return probs


def validate_indexes_per_lane(
    df: pd.DataFrame,
    *,
    lane_col: str = "lane",
    sample_id_col: str = "sample_id",
    i7_col: str = "i7",
    i5_col: str = "i5",
) -> Tuple[List[Problem], Dict[int, int]]:
    """
    Index rules:
      - i7 must be present for all samples
      - dual-index samples (i5 present): (i7,i5) pair must be unique per lane
        (i7 duplicates are OK if i5 differs; i5 duplicates OK if i7 differs)
      - single-index samples (i5 missing) are allowed and may be mixed with dual-index
        * single-index i7 MUST NOT equal any other i7 in lane
        * for mixed lanes, determine mismatches based on i7 separation involving single-index samples
      - mismatch decision per lane (0/1):
        * default 1
        * tighten to 0 if min effective distance == 1 (WARN)
        * warn if min effective distance == 2
        * OK if >= 3
    """
    probs: List[Problem] = []
    lane_mm: Dict[int, int] = {}

    for lane, td in df.groupby(lane_col):
        lane = int(lane)
        lane_mm[lane] = DEFAULT_BARCODE_MISMATCHES

        # normalize sequences: missing -> None
        i7_list = [normalize_seq(x) for x in td[i7_col].tolist()]
        i5_list = [normalize_seq(x) for x in td[i5_col].tolist()]

        # i7 required for all samples
        if any(x is None for x in i7_list):
            bad = td.loc[[x is None for x in i7_list], sample_id_col].astype(str).tolist()
            probs.append(
                Problem(
                    "ERROR", "I7_MISSING",
                    f"Lane {lane}: missing i7 for samples: {', '.join(bad)}",
                    lane=lane
                )
            )
            continue

        # classify rows
        is_single = [x is None for x in i5_list]  # i5 missing => single-index
        single_idxs = [i for i, s in enumerate(is_single) if s]
        dual_idxs = [i for i, s in enumerate(is_single) if not s]
        has_single = len(single_idxs) > 0
        has_dual = len(dual_idxs) > 0


        # ---- Precompute lane-trimmed i7/i5 aligned to rows ----
        min_len_i7 = min(len(x) for x in i7_list if x is not None)
        i7_trim_by_row: List[str] = [x[:min_len_i7] for x in i7_list]  # all not None

        i5_nonmissing = [x for x in i5_list if x is not None]
        min_len_i5 = min(len(x) for x in i5_nonmissing) if i5_nonmissing else 0
        i5_trim_by_row: List[Optional[str]] = [
            None if x is None else x[:min_len_i5] for x in i5_list
        ]


        # ---- Dual-index pair uniqueness check (after trimming, only among dual rows) ----
        if has_dual:
            dual_pairs: List[str] = []
            dual_rows: List[int] = []
            for row_i in dual_idxs:
                dual_pairs.append(f"{i7_trim_by_row[row_i]}+{i5_trim_by_row[row_i]}")
                dual_rows.append(row_i)

            dup_pairs = pd.Series(dual_pairs).duplicated(keep=False)
            if dup_pairs.any():
                pair_to_rows = defaultdict(list)
                for local_i, flag in enumerate(dup_pairs.tolist()):
                    if flag:
                        pair_to_rows[dual_pairs[local_i]].append(dual_rows[local_i])

                for p, rows in sorted(pair_to_rows.items(), key=lambda kv: kv[0]):
                    sids = td.iloc[rows][sample_id_col].astype(str).tolist()
                    probs.append(
                        Problem(
                            "ERROR",
                            "INDEX_DUPLICATE_IN_LANE",
                            f"Lane {lane}: duplicate index pair (after trimming) {p}. Samples: {', '.join(sids)}",
                            lane=lane,
                        )
                    )


        # ---- Single-index uniqueness constraint on i7 (after trimming) ----
        if has_single:
            # single-index i7 cannot equal any other trimmed i7 in the lane
            i7_to_rows = defaultdict(list)
            for row_i, seq in enumerate(i7_trim_by_row):
                i7_to_rows[seq].append(row_i)

            for row_i in single_idxs:
                seq = i7_trim_by_row[row_i]
                if len(i7_to_rows[seq]) > 1:
                    rows = i7_to_rows[seq]
                    sids = td.iloc[rows][sample_id_col].astype(str).tolist()
                    probs.append(
                        Problem(
                            "ERROR",
                            "SINGLE_I7_DUPLICATE_IN_LANE",
                            f"Lane {lane}: single-index i7 (after trimming) {seq} is also used by other sample(s). "
                            f"Samples: {', '.join(sids)}",
                            lane=lane,
                        )
                    )


        # ---- Determine mismatch policy (0/1) per lane ----
        # Mixed lane: focus on i7 separation between SINGLE and DUAL sets
        if has_single and has_dual:
            single_trim = [i7_trim_by_row[i] for i in single_idxs] # single
            dual_trim = [i7_trim_by_row[i] for i in dual_idxs] # dual

            i7_min_focus = _min_hamming_between_sets(single_trim, dual_trim)
            # if there are singles but no duals, this block isn't used (has_dual required)
            if i7_min_focus is not None:
                if i7_min_focus == HAMMING_WARN_TIGHTEN:
                    lane_mm[lane] = 0
                    probs.append(
                        Problem(
                            "WARN",
                            "MIXED_LANE_I7_TOO_SIMILAR_HAMMING_1",
                            f"Lane {lane}: lane includes single-index sample(s); min i7 Hamming (single vs dual) is {i7_min_focus}. "
                            f"Recommend barcode mismatches = 0.",
                            lane=lane,
                        )
                    )
                elif i7_min_focus == HAMMING_WARN:
                    lane_mm[lane] = 0
                    probs.append(
                        Problem(
                            "WARN",
                            "MIXED_LANE_I7_SIMILAR_HAMMING_2",
                            f"Lane {lane}: lane includes single-index sample(s); min i7 Hamming (single vs dual) is {i7_min_focus}. "
                            f"Recommend barcode mismatches = 0.",
                            lane=lane,
                        )
                    )
                elif i7_min_focus < HAMMING_OK_MIN:
                    lane_mm[lane] = 0
                    probs.append(
                        Problem(
                            "WARN",
                            "MIXED_LANE_I7_TOO_SIMILAR",
                            f"Lane {lane}: lane includes single-index sample(s); min i7 Hamming (single vs dual) is {i7_min_focus} (<{HAMMING_OK_MIN}). "
                            f"Recommend barcode mismatches = 0.",
                            lane=lane,
                        )
                    )
            continue

        # Dual-only lane: decide mismatches based on (i7+i5) effective distance
        if has_dual and not has_single:
            i7_dual_trim = [i7_trim_by_row[i] for i in dual_idxs]
            i5_dual_trim = [i5_trim_by_row[i] for i in dual_idxs]  # not None in dual-only

            d_eff_min = _min_effective_pair_distance(i7_dual_trim, i5_dual_trim)

            if d_eff_min is not None:
                if d_eff_min == HAMMING_WARN_TIGHTEN:
                    lane_mm[lane] = 0
                    probs.append(
                        Problem(
                            "WARN",
                            "DUAL_LANE_PAIR_TOO_SIMILAR_HAMMING_1",
                            f"Lane {lane}: dual-index samples; min effective pair distance max(d_i7,d_i5) is {d_eff_min}. "
                            f"Recommend barcode mismatches = 0.",
                            lane=lane,
                        )
                    )
                elif d_eff_min == HAMMING_WARN:
                    lane_mm[lane] = 0
                    probs.append(
                        Problem(
                            "WARN",
                            "DUAL_LANE_PAIR_SIMILAR_HAMMING_2",
                            f"Lane {lane}: dual-index samples; min effective pair distance max(d_i7,d_i5) is {d_eff_min}. "
                            f"Recommend barcode mismatches = 0.",
                            lane=lane,
                        )
                    )
            continue

        # Single-only lane: base decision on i7 only (trimmed)
        if has_single and not has_dual:
            i7_min = _min_pairwise_hamming(_trim_to_lane_min(i7_trim_by_row))
            if i7_min is not None:
                if i7_min == HAMMING_WARN_TIGHTEN:
                    lane_mm[lane] = 0
                    probs.append(
                        Problem(
                            "WARN",
                            "SINGLE_LANE_I7_TOO_SIMILAR_HAMMING_1",
                            f"Lane {lane}: single-index samples; min i7 Hamming after trimming is {i7_min}. "
                            f"Recommend barcode mismatches = 0.",
                            lane=lane,
                        )
                    )
                elif i7_min == HAMMING_WARN:
                    lane_mm[lane] = 0
                    probs.append(
                        Problem(
                            "WARN",
                            "SINGLE_LANE_I7_SIMILAR_HAMMING_2",
                            f"Lane {lane}: single-index samples; min i7 Hamming after trimming is {i7_min}. "
                            f"Recommend barcode mismatches = 0.",
                            lane=lane,
                        )
                    )

    return probs, lane_mm


def validate_all(df: pd.DataFrame) -> ValidationSummary:
    """
    Assumes df is already normalized to canonical columns:
    lane, sample_id, project_id, i7, i5 (+ optional extras).
    """
    # initialize a list storing Problems
    probs: List[Problem] = []
    # validate sample ids
    probs.extend(validate_sample_ids(df, lane_col=COL_LANE, sample_id_col=COL_SAMPLE_ID, project_id_col=COL_PROJECT_ID))
    # validate indexes per lane
    p2, lane_mm = validate_indexes_per_lane(df, lane_col=COL_LANE, sample_id_col=COL_SAMPLE_ID, i7_col=COL_I7, i5_col=COL_I5)
    probs.extend(p2)

    return ValidationSummary(problems=probs, lane_barcode_mismatches=lane_mm)

