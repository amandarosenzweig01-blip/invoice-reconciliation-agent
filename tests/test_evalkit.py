"""Smoke tests. These also serve as usage examples for the harness."""

import json
from pathlib import Path

from evalkit import (binary_prf, compare, field_accuracy, load_cases, run,
                     summarize, values_match)


def _write_golden(tmp_path: Path) -> Path:
    path = tmp_path / "golden.jsonl"
    rows = [
        {"id": "a", "input": {"n": 1}, "expected": {"vendor": "Acme LLC", "total": 100.0,
                                                    "is_exception": False}, "tags": ["clean"]},
        {"id": "b", "input": {"n": 2}, "expected": {"vendor": "Beta Co", "total": 250.5,
                                                    "is_exception": True}, "tags": ["scanned"]},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def test_money_matching_is_format_insensitive():
    assert values_match("$1,250.00", 1250, money=True)
    assert not values_match("$1,250.00", 1250.75, money=True)


def test_string_matching_ignores_case_and_spacing():
    assert values_match("Acme  LLC", "acme llc")


def test_binary_prf_counts():
    out = binary_prf([True, True, False], [True, False, False])
    assert out["true_positives"] == 1
    assert out["false_negatives"] == 1
    assert out["precision"] == 1.0


def test_partial_labels_are_skipped_not_penalized():
    rows = [
        {"expected": {"vendor": "a"}, "predicted": {"vendor": "a"}},
        {"expected": {}, "predicted": {"vendor": "z"}},
    ]
    assert field_accuracy(rows, ["vendor"])["vendor"] == 1.0


def test_run_and_compare_end_to_end(tmp_path):
    cases = load_cases(_write_golden(tmp_path))
    fields = ["vendor", "total", "is_exception"]

    def perfect(case_input):
        expected = {1: {"vendor": "Acme LLC", "total": 100.0, "is_exception": False},
                    2: {"vendor": "Beta Co", "total": 250.5, "is_exception": True}}
        return expected[case_input["n"]], 0.001

    def sloppy(case_input):
        return {"vendor": "wrong", "total": 0, "is_exception": False}, 0.001

    before = summarize(run(cases, sloppy, "t", "baseline", results_dir=tmp_path / "r"),
                       fields, ["total"], "is_exception")
    after = summarize(run(cases, perfect, "t", "fixed", results_dir=tmp_path / "r"),
                      fields, ["total"], "is_exception")

    assert after["field_accuracy_mean"] == 1.0
    assert before["field_accuracy_mean"] < after["field_accuracy_mean"]
    assert "+" in compare(before, after)
