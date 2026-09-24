"""Run a predict function over a golden set and write versioned results.

Your project supplies one function:

    def predict(case_input) -> dict
    def predict(case_input) -> tuple[dict, float]   # (output, cost_usd)

The runner handles timing, cost accumulation, error capture, and writing a
row-level CSV plus a summary JSON into evals/results/. Results are never
overwritten, which is what makes before-and-after comparisons possible.
"""

from __future__ import annotations

import csv
import json
import platform
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from .cases import Case

RESULTS_DIR = Path("evals/results")


@dataclass
class RunRow:
    case_id: str
    tags: list[str] = field(default_factory=list)
    expected: dict[str, Any] = field(default_factory=dict)
    predicted: dict[str, Any] = field(default_factory=dict)
    latency_s: float | None = None
    cost_usd: float | None = None
    error: str | None = None


def _coerce(result: Any) -> tuple[dict[str, Any], float | None]:
    if isinstance(result, tuple):
        if len(result) != 2:
            raise TypeError("predict returned a tuple that is not (output, cost_usd)")
        output, cost = result
        return dict(output), (float(cost) if cost is not None else None)
    if isinstance(result, dict):
        return dict(result), None
    raise TypeError(f"predict must return a dict or (dict, cost), got {type(result)!r}")


def run(
    cases: Sequence[Case],
    predict: Callable[[Any], Any],
    run_name: str,
    variant: str = "baseline",
    notes: str = "",
    results_dir: Path | str = RESULTS_DIR,
    fail_fast: bool = False,
) -> dict[str, Any]:
    rows: list[RunRow] = []
    started = datetime.now(timezone.utc)

    for case in cases:
        row = RunRow(case_id=case.id, tags=list(case.tags), expected=dict(case.expected))
        clock = time.perf_counter()
        try:
            output, cost = _coerce(predict(case.input))
            row.predicted = output
            row.cost_usd = cost
        except Exception:
            row.error = traceback.format_exc(limit=3).strip().splitlines()[-1]
            if fail_fast:
                raise
        finally:
            row.latency_s = round(time.perf_counter() - clock, 4)
        rows.append(row)
        status = "ERR " if row.error else "ok  "
        print(f"  {status} {case.id:<20} {row.latency_s:>7.2f}s")

    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    slug = f"{run_name}__{variant}__{stamp}"

    csv_path = out_dir / f"{slug}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["case_id", "tags", "expected", "predicted", "latency_s", "cost_usd", "error"])
        for row in rows:
            writer.writerow([
                row.case_id,
                "|".join(row.tags),
                json.dumps(row.expected, sort_keys=True),
                json.dumps(row.predicted, sort_keys=True),
                row.latency_s,
                row.cost_usd,
                row.error or "",
            ])

    run_record = {
        "run_name": run_name,
        "variant": variant,
        "notes": notes,
        "started_utc": started.isoformat(),
        "case_count": len(rows),
        "error_count": sum(1 for r in rows if r.error),
        "python": platform.python_version(),
        "rows_csv": str(csv_path),
        "rows": [asdict(r) for r in rows],
    }
    json_path = out_dir / f"{slug}.json"
    json_path.write_text(json.dumps(run_record, indent=2), encoding="utf-8")

    print(f"\nWrote {csv_path}")
    print(f"Wrote {json_path}")
    return run_record


def load_run(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def latest_run(run_name: str, variant: str, results_dir: Path | str = RESULTS_DIR) -> dict[str, Any] | None:
    matches = sorted(Path(results_dir).glob(f"{run_name}__{variant}__*.json"))
    return load_run(matches[-1]) if matches else None
