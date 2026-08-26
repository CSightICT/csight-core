"""Metric and set-invariance tests for locked policy reranker evaluation."""

import pytest

from scripts.evaluate_policy_reranker import (
    ndcg,
    ranking_metrics,
    reciprocal_rank,
    validate_set_invariance,
)

pytestmark = pytest.mark.unit


def test_reciprocal_rank_and_ndcg_support_multiple_relevant_clauses() -> None:
    relevant = frozenset({"a", "b"})
    assert reciprocal_rank(("x", "a", "b"), relevant) == 0.5
    assert ndcg(("a", "b", "x"), relevant) == 1.0


def test_candidate_set_invariance_rejects_loss_addition_and_duplicate() -> None:
    validate_set_invariance(("a", "b"), ("b", "a"))
    for reranked in (("a",), ("a", "c"), ("a", "a")):
        with pytest.raises(ValueError):
            validate_set_invariance(("a", "b"), reranked)


def test_ranking_metrics_compute_final_recall_mrr_ndcg_and_correctness() -> None:
    row = {
        "relevant_clause_ids": ["a", "b"],
        "hard_negative_clause_ids": ["x"],
        "ranked": ["a", "b"],
        "tenant_id": "tenant-a",
        "as_of_date": "2026-02-01",
        "clause_metadata": {
            "a": {
                "tenant_id": "tenant-a",
                "effective_from": "2026-01-01",
                "document_status": "ACTIVE",
            },
            "b": {
                "tenant_id": "tenant-a",
                "effective_from": "2026-01-01",
                "document_status": "ACTIVE",
            },
        },
    }
    metrics = ranking_metrics((row,), "ranked")
    assert metrics["recall_at_10"] == 1.0
    assert metrics["mrr_at_10"] == 1.0
    assert metrics["ndcg_at_10"] == 1.0
    assert metrics["cross_tenant_retrieval_rate"] == 0.0
