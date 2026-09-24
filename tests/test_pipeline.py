"""Week 2 tests. None of these call the API, so they cost nothing and run in
about a second. Run them before every eval to catch wiring mistakes before
you pay for 120 model calls.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from evalkit import load_cases
from pipeline.extract import PRICING, usage_cost
from pipeline.grounding import CONTRACT_CHECKED, grounded, grounding_rate
from pipeline.routing import build_content_blocks, pdf_text
from pipeline.schemas import ContractFields, InvoiceFields

GOLDEN = Path("evals/golden.jsonl")
pytestmark = pytest.mark.skipif(not GOLDEN.exists(), reason="corpus not generated yet")


@pytest.fixture(scope="module")
def cases():
    return load_cases(GOLDEN)


def test_every_invoice_routes_as_tagged(cases):
    """The corpus tags say which path each case should take. If a scanned
    invoice kept a text layer, it would silently take the cheap path and the
    vision route would never be exercised."""
    for case in cases:
        expected = "vision" if "scanned" in case.tags else "text"
        _, path, _ = build_content_blocks(case.input["invoice_pdf"])
        assert path == expected, f"{case.id} routed {path}, expected {expected}"


def test_vision_path_returns_image_blocks_and_no_source_text(cases):
    scanned = next(c for c in cases if "scanned" in c.tags)
    blocks, path, text = build_content_blocks(scanned.input["invoice_pdf"])
    assert path == "vision"
    assert blocks and all(b["type"] == "image" for b in blocks)
    assert text == ""


def test_grounding_catches_an_invented_field(cases):
    case = next(c for c in cases if "digital" in c.tags)
    spec = json.loads(Path(f"data/specs/{case.id}.json").read_text())
    source = pdf_text(case.input["contract_pdf"])

    truthy = ContractFields(
        creator_name=spec["contract"]["creator_name"],
        contract_id=spec["contract"]["contract_id"],
        rate_usd=spec["contract"]["rate_usd"],
        payment_terms_days=spec["contract"]["payment_terms_days"],
    )
    clean_rate, clean_ungrounded = grounding_rate(truthy, CONTRACT_CHECKED, source)
    assert clean_rate == 1.0 and clean_ungrounded == []

    invented = truthy.model_copy(update={"contract_id": "MC-2026-0000"})
    bad_rate, bad_ungrounded = grounding_rate(invented, CONTRACT_CHECKED, source)
    assert bad_rate < clean_rate
    assert "contract_id" in bad_ungrounded


def test_grounding_returns_none_on_vision_path():
    """None means "could not check" and must stay distinct from 0.0, which
    means "checked and absent". The week 3 gate treats them differently."""
    model = ContractFields(creator_name="Ava Reyes")
    rate, _ = grounding_rate(model, CONTRACT_CHECKED, "")
    assert rate is None


def test_money_grounding_is_format_insensitive():
    assert grounded(4500.0, "total fee of $4,500.00 payable") is True
    assert grounded(4500.0, "total fee of $9,900.00 payable") is False


def test_null_is_never_ungrounded():
    """A missing contract reference is a correct answer, not a failure."""
    assert grounded(None, "any text at all") is None


def test_cost_math():
    usage = types.SimpleNamespace(input_tokens=1_000_000, output_tokens=0)
    assert usage_cost(usage, "claude-sonnet-5") == PRICING["claude-sonnet-5"]["input"]


def test_schemas_allow_everything_to_be_missing():
    """Optional-everything is the design. A required field forces the model
    to invent a value when the document does not have one."""
    assert ContractFields().creator_name is None
    assert InvoiceFields().line_items == []
