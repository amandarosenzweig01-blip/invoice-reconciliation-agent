"""Turn a run record into the markdown table that goes in your README.

The output of `summarize` plus `to_markdown` is meant to be pasted directly
under the Results heading. The output of `compare` is the before-and-after
table, which is the single most persuasive artifact in the whole repo.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from .metrics import binary_prf, cost_summary, field_accuracy, latency_summary


def summarize(
    run_record: dict[str, Any],
    fields: Sequence[str],
    money_fields: Iterable[str] = (),
    flag_field: str | None = None,
) -> dict[str, Any]:
    """Collapse a run into headline numbers.

    `flag_field` names a boolean field in expected/predicted, such as
    'is_exception'. When given, precision and recall are computed for it.
    """
    rows = run_record["rows"]
    ok_rows = [r for r in rows if not r.get("error")]

    summary: dict[str, Any] = {
        "run_name": run_record.get("run_name"),
        "variant": run_record.get("variant"),
        "cases": len(rows),
        "errors": len(rows) - len(ok_rows),
        "field_accuracy": field_accuracy(ok_rows, fields, money_fields),
        "latency": latency_summary([r.get("latency_s") for r in rows]),
        "cost": cost_summary([r.get("cost_usd") for r in rows]),
    }

    accs = [v for v in summary["field_accuracy"].values() if v == v]
    summary["field_accuracy_mean"] = sum(accs) / len(accs) if accs else float("nan")

    if flag_field:
        y_true = [bool((r.get("expected") or {}).get(flag_field)) for r in ok_rows]
        y_pred = [bool((r.get("predicted") or {}).get(flag_field)) for r in ok_rows]
        summary["flag"] = {"field": flag_field, **binary_prf(y_true, y_pred)}

    by_tag: dict[str, dict[str, float]] = {}
    for tag in sorted({t for r in ok_rows for t in r.get("tags", [])}):
        tagged = [r for r in ok_rows if tag in r.get("tags", [])]
        tag_accs = [v for v in field_accuracy(tagged, fields, money_fields).values() if v == v]
        by_tag[tag] = {
            "cases": len(tagged),
            "field_accuracy_mean": sum(tag_accs) / len(tag_accs) if tag_accs else float("nan"),
        }
    summary["by_tag"] = by_tag
    return summary


def _pct(value: float) -> str:
    return "n/a" if value != value else f"{value * 100:.1f}%"


def to_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"### {summary['run_name']} / {summary['variant']}")
    lines.append("")
    lines.append(f"{summary['cases']} cases, {summary['errors']} hard errors.")
    lines.append("")
    lines.append("| Field | Accuracy |")
    lines.append("| --- | --- |")
    for name, value in summary["field_accuracy"].items():
        lines.append(f"| {name} | {_pct(value)} |")
    lines.append(f"| **mean** | **{_pct(summary['field_accuracy_mean'])}** |")
    lines.append("")

    if "flag" in summary:
        flag = summary["flag"]
        lines.append(f"**{flag['field']}**: precision {_pct(flag['precision'])}, "
                     f"recall {_pct(flag['recall'])}, F1 {_pct(flag['f1'])} "
                     f"({flag['true_positives']} TP, {flag['false_positives']} FP, "
                     f"{flag['false_negatives']} FN)")
        lines.append("")

    lat, cost = summary["latency"], summary["cost"]
    lines.append(f"Latency p50 {lat['p50_s']:.2f}s, p95 {lat['p95_s']:.2f}s. "
                 f"Cost {cost['mean_usd']:.4f} USD per case, {cost['total_usd']:.2f} USD total.")
    lines.append("")

    if summary["by_tag"]:
        lines.append("| Slice | Cases | Mean accuracy |")
        lines.append("| --- | --- | --- |")
        for tag, stats in summary["by_tag"].items():
            lines.append(f"| {tag} | {stats['cases']} | {_pct(stats['field_accuracy_mean'])} |")
        lines.append("")
    return "\n".join(lines)


def compare(before: dict[str, Any], after: dict[str, Any]) -> str:
    """Before-and-after table across two summaries."""
    lines = [
        f"### {before['variant']} vs {after['variant']}",
        "",
        "| Field | Before | After | Delta |",
        "| --- | --- | --- | --- |",
    ]
    names = list(dict.fromkeys(list(before["field_accuracy"]) + list(after["field_accuracy"])))
    for name in names:
        b = before["field_accuracy"].get(name, float("nan"))
        a = after["field_accuracy"].get(name, float("nan"))
        delta = "n/a" if (b != b or a != a) else f"{(a - b) * 100:+.1f} pts"
        lines.append(f"| {name} | {_pct(b)} | {_pct(a)} | {delta} |")

    bm, am = before["field_accuracy_mean"], after["field_accuracy_mean"]
    dm = "n/a" if (bm != bm or am != am) else f"{(am - bm) * 100:+.1f} pts"
    lines.append(f"| **mean** | **{_pct(bm)}** | **{_pct(am)}** | **{dm}** |")
    lines.append("")
    lines.append(f"Latency p95: {before['latency']['p95_s']:.2f}s to {after['latency']['p95_s']:.2f}s. "
                 f"Cost per case: {before['cost']['mean_usd']:.4f} to {after['cost']['mean_usd']:.4f} USD.")
    return "\n".join(lines)
