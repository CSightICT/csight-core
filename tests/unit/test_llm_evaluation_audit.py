"""Regression tests for the Sprint 3 audit of Qwen qualification metrics."""

from pathlib import Path

import pytest

from evaluation.llm.evaluate_extraction import (
    PRF,
    CaseResult,
    evaluation_contract_diagnostics,
    load_cases,
    set_metrics,
)

pytestmark = pytest.mark.unit


def _result(*, expected: frozenset[str], actual: frozenset[str]) -> CaseResult:
    return CaseResult(
        case_id="synthetic",
        category="metric-test",
        schema_valid=True,
        pydantic_valid=True,
        quotes_valid=True,
        forbidden=False,
        injection_violation=False,
        reasoning_leak=False,
        expected_issues=frozenset(),
        actual_issues=frozenset(),
        expected_action=frozenset({"UNKNOWN"}),
        actual_action="UNKNOWN",
        expected_missing=expected,
        actual_missing=actual,
        output_tokens=0,
        latency_seconds=0,
    )


def test_micro_set_prf_and_empty_set_diagnostics_are_mathematically_explicit() -> None:
    results = [
        _result(expected=frozenset(), actual=frozenset()),
        _result(expected=frozenset({"A", "B"}), actual=frozenset({"A"})),
        _result(expected=frozenset({"C"}), actual=frozenset({"D"})),
    ]

    assert PRF(results, "expected_missing", "actual_missing") == {
        "precision": 0.5,
        "recall": 1 / 3,
        "f1": 0.4,
    }
    metrics = set_metrics(results, "expected_missing", "actual_missing")
    assert metrics["exact_set_match_rate"] == 1 / 3
    assert metrics["empty_expected_cases"] == 1
    assert metrics["empty_actual_cases"] == 1
    assert metrics["expected_label_support"] == 3
    assert metrics["predicted_label_support"] == 2


def test_qualification_taxonomies_match_but_requested_action_meaning_is_ambiguous() -> None:
    dataset = Path(__file__).resolve().parents[2] / "evaluation/llm/qwen38_qualification_v1.jsonl"
    cases = load_cases(dataset)
    diagnostics = evaluation_contract_diagnostics(cases)

    assert len(cases) == 100
    assert diagnostics["issue_taxonomy_matches_output_enum"] is True
    assert diagnostics["action_taxonomy_matches_output_enum"] is True
    assert diagnostics["missing_taxonomy_matches_output_enum"] is True
    assert diagnostics["input_requested_action_distribution"] == {"UNSPECIFIED": 100}
    assert diagnostics["requested_action_semantic_ambiguity"] is True
    assert diagnostics["missing_information_label_support"] == {
        "ADDITIONAL_DESCRIPTION": 10,
        "CUSTOMER_REQUEST": 15,
        "DEFECT_LOCATION": 15,
        "DEFECT_TYPE": 10,
    }
