"""Three verdicts, not two.

    approve   the rules ran and found nothing
    flag      the rules ran and something specific is wrong with the invoice
    escalate  the rules did not run with enough confidence to be trusted

Keeping escalate separate from flag is the design decision that carries the
most weight in this project. A flag is a claim about the invoice. An
escalation is an admission about the extraction. Collapse them and you tell
a marketing ops manager that a perfectly good invoice is a problem, and
after that happens a few times they stop reading the flags at all.

The gate reads two numbers, one per document, rather than one blended score.
That matters more than it looks. A scanned invoice paired with a clean
digital contract has no grounding signal of its own, and averaging the two
halves would let the contract's confidence stand in for the invoice's. The
invoice is the document the verdict is actually about, so the weakest link
governs: the combined score is the minimum of whatever could be checked, and
an unverifiable invoice escalates on its own.
"""

from __future__ import annotations

from typing import Any

from .rules import Finding, Ledger, run_rules

DEFAULT_THRESHOLD = 0.75


def combine(contract_rate: float | None, invoice_rate: float | None) -> float | None:
    """Minimum of the halves that could be checked, or None if neither could.

    Minimum rather than mean: a verdict is only as trustworthy as the worst
    document behind it, and a mean lets a clean document paper over a bad one.
    """
    rates = [r for r in (contract_rate, invoice_rate) if r is not None]
    return min(rates) if rates else None


def decide(
    contract,
    invoice,
    contract_grounding: float | None,
    invoice_grounding: float | None,
    threshold: float = DEFAULT_THRESHOLD,
    ledger: Ledger | None = None,
    label: str = "",
    escalate_unverifiable: bool = True,
) -> dict[str, Any]:
    combined = combine(contract_grounding, invoice_grounding)

    def escalation(reason: str, explanation: str) -> dict[str, Any]:
        # Still record the invoice number. An escalated invoice has been seen,
        # and forgetting it would let the same number sail through later.
        if ledger is not None:
            ledger.record(invoice.invoice_number, label)
        return {"verdict": "escalate", "reason": reason, "grounding_rate": combined,
                "contract_grounding": contract_grounding,
                "invoice_grounding": invoice_grounding,
                "findings": [], "explanation": explanation}

    if escalate_unverifiable and invoice_grounding is None:
        return escalation(
            "invoice_unverifiable",
            "This invoice had no readable text layer, so the extracted values could not "
            "be checked against the source. A person should confirm them before payment.")

    if escalate_unverifiable and contract_grounding is None:
        return escalation(
            "contract_unverifiable",
            "This contract had no readable text layer, so the contracted terms could not "
            "be checked against the source. A person should confirm them before payment.")

    if combined is not None and combined < threshold:
        return escalation(
            "low_extraction_confidence",
            f"Only {combined:.0%} of the extracted values could be located in the source "
            f"documents, below the {threshold:.0%} threshold. A person should review this one.")

    findings: list[Finding] = run_rules(contract, invoice, ledger=ledger, label=label)
    blockers = [f for f in findings if f.severity == "blocker"]
    return {
        "verdict": "flag" if blockers else "approve",
        "reason": blockers[0].rule if blockers else None,
        "grounding_rate": combined,
        "contract_grounding": contract_grounding,
        "invoice_grounding": invoice_grounding,
        "findings": [f.as_dict() for f in findings],
        "explanation": blockers[0].message if blockers
                       else "The invoice matches the contract on counterparty, fee, "
                            "deliverable count, and submission deadline.",
    }
