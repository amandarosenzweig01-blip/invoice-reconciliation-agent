"""Golden dataset loading and value normalization.

A golden file is JSONL. One case per line:

    {"id": "inv_001", "input": {...}, "expected": {...}, "tags": ["scanned"]}

`input` is whatever your predict function needs (a file path, a question
string, a dict of two paths). `expected` is the labeled answer. `tags` let
you slice results later, which is how you find out that accuracy is fine
overall and terrible on the scanned subset.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Case:
    id: str
    input: Any
    expected: dict[str, Any]
    tags: list[str] = field(default_factory=list)


def load_cases(path: str | Path) -> list[Case]:
    cases: list[Case] = []
    seen: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno} is not valid JSON: {exc}") from exc
            for required in ("id", "input", "expected"):
                if required not in raw:
                    raise ValueError(f"{path}:{lineno} is missing '{required}'")
            case_id = str(raw["id"])
            if case_id in seen:
                raise ValueError(f"{path}:{lineno} duplicates case id '{case_id}'")
            seen.add(case_id)
            cases.append(
                Case(
                    id=case_id,
                    input=raw["input"],
                    expected=raw["expected"],
                    tags=list(raw.get("tags", [])),
                )
            )
    if not cases:
        raise ValueError(f"{path} contains no cases")
    return cases


_CURRENCY = re.compile(r"[^0-9.\-]")
_WHITESPACE = re.compile(r"\s+")


def normalize(value: Any) -> Any:
    """Make two values comparable without pretending they are equal.

    Strings lose case, surrounding whitespace, and internal runs of
    whitespace. Numbers stay numbers. Everything else is returned as is.
    Keep this conservative. If you find yourself adding clever rules here to
    make the score go up, you are moving the goalposts rather than fixing
    the extractor.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 4)
    if isinstance(value, str):
        cleaned = _WHITESPACE.sub(" ", value.strip().lower())
        return cleaned
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def as_money(value: Any) -> float | None:
    """Parse '$1,250.00', '1250', 1250.0 into 1250.0. Returns None on failure."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 2)
    if isinstance(value, str):
        stripped = _CURRENCY.sub("", value)
        if stripped in ("", "-", "."):
            return None
        try:
            return round(float(stripped), 2)
        except ValueError:
            return None
    return None


def values_match(expected: Any, predicted: Any, money: bool = False) -> bool:
    if money:
        left, right = as_money(expected), as_money(predicted)
        if left is None or right is None:
            return left is right
        return abs(left - right) < 0.005
    return normalize(expected) == normalize(predicted)
