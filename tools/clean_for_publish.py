#!/usr/bin/env python3
"""One-time cleanup before the repo goes public.

Strips comments that were written for the author rather than for a reader:
references to interviews, portfolios, and the week-by-week build order. The
design rationale stays, because that is what makes the code readable. Only
the career framing around it goes.

    python tools/clean_for_publish.py --dry-run
    python tools/clean_for_publish.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

REPLACEMENTS: list[tuple[str, str, str]] = [
    ("pipeline/extract.py",
     "# USD per million tokens. Verified September 2026 against public pricing.\n"
     "# Put the date in this comment and re-check it before you quote a cost\n"
     "# number in an interview.",
     "# USD per million tokens. Verified September 2026 against public pricing.\n"
     "# Re-check these before relying on any cost figure."),

    ("pipeline/routing.py",
     "This is the piece that gets the most attention in an interview, because it\n"
     "is a cost decision rather than a capability decision.",
     "This is a cost decision rather than a capability decision."),

    ("pipeline/routing.py",
     "# artifacts a scanner sometimes leaves behind. It is a heuristic, not a\n"
     "# truth, and it is worth saying so out loud.",
     "# artifacts a scanner sometimes leaves behind. It is a heuristic, not a\n"
     "# truth, and a sparse digital PDF would route to vision unnecessarily."),

    ("pipeline/rules.py",
     "    genuinely different names separate. Document that. An unjustified magic\n"
     "    number is a question you will be asked.",
     "    genuinely different names separate. It is empirical, not principled."),

    ("pipeline/grounding.py",
     "The obvious way to get confidence is to ask the model for it. Do not. Self\n"
     "reported confidence from a language model is poorly calibrated, and an\n"
     "interviewer who knows that will press on it.",
     "The obvious way to get confidence is to ask the model for it. Self reported\n"
     "confidence from a language model is poorly calibrated, so this does not."),

    ("pipeline/grounding.py",
     "    be checked, which is the vision path. Week 3's escalation gate treats\n"
     "    None as \"cannot vouch for this\" rather than as zero.",
     "    be checked, which is the vision path. The escalation gate treats None as\n"
     "    \"cannot vouch for this\" rather than as zero."),

    ("tests/test_rules.py",
     "real eval run is an extraction failure rather than a logic failure. That\n"
     "separation is worth having, and it is worth saying out loud in an interview:\n"
     "you can point at one test and say the decision layer is verified\n"
     "independently of the model.",
     "real eval run is an extraction failure rather than a logic failure. The\n"
     "decision layer is verified independently of the model."),

    ("tests/test_pipeline.py",
     '"""Week 2 tests. None of these call the API',
     '"""Pipeline tests. None of these call the API'),

    ("tests/test_pipeline.py",
     'means "checked and absent". The week 3 gate treats them differently."""',
     'means "checked and absent". The escalation gate treats them differently."""'),

    ("evalkit/metrics.py",
     "Every number an interviewer asks about should be traceable to about ten\n"
     "lines of code they could read over your shoulder.",
     "Every number reported here should be traceable to about ten lines of code."),

    ("evalkit/__init__.py",
     '"""Shared evaluation harness. Copy this package into each project repo unchanged."""',
     '"""Shared evaluation harness: golden sets, runs, metrics, and reports."""'),

    ("app.py",
     "One page, laid out in the order a demo runs. The example-case dropdown is\n"
     "the most important control here: a reviewer who opens this link with no\n"
     "files to upload must be able to see the system work in one click. Most\n"
     "portfolio demos fail exactly there.",
     "One page, laid out in the order a demo runs. The example-case dropdown lets\n"
     "anyone see the system work without supplying their own documents."),

    ("app.py",
     "# One ledger per browser session, so a duplicate invoice number is caught\n"
     "# across the cases a reviewer runs in a sitting.",
     "# One ledger per browser session, so a duplicate invoice number is caught\n"
     "# across the cases run in a single sitting."),

    ("tools/sweep_threshold.py",
     '    print("Pick a threshold and justify it in one sentence tied to the customer, "\n'
     '          "for example: at 0.75 roughly one invoice in eight reaches a human, which "\n'
     '          "is a workload marketing ops can absorb.")\n',
     ""),
]

STALE_FILES = ["evals/golden.example.jsonl"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    applied = skipped = 0
    for rel, old, new in REPLACEMENTS:
        path = Path(rel)
        if not path.exists():
            print(f"  skip   {rel} (not found)")
            skipped += 1
            continue
        text = path.read_text(encoding="utf-8")
        if old not in text:
            print(f"  skip   {rel} (already clean or text differs)")
            skipped += 1
            continue
        if not args.dry_run:
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
        print(f"  {'would fix' if args.dry_run else 'fixed'}  {rel}")
        applied += 1

    for rel in STALE_FILES:
        path = Path(rel)
        if path.exists():
            if not args.dry_run:
                path.unlink()
            print(f"  {'would remove' if args.dry_run else 'removed'}  {rel}")
            applied += 1

    print(f"\n{applied} changes, {skipped} skipped.")
    print("Now grep for anything left: "
          "grep -rniE 'interview|portfolio|week [0-9]|resume' --include='*.py' .")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
