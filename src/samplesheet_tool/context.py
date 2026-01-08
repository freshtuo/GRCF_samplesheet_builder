# context.py
# Class RunContext to wrap things up
# 

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import pandas as pd

from samplesheet_tool.io_normalize import check_required_columns, normalize_minimal, expand_lanes
from samplesheet_tool.indexes import (
    load_single_index_table, build_single_lookup,
    load_paired_index_table, build_pair_lookup,
    merge_single_lookups, merge_pair_lookups,
)
from samplesheet_tool.resolve import resolve_indexes
from samplesheet_tool.validate import validate_all
from samplesheet_tool.utils import Problem
from samplesheet_tool.config import COL_LANE, COL_PROJECT_ID, COL_BARCODE_MISMATCHES


def _parse_i7i5_map(spec: str) -> Tuple[str, str, str]:
    """
    Parse "path:ID_COL:SEQ_COL"
    Example: "/path/truseq_i7.csv:Name:Sequence"
    """
    parts = spec.split(":")
    if len(parts) != 3:
        raise ValueError(
            f"Invalid map spec '{spec}'. Expected format: path:ID_COL:SEQ_COL"
        )
    path, id_col, seq_col = (p.strip() for p in parts)
    if not path or not id_col or not seq_col:
        raise ValueError(f"Invalid map spec '{spec}': empty field.")
    return path, id_col, seq_col


def _parse_pair_map(spec: str) -> Tuple[str, str, str, str]:
    """
    Parse "path:PAIR_ID_COL:I7_COL:I5_COL"
    Example: "/path/Dual_Index_Kit_NN_Set_A.csv:Index_ID:Index_I7:Index_I5"
    """
    parts = spec.split(":")
    if len(parts) != 4:
        raise ValueError(
            f"Invalid pair-map spec '{spec}'. Expected format: path:PAIR_ID_COL:I7_COL:I5_COL"
        )
    path, pair_id_col, i7_col, i5_col = (p.strip() for p in parts)
    if not path or not pair_id_col or not i7_col or not i5_col:
        raise ValueError(f"Invalid pair-map spec '{spec}': empty field.")
    return path, pair_id_col, i7_col, i5_col


@dataclass
class RunContext:
    """
    RunContext orchestrates the pipeline while holding state that a future UI
    can keep in memory. This keeps __main__.py minimal.
    """

    input_path: str
    output_path: str

    # Repeatable table specs (no guessing; user must provide column names)
    # --i7-map path:ID_COL:SEQ_COL
    # --i5-map path:ID_COL:SEQ_COL
    # --pair-map path:PAIR_ID_COL:I7_COL:I5_COL
    i7_maps: List[str]
    i5_maps: List[str]
    pair_maps: List[str] = field(default_factory=list)

    dry_run: bool = False

    # State populated during the run
    df_input: Optional[pd.DataFrame] = None
    df_normalized: Optional[pd.DataFrame] = None
    df_resolved: Optional[pd.DataFrame] = None

    # Mismatches allowed (per lane)
    lane_barcode_mismatches: dict[int, int] = field(default_factory=dict)

    # Issues if any
    problems: List[Problem] = field(default_factory=list)

    def read_input(self) -> pd.DataFrame:
        path = Path(self.input_path)
        if not path.exists():
            raise FileNotFoundError(str(path))

        suf = path.suffix.lower()
        if suf in [".xlsx", ".xls"]:
            return pd.read_excel(path)

        if suf in [".csv", ".tsv"]:
            sep = "\t" if suf == ".tsv" else ","
            return pd.read_csv(path, sep=sep)

        raise ValueError(f"Unsupported input file type: {suf}")

    def load_index_lookups(
        self,
    ) -> Tuple[Dict[str, str], Dict[str, str], Optional[Dict[str, Tuple[str, str]]]]:
        """
        Load N i7 tables + N i5 tables + optional paired tables and merge them.
        Collision rule (strict):
          - If an ID appears with different sequence(s), raise ValueError.
          - If identical mapping repeats, OK.
        """
        # i7
        i7_lookups: List[Dict[str, str]] = []
        for spec in self.i7_maps:
            path, id_col, seq_col = _parse_i7i5_map(spec)
            df = load_single_index_table(path, id_col=id_col, seq_col=seq_col)
            i7_lookups.append(build_single_lookup(df))
        i7_lookup = merge_single_lookups(i7_lookups)

        # i5
        i5_lookups: List[Dict[str, str]] = []
        for spec in self.i5_maps:
            path, id_col, seq_col = _parse_i7i5_map(spec)
            df = load_single_index_table(path, id_col=id_col, seq_col=seq_col)
            i5_lookups.append(build_single_lookup(df))
        i5_lookup = merge_single_lookups(i5_lookups)

        # paired (optional)
        pair_lookup: Optional[Dict[str, Tuple[str, str]]] = None
        if self.pair_maps:
            pair_lookups: List[Dict[str, Tuple[str, str]]] = []
            for spec in self.pair_maps:
                path, pair_id_col, i7_col, i5_col = _parse_pair_map(spec)
                df = load_paired_index_table(
                    path,
                    pair_id_col=pair_id_col,
                    i7_col=i7_col,
                    i5_col=i5_col,
                )
                pair_lookups.append(build_pair_lookup(df))
            pair_lookup = merge_pair_lookups(pair_lookups)

        return i7_lookup, i5_lookup, pair_lookup

    def write_output(self) -> None:
        """
        For now, write the resolved table as CSV (placeholder).
        Later replace with BaseSpace SampleSheet writer.
        """
        if self.df_resolved is None:
            raise RuntimeError("No resolved DataFrame available to write.")

        # order samples by lane + project_id
        df_sorted = self.df_resolved.sort_values(by=[COL_LANE, COL_PROJECT_ID], ascending=[True, True])

        # write to file
        out = Path(self.output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        df_sorted.to_csv(out, index=False)

    def run(self) -> int:
        """
        Returns exit code:
          0 = success
          2 = validation failed (errors)
        """
        # 1) read input
        df_raw = self.read_input()
        self.df_input = df_raw

        # 2) strict required-column check + expand lanes (1,2,4 to multiple rows) + minimal normalization (NO renaming)
        check_required_columns(df_raw)
        df_expanded = expand_lanes(df_raw)
        df_norm = normalize_minimal(df_expanded)
        self.df_normalized = df_norm

        # 3) load and merge index lookups (may raise ValueError on collisions)
        i7_lookup, i5_lookup, pair_lookup = self.load_index_lookups()

        # 4) resolve index sequences from IDs when sequences are missing
        res = resolve_indexes(
            df_norm,
            i7_lookup=i7_lookup,
            i5_lookup=i5_lookup,
            pair_lookup=pair_lookup,
        )
        self.df_resolved = res.df
        self.problems.extend(res.problems)

        # 5) validate sample IDs + per-lane index constraints (mismatches)
        vs = validate_all(self.df_resolved)
        self.problems.extend(vs.problems)
        self.lane_barcode_mismatches = vs.lane_barcode_mismatches

        # 6) decide outcome
        has_errors = any(p.level == "ERROR" for p in self.problems)
        if has_errors:
            return 2

        # 7) write output (if not dry-run)
        if not self.dry_run:
            self.write_output()

        return 0

