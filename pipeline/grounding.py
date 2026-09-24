"""Grounding: a confidence signal that is not the model's own opinion.

The obvious way to get confidence is to ask the model for it. Do not. Self
reported confidence from a language model is poorly calibrated, and an
interviewer who knows that will press on it.

Grounding asks a different question: does this extracted value literally
appear in the document? It is cruder and it is checkable, which is the
trade you want. Be honest about the limitation in the README: a value can be
grounded and still be the wrong field, for example picking up a subtotal
that happens to match. Ungrounded values are the useful signal, because they
mean something was reconstructed rather than read.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

_STRIP = re.compile(r"[\s,$]")


def _squash(text: str) -> str:
    return _STRIP.sub("", text.lower())


def grounded(value: Any, source_text: str) -> bool | None:
    """True, False, or None when the check does not apply.

    None happens on the vision path (no text layer to check against) and for
    null values (nothing to verify). Keeping None distinct from False
    matters: "I could not check" and "I checked and it is not there" are
    different claims.
    """
    if value is None or not source_text:
        return None

    haystack = _squash(source_text)

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        candidates = {f"{value:.2f}", f"{value:.2f}".rstrip("0").rstrip("."), f"{value:.0f}"}
        return any(_squash(c) in haystack for c in candidates)
    if isinstance(value, date):
        return any(_squash(value.strftime(fmt)) in haystack
                   for fmt in ("%Y-%m-%d", "%B %-d, %Y", "%b %-d, %Y", "%m/%d/%Y", "%-m/%-d/%Y"))
    return _squash(str(value)) in haystack


# Fields worth checking. Nested lists are skipped because a partial match
# inside a list tells you very little, and a rate or a total appearing
# verbatim is the signal that actually matters for the verdict.
CONTRACT_CHECKED = ["creator_name", "contract_id", "rate_usd",
                    "usage_window_start", "usage_window_end", "payment_terms_days"]
INVOICE_CHECKED = ["vendor_name", "invoice_number", "invoice_date",
                   "contract_reference", "total_usd"]


def grounding_rate(model: Any, fields: list[str], source_text: str) -> tuple[float | None, list[str]]:
    """Share of non-null checked fields that appear in the source.

    Returns (rate, ungrounded_field_names). Rate is None when nothing could
    be checked, which is the vision path. Week 3's escalation gate treats
    None as "cannot vouch for this" rather than as zero.
    """
    checks = {f: grounded(getattr(model, f, None), source_text) for f in fields}
    applicable = {f: v for f, v in checks.items() if v is not None}
    if not applicable:
        return None, []
    ungrounded = sorted(f for f, v in applicable.items() if v is False)
    return sum(applicable.values()) / len(applicable), ungrounded
