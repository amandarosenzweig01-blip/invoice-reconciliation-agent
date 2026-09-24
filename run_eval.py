#!/usr/bin/env python3
"""Run the golden set against your pipeline and print the README table.

Usage:
    python run_eval.py --variant baseline
    python run_eval.py --variant reranked --compare-to baseline

Wire your pipeline in by editing `predict` and the FIELDS constants below.
Nothing else in this file should need to change across projects.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evalkit import compare, latest_run, load_cases, run, summarize, to_markdown

# --- configure per project -------------------------------------------------

RUN_NAME = "extraction"           # short slug used in result filenames
GOLDEN = "evals/golden.jsonl"
FIELDS = ["vendor", "total", "deliverable_count", "is_exception"]
MONEY_FIELDS = ["total"]
FLAG_FIELD = "is_exception"       # set to None if the project has no flag


def predict(case_input):
    """Replace this with a call into your pipeline.

    Return a dict of predicted fields, or (dict, cost_usd) if you are
    tracking spend. Do not catch exceptions here. The runner records them
    as hard errors, and a hard error rate is a number worth reporting.
    """
    raise NotImplementedError("wire predict() into your pipeline")


# --- generally leave alone -------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the golden set.")
    parser.add_argument("--variant", default="baseline",
                        help="what changed in this run, e.g. baseline, reranked, threshold-0.8")
    parser.add_argument("--cases", default=GOLDEN)
    parser.add_argument("--notes", default="")
    parser.add_argument("--compare-to", default=None,
                        help="variant name to diff this run against")
    parser.add_argument("--limit", type=int, default=None,
                        help="run only the first N cases, for smoke tests")
    args = parser.parse_args()

    if not Path(args.cases).exists():
        print(f"No golden set at {args.cases}. Label some data first.", file=sys.stderr)
        return 1

    cases = load_cases(args.cases)
    if args.limit:
        cases = cases[: args.limit]
    print(f"Running {len(cases)} cases as variant '{args.variant}'\n")

    record = run(cases, predict, run_name=RUN_NAME, variant=args.variant, notes=args.notes)
    current = summarize(record, FIELDS, MONEY_FIELDS, FLAG_FIELD)

    print()
    print(to_markdown(current))

    if args.compare_to:
        prior = latest_run(RUN_NAME, args.compare_to)
        if prior is None:
            print(f"No prior run found for variant '{args.compare_to}'.", file=sys.stderr)
        else:
            print()
            print(compare(summarize(prior, FIELDS, MONEY_FIELDS, FLAG_FIELD), current))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
