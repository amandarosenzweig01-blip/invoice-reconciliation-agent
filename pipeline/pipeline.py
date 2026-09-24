"""One function that takes a contract and an invoice and returns everything
downstream needs. run_eval.py calls it, and in week 3 the Streamlit app will
call the same function, which is why it returns a rich dict rather than just
the eval fields.
"""

from __future__ import annotations

from typing import Any

from .extract import MODEL, extract
from .grounding import CONTRACT_CHECKED, INVOICE_CHECKED, grounding_rate
from .routing import build_content_blocks
from .schemas import ContractFields, InvoiceFields


def run_pair(contract_pdf: str, invoice_pdf: str, model: str = MODEL) -> dict[str, Any]:
    c_blocks, c_path, c_text = build_content_blocks(contract_pdf)
    i_blocks, i_path, i_text = build_content_blocks(invoice_pdf)

    contract, c_cost = extract(c_blocks, ContractFields, "contract", model=model)
    invoice, i_cost = extract(i_blocks, InvoiceFields, "invoice", model=model)

    c_rate, c_ungrounded = grounding_rate(contract, CONTRACT_CHECKED, c_text)
    i_rate, i_ungrounded = grounding_rate(invoice, INVOICE_CHECKED, i_text)

    # Combine only the halves that could actually be checked. Averaging a
    # real number with a None would invent confidence the vision path has
    # not earned.
    rates = [r for r in (c_rate, i_rate) if r is not None]
    combined = sum(rates) / len(rates) if rates else None

    return {
        "contract": contract,
        "invoice": invoice,
        "cost_usd": c_cost + i_cost,
        "path": f"{c_path}/{i_path}",
        "grounding_rate": combined,
        "ungrounded_fields": [f"contract.{f}" for f in c_ungrounded]
                             + [f"invoice.{f}" for f in i_ungrounded],
    }


def to_eval_fields(result: dict[str, Any]) -> dict[str, Any]:
    """Flatten a run_pair result into the fields the golden set scores.

    is_exception is hardcoded False here. This week measures extraction
    only. Establishing that boundary now means that when the number moves in
    week 3, you know exactly which layer moved it.
    """
    contract, invoice = result["contract"], result["invoice"]
    return {
        "creator_name": contract.creator_name,
        "contract_rate_usd": contract.rate_usd,
        "invoice_total_usd": invoice.total_usd,
        "deliverable_count_contracted": sum(d.count for d in contract.deliverables) or None,
        "deliverable_count_invoiced": sum(li.quantity for li in invoice.line_items) or None,
        "is_exception": False,
        "exception_type": None,
        "_path": result["path"],
        "_grounding_rate": result["grounding_rate"],
    }
