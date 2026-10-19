"""Ranking meaning and fail-closed input fixtures; no datasets or providers."""

import math

import pytest
from pydantic import ValidationError

from app.platform.retrieval_evaluation import (
    RETRIEVAL_CUTOFFS,
    RetrievalEvaluationError,
    RetrievalEvaluationMetrics,
    RetrievalEvaluationObservation,
    compute_retrieval_metrics,
)

pytestmark = pytest.mark.unit


def _observation(
    *,
    record_id: str = "case-1",
    relevant: tuple[str, ...] = ("rule", "exception"),
    hits: tuple[str, ...] = ("rule",),
    success: bool = True,
) -> RetrievalEvaluationObservation:
    return RetrievalEvaluationObservation(
        record_id=record_id,
        relevant_clause_ids=relevant,
        hit_clause_ids=hits,
        success=success,
    )


def test_hit_rate_does_not_hide_missing_exception_clause() -> None:
    result = compute_retrieval_metrics((_observation(),))
    assert tuple(item.cutoff for item in result.cutoffs) == RETRIEVAL_CUTOFFS
    for item in result.cutoffs:
        assert item.hit_rate == 1.0
        assert item.clause_recall == 0.5
        assert item.exact_gold_coverage == 0.0
    assert result.mrr_at_10 == 1.0
    assert result.ndcg_at_10 == pytest.approx(round(1 / (1 + 1 / math.log2(3)), 6))


def test_top_three_coverage_is_distinct_from_top_ten_coverage() -> None:
    result = compute_retrieval_metrics(
        (_observation(hits=("rule", "other-1", "other-2", "exception")),)
    )
    by_cutoff = {item.cutoff: item for item in result.cutoffs}
    assert by_cutoff[3].clause_recall == 0.5
    assert by_cutoff[3].exact_gold_coverage == 0.0
    assert by_cutoff[5].clause_recall == 1.0
    assert by_cutoff[10].exact_gold_coverage == 1.0


@pytest.mark.parametrize("hits", ((), ("unrelated",)))
def test_no_relevant_hits_score_zero(hits: tuple[str, ...]) -> None:
    result = compute_retrieval_metrics((_observation(hits=hits),))
    assert all(
        item.hit_rate == item.clause_recall == item.exact_gold_coverage == 0.0
        for item in result.cutoffs
    )
    assert result.mrr_at_10 == result.ndcg_at_10 == 0.0
    assert result.zero_result_rate == float(not hits)


def test_failed_case_stays_in_macro_denominator_with_zero_score() -> None:
    result = compute_retrieval_metrics(
        (
            _observation(hits=("rule", "exception")),
            _observation(record_id="case-2", hits=(), success=False),
        )
    )
    top_ten = next(item for item in result.cutoffs if item.cutoff == 10)
    assert result.record_count == 2
    assert result.success_count == result.failed_count == 1
    assert top_ten.hit_rate == top_ten.clause_recall == top_ten.exact_gold_coverage == 0.5
    assert result.mrr_at_10 == result.ndcg_at_10 == result.zero_result_rate == 0.5


def test_clause_recall_is_case_macro_not_micro_average() -> None:
    result = compute_retrieval_metrics(
        (
            _observation(relevant=("rule",), hits=("rule",)),
            _observation(record_id="case-2", relevant=("a", "b", "c"), hits=("a",)),
        )
    )
    assert result.aggregation == "MACRO_CASE_MEAN_FAILURES_INCLUDED"
    assert result.cutoffs[0].clause_recall == 0.666667
    assert result.cutoffs[0].clause_recall != 2 / 4


@pytest.mark.parametrize("relevant", ((), ("rule", "rule"), ("",), (" ",), (" rule",)))
def test_empty_or_duplicate_gold_fails_closed(relevant: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        _observation(relevant=relevant)


@pytest.mark.parametrize("hits", (("rule", "rule"), ("",), (" ",), ("rule ",)))
def test_duplicate_or_empty_hit_identifiers_fail_closed(hits: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        _observation(hits=hits)


@pytest.mark.parametrize("record_id", ("", " ", " case-1", "case-1 "))
def test_record_identifier_must_not_be_empty_or_padded(record_id: str) -> None:
    with pytest.raises(ValidationError):
        _observation(record_id=record_id)


def test_failure_with_successful_hits_cannot_be_scored() -> None:
    with pytest.raises(ValidationError, match="failed retrieval observation cannot contain hits"):
        _observation(success=False)


@pytest.mark.parametrize("success", ("false", "true", 0, 1))
def test_success_flag_is_not_coerced_from_strings_or_numbers(success: str | int) -> None:
    payload = _observation(hits=()).model_dump() | {"success": success}
    with pytest.raises(ValidationError):
        RetrievalEvaluationObservation.model_validate(payload)


def test_empty_dataset_and_duplicate_cases_are_rejected() -> None:
    with pytest.raises(RetrievalEvaluationError, match="requires observations"):
        compute_retrieval_metrics(())
    item = _observation()
    with pytest.raises(RetrievalEvaluationError, match="record identifiers must be unique"):
        compute_retrieval_metrics((item, item))


def test_unvalidated_model_copy_cannot_bypass_input_checks() -> None:
    tampered = _observation().model_copy(update={"hit_clause_ids": ("rule", "rule", "rule")})
    with pytest.raises(ValidationError, match="unique"):
        compute_retrieval_metrics((tampered,))


def test_ndcg_uses_top_ten_and_penalizes_missing_gold() -> None:
    outside = _observation(hits=(*(f"other-{index}" for index in range(10)), "rule"))
    result = compute_retrieval_metrics((outside,))
    assert result.mrr_at_10 == result.ndcg_at_10 == 0.0
    assert result.cutoffs[-1].clause_recall == 0.5
    perfect = compute_retrieval_metrics((_observation(hits=("rule", "exception")),))
    assert perfect.ndcg_at_10 == 1.0


def test_aggregate_report_does_not_emit_identifiers_or_release_qualification() -> None:
    result = compute_retrieval_metrics((_observation(),))
    payload = result.model_dump_json()
    assert "case-1" not in payload and "exception" not in payload
    assert result.release_eligible is False
    assert result.schema_version == "retrieval_ranking_metrics/1.0.0"
    with pytest.raises(ValidationError):
        RetrievalEvaluationMetrics.model_validate(result.model_dump() | {"release_eligible": True})


@pytest.mark.parametrize("change", ("counts", "cutoffs", "ndcg"))
def test_report_rejects_inconsistent_counts_cutoffs_or_out_of_range_scores(change: str) -> None:
    payload = compute_retrieval_metrics((_observation(),)).model_dump()
    if change == "counts":
        payload["failed_count"] = 1
    elif change == "cutoffs":
        payload["cutoffs"] = []
    else:
        payload["ndcg_at_10"] = 1.3
    with pytest.raises(ValidationError):
        RetrievalEvaluationMetrics.model_validate(payload)
