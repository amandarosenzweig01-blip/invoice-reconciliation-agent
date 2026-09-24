"""Scenario specs: the ground truth for every case in the corpus.

The whole design rests on one idea. We do not generate documents and then
label them. We generate a spec, mutate it with a defect injector that
updates the label in the same function, and only then render documents from
it. Because the mutation and the label are written together they cannot
drift apart, so the golden set is correct by construction.

Run this file directly to print the planned distribution:

    python tools/scenarios.py
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

# --- source material -------------------------------------------------------

CREATORS = [
    "Ava Reyes", "Mira Chen", "Jordan Whitfield", "Simone Okafor", "Elena Vasquez",
    "Priya Raman", "Noor Haddad", "Tessa Lindqvist", "Camille Boucher", "Yuki Tanaka",
    "Rosa Delgado", "Imani Brooks", "Hana Park", "Lucia Ferrari", "Nadia Petrov",
    "Grace Oyelaran", "Sofia Marchetti", "Dana Kowalski", "Leila Nasser", "Jia Wen Lim",
]

AGENCIES = [
    "Lumen Studio LLC", "Northside Creative", "Halo Talent Group", "Verso Collective",
    "Bright Lane Media", "Onyx Partners LLC",
]

SUFFIXES = ["Creative LLC", "Media LLC", "Studio", "Inc.", "Collective"]

# Unit prices are deliberately round numbers. Messy arithmetic adds nothing
# to what this corpus is testing and makes failures harder to read.
DELIVERABLE_TYPES = {
    "reel": {"label": "Instagram reel", "unit_price": 1500.00},
    "story": {"label": "Instagram story frame", "unit_price": 500.00},
    "ugc_video": {"label": "UGC video asset", "unit_price": 2000.00},
    "static_post": {"label": "Static in-feed post", "unit_price": 1000.00},
}

PAYMENT_TERMS = [30, 45, 60]
CONTRACT_LAYOUTS = ["contract_a", "contract_b", "contract_c"]
INVOICE_LAYOUTS = ["invoice_a", "invoice_b", "invoice_c"]

# --- the plan --------------------------------------------------------------
# Three of these nine are NOT exceptions. They look suspicious and are
# legitimate. Without them, precision is unmeasurable: a system that flags
# everything would score perfectly on recall and be useless in practice.

DEFECT_PLAN: list[tuple[str, int, bool]] = [
    ("clean",                 20, False),
    ("vendor_name_variant",    5, False),
    ("rate_in_words",          4, False),
    ("missing_reference",      3, False),
    ("rate_overcharge",        9, True),
    ("missing_deliverable",    7, True),
    ("bundled_invoice",        4, True),
    ("duplicate_invoice",      4, True),
    ("late_invoice",           4, True),
]

TOTAL_CASES = sum(count for _, count, _ in DEFECT_PLAN)
SCANNED_TARGET = 8          # spread across defect types, not concentrated
DEV_TARGET = 20             # cases you are allowed to inspect while iterating


# --- building a clean case -------------------------------------------------

def _pick_deliverables(rng: random.Random) -> list[dict[str, Any]]:
    kinds = rng.sample(list(DELIVERABLE_TYPES), rng.choice([1, 2, 2, 3]))
    return [{"type": k, "count": rng.choice([1, 1, 2, 2, 3])} for k in kinds]


def _line_items(deliverables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "description": DELIVERABLE_TYPES[d["type"]]["label"],
            "quantity": d["count"],
            "unit_price": DELIVERABLE_TYPES[d["type"]]["unit_price"],
            "amount": round(d["count"] * DELIVERABLE_TYPES[d["type"]]["unit_price"], 2),
        }
        for d in deliverables
    ]


def make_clean_spec(case_id: str, rng: random.Random) -> dict[str, Any]:
    """A contract and a matching invoice with nothing wrong."""
    creator = rng.choice(CREATORS)
    deliverables = _pick_deliverables(rng)
    items = _line_items(deliverables)
    rate = round(sum(i["amount"] for i in items), 2)

    start = date(2026, 1, 1) + timedelta(days=rng.randrange(0, 210))
    window_days = rng.choice([90, 120, 180])
    terms = rng.choice(PAYMENT_TERMS)
    contract_id = f"MC-{start.year}-{rng.randrange(1000, 9999)}"

    return {
        "case_id": case_id,
        "defect": "clean",
        "contract": {
            "creator_name": creator,
            "contract_id": contract_id,
            "rate_usd": rate,
            "deliverables": deliverables,
            "deliverable_count": sum(d["count"] for d in deliverables),
            "usage_window_start": start.isoformat(),
            "usage_window_end": (start + timedelta(days=window_days)).isoformat(),
            "payment_terms_days": terms,
        },
        "invoice": {
            "vendor_name": creator,
            "invoice_number": f"{''.join(w[0] for w in creator.split())}-{rng.randrange(100, 999)}",
            "invoice_date": (start + timedelta(days=rng.randrange(5, 40))).isoformat(),
            "contract_reference": contract_id,
            "line_items": items,
            "total_usd": rate,
        },
        "truth": {
            "is_exception": False,
            "exception_type": None,
            "expected_findings": [],
        },
        "render": {
            "contract_layout": rng.choice(CONTRACT_LAYOUTS),
            "invoice_layout": rng.choice(INVOICE_LAYOUTS),
            "scanned": False,
            "rate_in_words": False,
        },
    }


# --- defect injectors ------------------------------------------------------
# Each takes a clean spec and returns a mutated one. Every injector that
# creates a real problem sets truth in the same breath.

def inject_clean(spec, rng):
    return spec


def inject_vendor_name_variant(spec, rng):
    """The invoice comes from the creator's business entity.

    NOT an exception. "Ava Reyes" signs and "Ava Reyes Creative LLC" bills,
    which is how most creators actually operate. This case exists to catch a
    name matcher that is too strict.
    """
    if rng.random() < 0.3:
        spec["invoice"]["vendor_name"] = rng.choice(AGENCIES)
        spec["invoice"]["billing_on_behalf_of"] = spec["contract"]["creator_name"]
    else:
        spec["invoice"]["vendor_name"] = f"{spec['contract']['creator_name']} {rng.choice(SUFFIXES)}"
    return spec


def inject_rate_in_words(spec, rng):
    """The contract writes the fee out in words instead of digits.

    NOT an exception. This is an extraction robustness case only.
    """
    spec["render"]["rate_in_words"] = True
    return spec


def inject_missing_reference(spec, rng):
    """The invoice never cites the contract it belongs to.

    NOT an exception. This is the hallucination trap: a model asked to find a
    contract reference that is not present will often produce a plausible
    looking ID rather than returning null.
    """
    spec["invoice"]["contract_reference"] = None
    return spec


def inject_rate_overcharge(spec, rng):
    over_pct = rng.uniform(0.05, 0.25)
    new_total = round(spec["contract"]["rate_usd"] * (1 + over_pct), 2)
    items = spec["invoice"]["line_items"]
    # Put the whole overage on the last line so the invoice still adds up.
    delta = round(new_total - spec["invoice"]["total_usd"], 2)
    items[-1]["amount"] = round(items[-1]["amount"] + delta, 2)
    items[-1]["unit_price"] = round(items[-1]["amount"] / items[-1]["quantity"], 2)
    spec["invoice"]["total_usd"] = new_total
    spec["truth"] = {"is_exception": True, "exception_type": "rate_overcharge",
                     "expected_findings": ["rate_overcharge"]}
    return spec


def inject_missing_deliverable(spec, rng):
    """Invoice bills for fewer deliverables than the contract specifies."""
    items = spec["invoice"]["line_items"]
    if len(items) > 1:
        dropped = items.pop(rng.randrange(len(items)))
    else:
        if items[0]["quantity"] <= 1:
            return inject_rate_overcharge(spec, rng)   # cannot drop below one
        items[0]["quantity"] -= 1
        items[0]["amount"] = round(items[0]["quantity"] * items[0]["unit_price"], 2)
    spec["invoice"]["total_usd"] = round(sum(i["amount"] for i in items), 2)
    spec["truth"] = {"is_exception": True, "exception_type": "deliverable_count_mismatch",
                     "expected_findings": ["deliverable_count"]}
    return spec


def inject_bundled_invoice(spec, rng):
    """One invoice covering this contract and a second, unrelated one.

    The right behavior is to notice the invoice is out of scope rather than
    silently reconcile the part that happens to match.
    """
    extra = _line_items(_pick_deliverables(rng))
    other_id = f"MC-2026-{rng.randrange(1000, 9999)}"
    for item in extra:
        item["description"] = f"{item['description']} (ref {other_id})"
    spec["invoice"]["line_items"].extend(extra)
    spec["invoice"]["total_usd"] = round(
        sum(i["amount"] for i in spec["invoice"]["line_items"]), 2)
    spec["invoice"]["contract_reference"] = f"{spec['contract']['contract_id']}, {other_id}"
    spec["truth"] = {"is_exception": True, "exception_type": "bundled_invoice",
                     "expected_findings": ["scope", "rate_overcharge"]}
    return spec


def inject_late_invoice(spec, rng):
    """Invoice submitted after the contractual submission deadline."""
    end = date.fromisoformat(spec["contract"]["usage_window_end"])
    terms = spec["contract"]["payment_terms_days"]
    spec["invoice"]["invoice_date"] = (
        end + timedelta(days=terms + rng.randrange(15, 90))).isoformat()
    spec["truth"] = {"is_exception": True, "exception_type": "late_submission",
                     "expected_findings": ["payment_window"]}
    return spec


def inject_duplicate_invoice(spec, rng):
    """Marked here, resolved at corpus level.

    A duplicate only exists relative to invoices already seen, so this is the
    one rule that needs state rather than just the two documents in hand.
    The corpus builder copies an earlier invoice number in afterwards.
    """
    spec["truth"] = {"is_exception": True, "exception_type": "duplicate_invoice",
                     "expected_findings": ["duplicate_invoice"]}
    spec["_needs_duplicate_number"] = True
    return spec


INJECTORS = {
    "clean": inject_clean,
    "vendor_name_variant": inject_vendor_name_variant,
    "rate_in_words": inject_rate_in_words,
    "missing_reference": inject_missing_reference,
    "rate_overcharge": inject_rate_overcharge,
    "missing_deliverable": inject_missing_deliverable,
    "bundled_invoice": inject_bundled_invoice,
    "duplicate_invoice": inject_duplicate_invoice,
    "late_invoice": inject_late_invoice,
}


# --- corpus assembly -------------------------------------------------------

def build_corpus(seed: int = 20260924) -> list[dict[str, Any]]:
    rng = random.Random(seed)

    defects: list[str] = []
    for name, count, _ in DEFECT_PLAN:
        defects.extend([name] * count)
    rng.shuffle(defects)

    specs = []
    for i, defect in enumerate(defects, start=1):
        spec = make_clean_spec(f"case_{i:03d}", rng)
        spec["defect"] = defect
        specs.append(INJECTORS[defect](spec, rng))

    # Duplicates borrow an invoice number from an earlier non-duplicate case.
    donors = [s for s in specs if s["defect"] != "duplicate_invoice"]
    for spec in specs:
        if spec.pop("_needs_duplicate_number", False):
            donor = rng.choice([d for d in donors
                                if int(d["case_id"][-3:]) < int(spec["case_id"][-3:])] or donors)
            spec["invoice"]["invoice_number"] = donor["invoice"]["invoice_number"]
            spec["truth"]["duplicate_of"] = donor["case_id"]

    # Scanned cases spread across defect types rather than clustered, so the
    # vision path is exercised on both good and bad invoices.
    for spec in rng.sample(specs, SCANNED_TARGET):
        spec["render"]["scanned"] = True

    # Dev and test split. You may inspect dev cases freely. Test cases run
    # only at variant boundaries and are never examined one by one, because
    # patching a prompt against every failure fits the prompt to the
    # evaluation set and the number stops predicting anything.
    dev_ids = {s["case_id"] for s in rng.sample(specs, DEV_TARGET)}
    for spec in specs:
        spec["split"] = "dev" if spec["case_id"] in dev_ids else "test"

    return specs


def summarize(specs: list[dict[str, Any]]) -> str:
    from collections import Counter
    by_defect = Counter(s["defect"] for s in specs)
    lines = [f"{len(specs)} cases", ""]
    lines.append(f"{'defect':<24}{'n':>4}  exception")
    for name, _, is_exc in DEFECT_PLAN:
        lines.append(f"{name:<24}{by_defect[name]:>4}  {'yes' if is_exc else 'no'}")
    lines.append("")
    lines.append(f"exceptions       {sum(1 for s in specs if s['truth']['is_exception']):>4}")
    lines.append(f"approvals        {sum(1 for s in specs if not s['truth']['is_exception']):>4}")
    lines.append(f"scanned          {sum(1 for s in specs if s['render']['scanned']):>4}")
    lines.append(f"dev split        {sum(1 for s in specs if s['split'] == 'dev'):>4}")
    lines.append(f"test split       {sum(1 for s in specs if s['split'] == 'test'):>4}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summarize(build_corpus()))
