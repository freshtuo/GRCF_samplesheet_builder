# __main__.py
# CLI entry point
#

from __future__ import annotations

import argparse
import sys

from samplesheet_tool.context import RunContext


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="samplesheet-tool",
        description="Illumina SampleSheet validation and generation tool (NovaSeq X Plus)"
    )

    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Input sample CSV/XLSX file(s)"
    )

    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output BaseSpace SampleSheet CSV"
    )

    parser.add_argument(
        "--i7-map", 
        action="append", required=True, 
        help="Repeatable: path:ID_COL:SEQ_COL for i7")
    parser.add_argument(
        "--i5-map", 
        action="append", required=True,
        help="Repeatable: path:ID_COL:SEQ_COL for i5")
    parser.add_argument(
        "--pair-map", 
        action="append", default=[],
        help="Repeatable: path:PAIR_ID_COL:I7_COL:I5_COL for paired indexes")

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only; do not write SampleSheet"
    )

    return parser


def print_problems(problems):
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    problems = sorted(problems, key=lambda p: (order.get(p.level, 9), p.lane or -1, p.code, p.sample_id or ""))

    for p in problems:
        lane = f"lane={p.lane}" if p.lane is not None else "lane=?"
        sid = f"sample_id={p.sample_id}" if p.sample_id else ""
        print(f"[{p.level}] {p.code} {lane} {sid} - {p.message}".strip())


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    ctx = RunContext(
        input_path=args.input,
        output_path=args.output,
        i7_maps=args.i7_map,
        i5_maps=args.i5_map,
        pair_maps=args.pair_map,
        dry_run=args.dry_run,
    )

    code = ctx.run()
    print_problems(ctx.problems)

    if code == 0:
        if args.dry_run:
            print("\nDry run: validation passed.")
        else:
            print(f"\nWrote: {args.output}")
    else:
        print("\nValidation failed (errors found).")

    if ctx.lane_barcode_mismatches:
        print("\nLane barcode mismatch recommendations:")
        for lane in sorted(ctx.lane_barcode_mismatches):
            mm = ctx.lane_barcode_mismatches[lane]
            print(f"  Lane {lane}: barcode_mismatches = {mm}")

    return code


if __name__ == "__main__":
    sys.exit(main())

