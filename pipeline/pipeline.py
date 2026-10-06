"""One function that takes a contract and an invoice and returns a verdict.

run_eval.py calls it and so does the Streamlit app, which is why it returns
the full picture rather than only the fields the eval scores.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .decide import DEFAULT_THRESHOLD, decide
from .extract import MODEL, extract
from .grounding import CONTRACT_CHECKED, INVOICE_CHECKED, grounding_rate
from .routing import build_content_blocks
from .rules import Ledger
from .schemas import ContractFields, InvoiceFields


def case_label(contract_pdf: str) -> str:
    return Path(contract_pdf).name.replace("_contract.pdf", "")


def run_pair(
    contract_pdf: str,
    invoice_pdf: str,
    model: str = MODEL,
    threshold: float = DEFAULT_THRESHOLD,
    ledger: Ledger | None = None,
    escalate_unverifiable: bool = True,
) -> dict[str, Any]:
    c_blocks, c_path, c_text = build_content_blocks(contract_pdf)
    i_blocks, i_path, i_text = build_content_blocks(invoice_pdf)

    contract, c_cost = extract(c_blocks, ContractFields, "contract", model=model)
    invoice, i_cost = extract(i_blocks, InvoiceFields, "invoice", model=model)

    c_rate, c_ungrounded = grounding_rate(contract, CONTRACT_CHECKED, c_text)
    i_rate, i_ungrounded = grounding_rate(invoice, INVOICE_CHECKED, i_text)

    label = case_label(contract_pdf)
    verdict = decide(contract, invoice, c_rate, i_rate, threshold=threshold,
                     ledger=ledger, label=label,
                     escalate_unverifiable=escalate_unverifiable)

    return {
        "contract": contract,
        "invoice": invoice,
        "cost_usd": c_cost + i_cost,
        "path": f"{c_path}/{i_path}",
        "ungrounded_fields": [f"contract.{f}" for f in c_ungrounded]
                             + [f"invoice.{f}" for f in i_ungrounded],
        **verdict,
    }


def to_eval_fields(result: dict[str, Any]) -> dict[str, Any]:
    """Flatten into the fields the golden set scores.

    An escalation counts as not-an-exception for the is_exception metric,
    which is the honest reading: the system did not claim the invoice was
    wrong, it declined to judge. The escalation rate is reported separately
    rather than folded into precision and recall.
    """
    contract, invoice = result["contract"], result["invoice"]
    return {
        "creator_name": contract.creator_name,
        "contract_rate_usd": contract.rate_usd,
        "invoice_total_usd": invoice.total_usd,
        "deliverable_count_contracted": sum(d.count for d in contract.deliverables) or None,
        "deliverable_count_invoiced": sum(li.quantity for li in invoice.line_items) or None,
        "is_exception": result["verdict"] == "flag",
        "_verdict": result["verdict"],
        "_reason": result.get("reason"),
        "_path": result["path"],
        "_grounding_rate": result["grounding_rate"],
    }
