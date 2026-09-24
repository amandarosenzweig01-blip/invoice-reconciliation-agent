#!/usr/bin/env python3
"""Run the golden set against the pipeline and print the README table.

    python run_eval.py --variant extraction-only --limit 3
    python run_eval.py --variant extraction-only
    python run_eval.py --variant haiku --compare-to extraction-only

Always smoke test with --limit 3 before a full run. Sixty cases is 120 model
calls, and discovering a typo on call 118 is an expensive way to find it.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from evalkit import compare, latest_run, load_cases, run, summarize, to_markdown
from pipeline.pipeline import run_pair, to_eval_fields

RUN_NAME = "reconciliation"
GOLDEN = "evals/golden.jsonl"
FIELDS = ["creator_name", "contract_rate_usd", "invoice_total_usd",
          "deliverable_count_contracted", "deliverable_count_invoiced", "is_exception"]
MONEY_FIELDS = ["contract_rate_usd", "invoice_total_usd"]
FLAG_FIELD = "is_exception"


def make_predict(model: str):
    def predict(case_input):
        result = run_pair(case_input["contract_pdf"], case_input["invoice_pdf"], model=model)
        return to_eval_fields(result), result["cost_usd"]
    return predict


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the golden set.")
    parser.add_argument("--variant", default="extraction-only")
    parser.add_argument("--cases", default=GOLDEN)
    parser.add_argument("--model", default=os.environ.get("EXTRACTION_MODEL", "claude-sonnet-5"))
    parser.add_argument("--split", choices=["dev", "test", "all"], default="all",
                        help="dev is yours to inspect; test runs only at variant boundaries")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--notes", default="")
    parser.add_argument("--compare-to", default=None)
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Check your .env file.", file=sys.stderr)
        return 1
    if not Path(args.cases).exists():
        print(f"No golden set at {args.cases}. Run tools/specs_to_golden.py first.", file=sys.stderr)
        return 1

    cases = load_cases(args.cases)
    if args.split != "all":
        cases = [c for c in cases if args.split in c.tags]
    if args.limit:
        cases = cases[: args.limit]

    print(f"Running {len(cases)} cases, model={args.model}, variant='{args.variant}'\n")
    record = run(cases, make_predict(args.model), run_name=RUN_NAME,
                 variant=args.variant, notes=args.notes or f"model={args.model} split={args.split}")
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
