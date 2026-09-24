#!/usr/bin/env python3
"""Turn data/specs/*.json into evals/golden.jsonl.

    python tools/specs_to_golden.py

The expected dict is deliberately flat. The harness scores field by field,
so anything nested would be scored as a single all-or-nothing blob and you
would lose the ability to see which field is hard. Flatten aggressively.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = ROOT / "data" / "specs"
GOLDEN = ROOT / "evals" / "golden.jsonl"


def to_case(spec: dict) -> dict:
    contract, invoice, truth = spec["contract"], spec["invoice"], spec["truth"]
    return {
        "id": spec["case_id"],
        "input": {
            "contract_pdf": f"data/contracts/{spec['case_id']}_contract.pdf",
            "invoice_pdf": f"data/invoices/{spec['case_id']}_invoice.pdf",
        },
        "expected": {
            "creator_name": contract["creator_name"],
            "contract_rate_usd": contract["rate_usd"],
            "invoice_total_usd": invoice["total_usd"],
            "deliverable_count_contracted": contract["deliverable_count"],
            "deliverable_count_invoiced": sum(li["quantity"] for li in invoice["line_items"]),
            "is_exception": truth["is_exception"],
            "exception_type": truth["exception_type"],
        },
        "tags": [
            spec["defect"],
            spec["split"],
            "scanned" if spec["render"]["scanned"] else "digital",
        ],
    }


def main() -> int:
    paths = sorted(SPEC_DIR.glob("case_*.json"))
    if not paths:
        print(f"No specs in {SPEC_DIR}. Run generate_corpus.py first.", file=sys.stderr)
        return 1

    cases = [to_case(json.loads(p.read_text(encoding="utf-8"))) for p in paths]
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text("\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8")

    missing = [c["id"] for c in cases
               for key in ("contract_pdf", "invoice_pdf")
               if not (ROOT / c["input"][key]).exists()]
    tags = Counter(t for c in cases for t in c["tags"])

    print(f"Wrote {len(cases)} cases to {GOLDEN}\n")
    print(f"{'exceptions':<14}{sum(1 for c in cases if c['expected']['is_exception']):>4}")
    print(f"{'approvals':<14}{sum(1 for c in cases if not c['expected']['is_exception']):>4}")
    print(f"{'dev':<14}{tags['dev']:>4}")
    print(f"{'test':<14}{tags['test']:>4}")
    print(f"{'scanned':<14}{tags['scanned']:>4}")
    if missing:
        print(f"\nMissing PDFs for {len(set(missing))} cases. Run generate_corpus.py.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
