#!/usr/bin/env python3
"""Run the golden set against the full pipeline and print the README table.

    python run_eval.py --variant extraction-only-v2 --extraction-only
    python run_eval.py --variant full-pipeline --compare-to extraction-only-v2
    python run_eval.py --variant threshold-0.85 --threshold 0.85

Always smoke test with --limit 3 first. Sixty cases is 120 model calls.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from evalkit import compare, latest_run, load_cases, run, summarize, to_markdown
from pipeline.decide import DEFAULT_THRESHOLD
from pipeline.pipeline import run_pair, to_eval_fields
from pipeline.rules import Ledger

RUN_NAME = "reconciliation"
GOLDEN = "evals/golden.jsonl"
FIELDS = ["creator_name", "contract_rate_usd", "invoice_total_usd",
          "deliverable_count_contracted", "deliverable_count_invoiced", "is_exception"]
MONEY_FIELDS = ["contract_rate_usd", "invoice_total_usd"]
FLAG_FIELD = "is_exception"


def make_predict(model: str, threshold: float, ledger: Ledger, escalate_unverifiable: bool = True,
                 extraction_only: bool = False):
    """The ledger is shared across every case in one run, which is what makes
    duplicate detection possible. It is the only rule that needs state.

    extraction_only scores the extracted fields with is_exception hardcoded
    False, the week 2 baseline, so the before-and-after isolates what the
    reconciliation layer added on the same corpus."""
    def predict(case_input):
        result = run_pair(case_input["contract_pdf"], case_input["invoice_pdf"],
                          model=model, threshold=threshold, ledger=ledger,
                          escalate_unverifiable=escalate_unverifiable)
        fields = to_eval_fields(result)
        if extraction_only:
            fields.update(is_exception=False, _verdict=None, _reason=None)
        return fields, result["cost_usd"]
    return predict


def verdict_breakdown(record) -> str:
    counts = Counter((r.get("predicted") or {}).get("_verdict", "error") for r in record["rows"])
    total = sum(counts.values()) or 1
    lines = ["| Verdict | Cases | Share |", "| --- | --- | --- |"]
    for name in ("approve", "flag", "escalate", "error"):
        if counts.get(name):
            lines.append(f"| {name} | {counts[name]} | {counts[name] / total:.0%} |")
    reasons = Counter((r.get("predicted") or {}).get("_reason")
                      for r in record["rows"]
                      if (r.get("predicted") or {}).get("_verdict") == "escalate")
    if reasons:
        lines.append("")
        lines.append("Escalation reasons: " + ", ".join(f"{k} ({v})" for k, v in reasons.items()))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the golden set.")
    parser.add_argument("--variant", default="full-pipeline")
    parser.add_argument("--cases", default=GOLDEN)
    parser.add_argument("--model", default=os.environ.get("EXTRACTION_MODEL", "claude-sonnet-5"))
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="grounding rate below which a case escalates instead of being judged")
    parser.add_argument("--judge-unverifiable", action="store_true",
                        help="judge vision-path documents instead of escalating them")
    parser.add_argument("--extraction-only", action="store_true",
                        help="score extraction alone, no reconciliation verdict")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="all")
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

    print(f"Running {len(cases)} cases, model={args.model}, "
          f"threshold={args.threshold}, variant='{args.variant}'\n")

    record = run(cases, make_predict(args.model, args.threshold, Ledger(),
                                     escalate_unverifiable=not args.judge_unverifiable,
                                     extraction_only=args.extraction_only),
                 run_name=RUN_NAME, variant=args.variant,
                 notes=args.notes or f"model={args.model} threshold={args.threshold} split={args.split}")
    current = summarize(record, FIELDS, MONEY_FIELDS, FLAG_FIELD)

    print()
    print(to_markdown(current))
    if not args.extraction_only:
        print()
        print(verdict_breakdown(record))

    if args.compare_to:
        prior = latest_run(RUN_NAME, args.compare_to)
        if prior is None:
            print(f"\nNo prior run found for variant '{args.compare_to}'.", file=sys.stderr)
        else:
            print()
            print(compare(summarize(prior, FIELDS, MONEY_FIELDS, FLAG_FIELD), current))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
