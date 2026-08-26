"""Pure metric tests for candidate-pool and oracle diagnostics."""

import math

import pytest

from scripts.analyze_policy_candidates import candidate_metrics, ndcg, oracle_order

pytestmark = pytest.mark.unit


def test_oracle_preserves_candidate_set_and_places_relevant_first() -> None:
    candidates = ("a", "b", "c", "d")
    ordered = oracle_order(candidates, frozenset({"b", "d"}))
    assert ordered == ("b", "d", "a", "c")
    assert frozenset(ordered) == frozenset(candidates)


def test_oracle_ndcg_uses_multiple_relevant_clauses() -> None:
    assert math.isclose(ndcg(("b", "d", "a"), frozenset({"b", "d"})), 1.0)


def test_candidate_metrics_separate_recall_from_oracle_ranking() -> None:
    result = candidate_metrics(
        (
            {
                "relevant_clause_ids": ["b", "d"],
                "candidate_ids": ["a", "b", "c", "d"],
                "hard_negative_clause_ids": ["c"],
            },
        )
    )
    assert result["candidate_recall"] == 1.0
    assert result["candidate_exact_coverage"] == 1.0
    assert result["oracle_mrr_at_10"] == 1.0
    assert result["oracle_ndcg_at_10"] == 1.0
    assert result["hard_negative_inclusion_rate"] == 1.0
