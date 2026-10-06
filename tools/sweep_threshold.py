#!/usr/bin/env python3
"""Sweep the escalation threshold and print the tradeoff table.

    python tools/sweep_threshold.py
    python tools/sweep_threshold.py --thresholds 0.5 0.75 0.9 --split test

The first pass pays for extraction. Every pass after that reads the cache,
so the sweep is effectively free. That is the whole reason the cache exists.

The table this produces is the best single artifact in the project. It turns
a hyperparameter into a staffing question, which is the translation the job
is actually about.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from evalkit import load_cases, run, summarize
from pipeline.rules import Ledger
from run_eval import FIELDS, FLAG_FIELD, MONEY_FIELDS, RUN_NAME, make_predict

DEFAULTS = [0.50, 0.65, 0.75, 0.85, 0.95]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thresholds", type=float, nargs="+", default=DEFAULTS)
    ap.add_argument("--cases", default="evals/golden.jsonl")
    ap.add_argument("--model", default=os.environ.get("EXTRACTION_MODEL", "claude-sonnet-5"))
    ap.add_argument("--split", choices=["dev", "test", "all"], default="all")
    ap.add_argument("--judge-unverifiable", action="store_true",
                    help="judge vision-path documents instead of escalating them")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        return 1

    cases = load_cases(args.cases)
    if args.split != "all":
        cases = [c for c in cases if args.split in c.tags]

    rows = []
    for threshold in args.thresholds:
        print(f"threshold {threshold:.2f} ...", flush=True)
        record = run(cases,
                     make_predict(args.model, threshold, Ledger(),
                                  escalate_unverifiable=not args.judge_unverifiable),
                     run_name=RUN_NAME, variant=f"threshold-{threshold:.2f}",
                     notes=f"sweep, split={args.split}")
        summary = summarize(record, FIELDS, MONEY_FIELDS, FLAG_FIELD)
        verdicts = Counter((r.get("predicted") or {}).get("_verdict") for r in record["rows"])
        total = len(record["rows"])
        flag = summary.get("flag", {})
        rows.append({
            "threshold": threshold,
            "recall": flag.get("recall", float("nan")),
            "precision": flag.get("precision", float("nan")),
            "escalated": verdicts.get("escalate", 0) / total,
            "approved": verdicts.get("approve", 0) / total,
            "flagged": verdicts.get("flag", 0) / total,
        })

    print()
    print("| Threshold | Exception recall | Exception precision | Escalation rate | Auto-approved |")
    print("| --- | --- | --- | --- | --- |")
    for r in rows:
        print(f"| {r['threshold']:.2f} | {r['recall']:.1%} | {r['precision']:.1%} "
              f"| {r['escalated']:.1%} | {r['approved']:.1%} |")
    print()
    print(f"Run on {len(cases)} cases, split={args.split}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
