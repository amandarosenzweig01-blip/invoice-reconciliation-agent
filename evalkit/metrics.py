"""Metrics. Small, boring, and auditable on purpose.

Every number an interviewer asks about should be traceable to about ten
lines of code they could read over your shoulder.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from .cases import values_match


def field_accuracy(
    rows: Sequence[dict[str, Any]],
    fields: Sequence[str],
    money_fields: Iterable[str] = (),
) -> dict[str, float]:
    """Per-field exact-match accuracy across rows.

    Each row needs 'expected' and 'predicted' dicts. Fields absent from a
    row's expected dict are skipped for that row rather than counted wrong,
    so partial labeling does not silently deflate the score.
    """
    money = set(money_fields)
    scores: dict[str, float] = {}
    for name in fields:
        hits = 0
        total = 0
        for row in rows:
            expected = row.get("expected") or {}
            if name not in expected:
                continue
            total += 1
            predicted = row.get("predicted") or {}
            if values_match(expected.get(name), predicted.get(name), money=name in money):
                hits += 1
        scores[name] = hits / total if total else float("nan")
    return scores


def binary_prf(y_true: Sequence[bool], y_pred: Sequence[bool]) -> dict[str, float]:
    """Precision, recall, F1 for a positive class such as 'is an exception'."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must be the same length")
    tp = sum(1 for t, p in zip(y_true, y_pred) if t and p)
    fp = sum(1 for t, p in zip(y_true, y_pred) if not t and p)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t and not p)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
    }


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile. No numpy dependency, no interpolation debate."""
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return float("nan")
    if p <= 0:
        return clean[0]
    if p >= 100:
        return clean[-1]
    rank = max(1, min(len(clean), int(round(p / 100 * len(clean) + 0.5)) - 1 + 1))
    return clean[rank - 1]


def latency_summary(values: Sequence[float]) -> dict[str, float]:
    clean = [v for v in values if v is not None]
    if not clean:
        return {"p50_s": float("nan"), "p95_s": float("nan"), "mean_s": float("nan")}
    return {
        "p50_s": percentile(clean, 50),
        "p95_s": percentile(clean, 95),
        "mean_s": sum(clean) / len(clean),
    }


def cost_summary(values: Sequence[float]) -> dict[str, float]:
    clean = [v for v in values if v is not None]
    if not clean:
        return {"total_usd": 0.0, "mean_usd": 0.0}
    return {"total_usd": sum(clean), "mean_usd": sum(clean) / len(clean)}
