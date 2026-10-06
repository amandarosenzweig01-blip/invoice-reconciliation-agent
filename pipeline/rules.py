"""Reconciliation rules. No model calls in this file, on purpose.

This is the layer that decides. It is deterministic because determinism buys
four things that matter to a customer: the same inputs always produce the
same verdict, the rules are unit testable without spending a cent, a finance
team can read them and disagree with a specific line, and arithmetic is
something computers have been reliably correct about for seventy years.
Routing that through a probabilistic system would add risk for no benefit.

Every message is written for a marketing operations manager, not for you.
They are what the demo shows, and a rule name is not an explanation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from rapidfuzz import fuzz

VENDOR_MATCH_THRESHOLD = 85
MONEY_TOLERANCE = 0.005


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str          # "blocker" sets the verdict to flag; "warning" does not
    expected: Any
    actual: Any
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "severity": self.severity,
                "expected": str(self.expected), "actual": str(self.actual),
                "message": self.message}


@dataclass
class Ledger:
    """Invoice numbers already seen, which is what makes duplicate detection
    possible. It is the one rule that needs state rather than just the two
    documents in front of you, and it is worth calling that out in the demo.
    """
    seen: dict[str, str] = field(default_factory=dict)   # invoice_number -> case label

    def record(self, invoice_number: str | None, label: str) -> None:
        if invoice_number:
            self.seen.setdefault(invoice_number, label)

    def prior(self, invoice_number: str | None, label: str) -> str | None:
        if not invoice_number:
            return None
        found = self.seen.get(invoice_number)
        return found if found and found != label else None


# --- the rules -------------------------------------------------------------

def check_vendor(contract, invoice) -> Finding | None:
    """Names rarely match exactly, and that is normal rather than suspicious.

    Two legitimate patterns show up constantly. A creator signs as "Ava
    Reyes" and bills as "Ava Reyes Creative LLC". Or an agency bills on the
    creator's behalf, in which case the invoice names the agency and cites
    the creator separately, so that field is what we compare.

    token_set_ratio ignores word order and duplicate tokens, so an added LLC
    suffix costs very little similarity. The 85 threshold came from running
    the matcher over the dev set and finding where legitimate variants and
    genuinely different names separate. It is empirical, not principled.
    """
    billed_for = getattr(invoice, "billing_on_behalf_of", None) or invoice.vendor_name
    if not contract.creator_name or not billed_for:
        return Finding("vendor_match", "warning", contract.creator_name, billed_for,
                       "A party name is missing from one of the documents, so the "
                       "counterparty could not be confirmed.")
    score = fuzz.token_set_ratio(contract.creator_name.lower(), billed_for.lower())
    if score < VENDOR_MATCH_THRESHOLD:
        return Finding("vendor_match", "blocker", contract.creator_name, billed_for,
                       f"This invoice bills for {billed_for}, but the contract is with "
                       f"{contract.creator_name}.")
    return None


def check_total(contract, invoice) -> Finding | None:
    """Overcharge is a blocker. Undercharge is only a warning, because a
    creator billing less than contracted costs the brand nothing and often
    just means a deliverable is still outstanding."""
    if contract.rate_usd is None or invoice.total_usd is None:
        return None
    if invoice.total_usd > contract.rate_usd + MONEY_TOLERANCE:
        over = invoice.total_usd - contract.rate_usd
        return Finding("rate_overcharge", "blocker", contract.rate_usd, invoice.total_usd,
                       f"The invoice is \\${over:,.2f} above the contracted fee of "
                       f"\\${contract.rate_usd:,.2f}.")
    if invoice.total_usd < contract.rate_usd - MONEY_TOLERANCE:
        under = contract.rate_usd - invoice.total_usd
        return Finding("rate_undercharge", "warning", contract.rate_usd, invoice.total_usd,
                       f"The invoice is \\${under:,.2f} below the contracted fee, which may "
                       f"\\mean deliverables are still outstanding.")
    return None


def check_deliverable_count(contract, invoice) -> Finding | None:
    contracted = sum(d.count for d in contract.deliverables)
    invoiced = sum(li.quantity for li in invoice.line_items)
    if not contracted or not invoiced:
        return None
    if invoiced < contracted:
        return Finding("deliverable_count", "blocker", contracted, invoiced,
                       f"The contract covers {contracted} deliverables but the invoice "
                       f"bills for {invoiced}.")
    if invoiced > contracted:
        return Finding("deliverable_count", "blocker", contracted, invoiced,
                       f"The invoice bills for {invoiced} deliverables but the contract "
                       f"covers {contracted}.")
    return None


def check_scope(contract, invoice) -> Finding | None:
    """One invoice covering several contracts.

    The right behavior is to notice the invoice is out of scope rather than
    silently reconcile only the part that happens to match. A partial match
    that looks clean is worse than an obvious failure.
    """
    ref = invoice.contract_reference
    if not ref:
        return None          # a missing reference is not by itself a problem
    refs = [r.strip() for r in str(ref).replace(";", ",").split(",") if r.strip()]
    if len(refs) > 1:
        return Finding("scope", "blocker", contract.contract_id, ref,
                       f"This invoice covers {len(refs)} contracts and cannot be "
                       f"reconciled against {contract.contract_id} alone.")
    if contract.contract_id and refs[0] != contract.contract_id:
        return Finding("scope", "blocker", contract.contract_id, refs[0],
                       f"The invoice cites contract {refs[0]} but was matched to "
                       f"{contract.contract_id}.")
    return None


def check_payment_window(contract, invoice) -> Finding | None:
    """Invoices must arrive within the submission deadline, which the
    contracts define as the close of the usage window plus the payment terms."""
    if not (contract.usage_window_end and contract.payment_terms_days and invoice.invoice_date):
        return None
    deadline = contract.usage_window_end + timedelta(days=contract.payment_terms_days)
    if invoice.invoice_date > deadline:
        days_late = (invoice.invoice_date - deadline).days
        return Finding("payment_window", "blocker", deadline.isoformat(),
                       invoice.invoice_date.isoformat(),
                       f"This invoice arrived {days_late} days after the submission "
                       f"deadline of {deadline:%B %d, %Y}.")
    return None


def check_duplicate(invoice, ledger: Ledger, label: str) -> Finding | None:
    prior = ledger.prior(invoice.invoice_number, label)
    if prior:
        return Finding("duplicate_invoice", "blocker", "unique invoice number",
                       invoice.invoice_number,
                       f"Invoice number {invoice.invoice_number} was already submitted "
                       f"on {prior}.")
    return None


def run_rules(contract, invoice, ledger: Ledger | None = None, label: str = "") -> list[Finding]:
    findings = [
        check_vendor(contract, invoice),
        check_scope(contract, invoice),
        check_total(contract, invoice),
        check_deliverable_count(contract, invoice),
        check_payment_window(contract, invoice),
    ]
    if ledger is not None:
        findings.append(check_duplicate(invoice, ledger, label))
        ledger.record(invoice.invoice_number, label)
    return [f for f in findings if f is not None]
