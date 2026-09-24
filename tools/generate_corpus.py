#!/usr/bin/env python3
"""Generate the corpus: 60 specs and 120 PDFs.

    python tools/generate_corpus.py
    python tools/generate_corpus.py --limit 4     # quick look before committing
    python tools/generate_corpus.py --seed 7      # a different draw

Everything it writes is deterministic given the seed, so anyone who clones
the repo reproduces your exact corpus. That is worth stating in the README.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.render import html_to_pdf, render_html, scannify, text_layer_length
from tools.scenarios import build_corpus, summarize

ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = ROOT / "data" / "specs"
CONTRACT_DIR = ROOT / "data" / "contracts"
INVOICE_DIR = ROOT / "data" / "invoices"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260924)
    ap.add_argument("--limit", type=int, default=None, help="render only the first N cases")
    ap.add_argument("--specs-only", action="store_true", help="skip PDF rendering")
    args = ap.parse_args()

    specs = build_corpus(seed=args.seed)
    print(summarize(specs))
    print()

    for d in (SPEC_DIR, CONTRACT_DIR, INVOICE_DIR):
        d.mkdir(parents=True, exist_ok=True)

    targets = specs[: args.limit] if args.limit is not None else specs
    problems: list[str] = []

    for i, spec in enumerate(targets, start=1):
        cid = spec["case_id"]
        (SPEC_DIR / f"{cid}.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        if args.specs_only:
            continue

        c_pdf = CONTRACT_DIR / f"{cid}_contract.pdf"
        i_pdf = INVOICE_DIR / f"{cid}_invoice.pdf"
        html_to_pdf(render_html(spec["render"]["contract_layout"], spec), c_pdf)
        html_to_pdf(render_html(spec["render"]["invoice_layout"], spec), i_pdf)

        if spec["render"]["scanned"]:
            # Scan the invoice only. Mixed-path pairs are realistic, since a
            # brand's own contract is a clean PDF while the invoice arrives
            # as whatever the creator photographed.
            scannify(i_pdf, seed=args.seed + i)
            remaining = text_layer_length(i_pdf)
            if remaining > 50:
                problems.append(f"{cid}: scanned invoice still has {remaining} chars of text")

        print(f"  {i:>3}/{len(targets)}  {cid}  {spec['defect']:<22}"
              f"{'scanned' if spec['render']['scanned'] else ''}")

    print(f"\nSpecs   -> {SPEC_DIR}")
    if not args.specs_only:
        print(f"PDFs    -> {CONTRACT_DIR} and {INVOICE_DIR}")

    if problems:
        print("\nCheck these, the scan did not destroy the text layer:")
        for p in problems:
            print(f"  {p}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
