"""Shared evaluation harness. Copy this package into each project repo unchanged."""

from .cases import Case, as_money, load_cases, normalize, values_match
from .metrics import binary_prf, cost_summary, field_accuracy, latency_summary, percentile
from .report import compare, summarize, to_markdown
from .runner import latest_run, load_run, run

__all__ = [
    "Case", "load_cases", "normalize", "as_money", "values_match",
    "field_accuracy", "binary_prf", "latency_summary", "cost_summary", "percentile",
    "run", "load_run", "latest_run",
    "summarize", "to_markdown", "compare",
]
