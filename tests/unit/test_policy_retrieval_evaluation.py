"""Metric fixtures for multiple-relevant policy retrieval evaluation."""

import math
from datetime import date

import pytest

from app.platform.policy_reference import ClauseType, DocumentStatus
from app.platform.policy_retrieval import PolicyClauseRecord, PolicySearchHit
from scripts.evaluate_policy_retrieval import (
    GoldQuery,
    QueryOutcome,
    metrics,
    ndcg,
    reciprocal_rank,
)

pytestmark = pytest.mark.unit


def _hit(clause_id: str) -> PolicySearchHit:
    document_id, version, _ = clause_id.split(":", maxsplit=2)
    return PolicySearchHit(
        clause=PolicyClauseRecord(
            row_id=clause_id,
            tenant_id="tenant-a",
            document_id=document_id,
            document_version=version,
            title="정책",
            clause_id=clause_id,
            section_path=("정책",),
            clause_type=ClauseType.RULE,
            text="정책 조항",
            policy_type="RETURN_EXCHANGE",
            product_categories=("GENERAL",),
            defect_types=("LEAKAGE",),
            actions=("REVIEW",),
            requires_human_review=False,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            document_status=DocumentStatus.ACTIVE,
            source_type="SYNTHETIC_REFERENCE",
            source_hash="a" * 64,
        ),
        lexical_rank=1,
        lexical_score=1.0,
    )


def test_reciprocal_rank_and_ndcg_multiple_relevant_fixture() -> None:
    relevant = frozenset({"POLICY-A:1.0.0:C1", "POLICY-A:1.0.0:C2"})
    ids = ("POLICY-A:1.0.0:C2", "POLICY-X:1.0.0:C1", "POLICY-A:1.0.0:C1")
    assert reciprocal_rank(ids, relevant) == 1.0
    assert ndcg(ids, relevant) == pytest.approx(1.5 / (1.0 + 1.0 / math.log2(3)))


def test_ndcg_penalizes_missing_relevant_when_result_list_is_short() -> None:
    relevant = frozenset({"POLICY-A:1.0.0:C1", "POLICY-A:1.0.0:C2"})
    assert ndcg(("POLICY-A:1.0.0:C1",), relevant) == pytest.approx(1.0 / (1.0 + 1.0 / math.log2(3)))


def test_metrics_reports_recall_precision_exact_coverage_and_correctness() -> None:
    relevant = ("POLICY-A:1.0.0:C1", "POLICY-A:1.0.0:C2")
    ranked = (
        _hit("POLICY-A:1.0.0:C2"),
        _hit("POLICY-X:1.0.0:C1"),
        _hit("POLICY-A:1.0.0:C1"),
    )
    outcome = QueryOutcome(
        gold=GoldQuery(
            payload={
                "query_id": "fixture",
                "query_text": "누액 교환",
                "as_of_date": "2026-02-01",
                "tenant_id": "tenant-a",
                "case": {"product_category": "GENERAL"},
                "expected_filters": {},
                "relevant_clause_ids": list(relevant),
                "hard_negative_clause_ids": [],
            },
            tenant_uuid="tenant-a",
        ),
        hits={"LEXICAL_BM25": ranked},
        latency_ms={"LEXICAL_BM25": 4.0},
        deterministic=True,
    )
    result = metrics((outcome,), "LEXICAL_BM25")
    assert result["recall_at_1"] == 0.5
    assert result["recall_at_3"] == 1.0
    assert result["precision_at_3"] == pytest.approx(2 / 3)
    assert result["exact_gold_coverage_at_3"] == 1.0
    assert result["mrr_at_10"] == 1.0
    assert result["cross_tenant_retrieval_rate"] == 0.0
    assert result["future_policy_retrieval_rate"] == 0.0
    assert result["retired_policy_retrieval_rate"] == 0.0
    assert result["duplicate_clause_hit_count"] == 0
    assert result["deterministic_ranking"] == 1.0
