"""Rule tests. No API calls, so these cost nothing and run in a second.

The important one is test_rules_are_correct_given_perfect_extraction. It
feeds the ground truth straight into the decision layer, bypassing the model
entirely. If it passes, the rules are right, and any failure you see in a
real eval run is an extraction failure rather than a logic failure. The
decision layer is verified independently of the model.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from pipeline.decide import combine, decide
from pipeline.rules import (Ledger, check_deliverable_count, check_payment_window,
                            check_scope, check_total, check_vendor, run_rules)
from pipeline.schemas import ContractFields, Deliverable, InvoiceFields, LineItem

SPEC_DIR = Path("data/specs")
pytestmark = pytest.mark.skipif(not SPEC_DIR.exists(), reason="corpus not generated yet")

CONTRACT_KEYS = ["creator_name", "contract_id", "rate_usd", "deliverables",
                 "usage_window_start", "usage_window_end", "payment_terms_days"]


def models_from(spec: dict) -> tuple[ContractFields, InvoiceFields]:
    c, i = spec["contract"], spec["invoice"]
    return (
        ContractFields(**{k: c[k] for k in CONTRACT_KEYS}),
        InvoiceFields(
            vendor_name=i["vendor_name"],
            billing_on_behalf_of=i.get("billing_on_behalf_of"),
            invoice_number=i["invoice_number"],
            invoice_date=i["invoice_date"],
            contract_reference=i["contract_reference"],
            line_items=i["line_items"],
            total_usd=i["total_usd"],
        ),
    )


@pytest.fixture(scope="module")
def specs() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(SPEC_DIR.glob("case_*.json"))]


def test_rules_are_correct_given_perfect_extraction(specs):
    """Every one of the 60 cases must get the right verdict when the
    extraction is handed to the rules without error."""
    ledger = Ledger()
    wrong = []
    for spec in specs:
        contract, invoice = models_from(spec)
        out = decide(contract, invoice, 1.0, 1.0, ledger=ledger, label=spec["case_id"])
        predicted = out["verdict"] == "flag"
        if predicted != spec["truth"]["is_exception"]:
            wrong.append((spec["case_id"], spec["defect"],
                          "false positive" if predicted else "missed",
                          out.get("reason")))
    assert not wrong, f"{len(wrong)} wrong verdicts: {wrong}"


def test_legitimate_variants_are_not_flagged(specs):
    """vendor_name_variant, rate_in_words, and missing_reference look
    suspicious and are correct invoices. If any of them flags, the system
    is crying wolf and the flags stop being read."""
    ledger = Ledger()
    benign = {"vendor_name_variant", "rate_in_words", "missing_reference", "clean"}
    for spec in specs:
        contract, invoice = models_from(spec)
        out = decide(contract, invoice, 1.0, 1.0, ledger=ledger, label=spec["case_id"])
        if spec["defect"] in benign:
            assert out["verdict"] == "approve", (spec["case_id"], spec["defect"], out["reason"])


def test_agency_billing_on_behalf_of_a_creator_passes():
    contract = ContractFields(creator_name="Ava Reyes")
    invoice = InvoiceFields(vendor_name="Lumen Studio LLC", billing_on_behalf_of="Ava Reyes")
    assert check_vendor(contract, invoice) is None


def test_entity_suffix_does_not_trip_the_matcher():
    contract = ContractFields(creator_name="Ava Reyes")
    invoice = InvoiceFields(vendor_name="Ava Reyes Creative LLC")
    assert check_vendor(contract, invoice) is None


def test_a_genuinely_different_name_is_a_blocker():
    contract = ContractFields(creator_name="Ava Reyes")
    invoice = InvoiceFields(vendor_name="Northside Creative")
    finding = check_vendor(contract, invoice)
    assert finding and finding.severity == "blocker"


def test_overcharge_blocks_and_undercharge_only_warns():
    contract = ContractFields(rate_usd=4500.0)
    over = check_total(contract, InvoiceFields(total_usd=5000.0))
    under = check_total(contract, InvoiceFields(total_usd=4000.0))
    assert over and over.severity == "blocker"
    assert under and under.severity == "warning"
    assert check_total(contract, InvoiceFields(total_usd=4500.0)) is None


def test_deliverable_count_catches_both_directions():
    contract = ContractFields(deliverables=[Deliverable(type="reel", count=3)])
    short = check_deliverable_count(contract, InvoiceFields(
        line_items=[LineItem(description="reel", quantity=2)]))
    over = check_deliverable_count(contract, InvoiceFields(
        line_items=[LineItem(description="reel", quantity=5)]))
    assert short and short.severity == "blocker"
    assert over and over.severity == "blocker"


def test_multiple_contract_references_are_out_of_scope():
    contract = ContractFields(contract_id="MC-2026-1111")
    bundled = check_scope(contract, InvoiceFields(
        contract_reference="MC-2026-1111, MC-2026-2222"))
    assert bundled and bundled.severity == "blocker"


def test_a_missing_reference_is_not_a_problem():
    contract = ContractFields(contract_id="MC-2026-1111")
    assert check_scope(contract, InvoiceFields(contract_reference=None)) is None


def test_payment_window_deadline():
    contract = ContractFields(usage_window_end=date(2026, 6, 1), payment_terms_days=30)
    on_time = check_payment_window(contract, InvoiceFields(invoice_date=date(2026, 6, 30)))
    late = check_payment_window(contract, InvoiceFields(invoice_date=date(2026, 7, 15)))
    assert on_time is None
    assert late and late.severity == "blocker"


def test_duplicate_needs_a_prior_sighting():
    ledger = Ledger()
    first = InvoiceFields(invoice_number="AR-118")
    second = InvoiceFields(invoice_number="AR-118")
    contract = ContractFields()
    first_pass = run_rules(contract, first, ledger=ledger, label="case_001")
    assert not any(f.rule == "duplicate_invoice" for f in first_pass)
    findings = run_rules(contract, second, ledger=ledger, label="case_002")
    assert any(f.rule == "duplicate_invoice" for f in findings)


def test_unverifiable_invoice_escalates_rather_than_being_judged():
    """A clean digital contract must not lend its confidence to a scanned
    invoice. The invoice is the document the verdict is about."""
    contract = ContractFields(creator_name="Ava Reyes", rate_usd=4500.0)
    invoice = InvoiceFields(vendor_name="Ava Reyes", total_usd=9000.0)
    out = decide(contract, invoice, contract_grounding=1.0, invoice_grounding=None)
    assert out["verdict"] == "escalate"
    assert out["reason"] == "invoice_unverifiable"


def test_combine_takes_the_weakest_link():
    assert combine(1.0, 0.4) == 0.4
    assert combine(None, 0.6) == 0.6
    assert combine(None, None) is None


def test_low_confidence_escalates_instead_of_flagging():
    contract = ContractFields(creator_name="Ava Reyes", rate_usd=4500.0)
    invoice = InvoiceFields(vendor_name="Ava Reyes", total_usd=9000.0)
    out = decide(contract, invoice, 0.9, 0.4, threshold=0.75)
    assert out["verdict"] == "escalate"
    assert out["findings"] == []


def test_escalated_invoices_still_enter_the_ledger():
    """Forgetting an escalated invoice number would let the same number sail
    through on a later submission."""
    ledger = Ledger()
    invoice = InvoiceFields(invoice_number="AR-900", vendor_name="Ava Reyes")
    decide(ContractFields(), invoice, 1.0, None, ledger=ledger, label="case_001")
    assert ledger.prior("AR-900", "case_002") == "case_001"
