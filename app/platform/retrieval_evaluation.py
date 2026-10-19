"""Pure, versioned ranking diagnostics; no model or release qualification authority.

Hit rate counts cases with any relevant hit. Clause recall counts the fraction of
each case's Gold clauses retrieved. All aggregate metrics are macro case means,
including failed cases, and must not be substituted for historical frozen gates.
"""

from __future__ import annotations

import math
import statistics
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RETRIEVAL_CUTOFFS = (1, 3, 5, 10, 20)


class RetrievalEvaluationError(ValueError):
    """Ranking input cannot establish a valid evaluation denominator or order."""


class _Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, hide_input_in_errors=True, revalidate_instances="always"
    )


class RetrievalEvaluationObservation(_Contract):
    record_id: str = Field(min_length=1, max_length=512)
    relevant_clause_ids: tuple[str, ...] = Field(min_length=1)
    hit_clause_ids: tuple[str, ...]
    success: bool = Field(default=True, strict=True)

    @field_validator("record_id")
    @classmethod
    def require_record_identifier(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("record identifier must be nonempty and unpadded")
        return value

    @field_validator("relevant_clause_ids", "hit_clause_ids")
    @classmethod
    def require_unique_identifiers(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() or value != value.strip() for value in values):
            raise ValueError("clause identifiers must be nonempty and unpadded")
        if len(values) != len(set(values)):
            raise ValueError("clause identifiers must be unique")
        return values

    @model_validator(mode="after")
    def require_failed_case_without_hits(self) -> RetrievalEvaluationObservation:
        if not self.success and self.hit_clause_ids:
            raise ValueError("failed retrieval observation cannot contain hits")
        return self


class RetrievalCutoffMetrics(_Contract):
    cutoff: Literal[1, 3, 5, 10, 20]
    hit_rate: float = Field(ge=0, le=1)
    clause_recall: float = Field(ge=0, le=1)
    exact_gold_coverage: float = Field(ge=0, le=1)


class RetrievalEvaluationMetrics(_Contract):
    schema_version: Literal["retrieval_ranking_metrics/1.0.0"] = "retrieval_ranking_metrics/1.0.0"
    aggregation: Literal["MACRO_CASE_MEAN_FAILURES_INCLUDED"] = "MACRO_CASE_MEAN_FAILURES_INCLUDED"
    record_count: int = Field(gt=0)
    success_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    cutoffs: tuple[RetrievalCutoffMetrics, ...]
    mrr_at_10: float = Field(ge=0, le=1)
    ndcg_at_10: float = Field(ge=0, le=1)
    zero_result_rate: float = Field(ge=0, le=1)
    release_eligible: Literal[False] = False

    @model_validator(mode="after")
    def require_complete_contract(self) -> RetrievalEvaluationMetrics:
        if self.success_count + self.failed_count != self.record_count:
            raise ValueError("retrieval counts must include every observation exactly once")
        if tuple(item.cutoff for item in self.cutoffs) != RETRIEVAL_CUTOFFS:
            raise ValueError("retrieval cutoffs must be exactly 1, 3, 5, 10, 20 in order")
        return self


def compute_retrieval_metrics(
    observations: tuple[RetrievalEvaluationObservation, ...],
) -> RetrievalEvaluationMetrics:
    """Score known-Gold rankings, rejecting malformed evidence rather than repairing it.

    Empty Gold belongs to a separately specified no-answer evaluation, not this
    contract. Duplicate ranked hits are rejected, never silently deduplicated.
    Input identifiers stay in memory; the report contains aggregate metrics only.
    """
    if not observations:
        raise RetrievalEvaluationError("retrieval evaluation requires observations")
    # Revalidate copied/constructed Pydantic instances as well as ordinary inputs.
    checked = tuple(RetrievalEvaluationObservation.model_validate(item) for item in observations)
    if len({item.record_id for item in checked}) != len(checked):
        raise RetrievalEvaluationError("retrieval record identifiers must be unique")

    cutoffs: list[RetrievalCutoffMetrics] = []
    for cutoff in RETRIEVAL_CUTOFFS:
        hits: list[float] = []
        recalls: list[float] = []
        coverage: list[float] = []
        for item in checked:
            relevant = frozenset(item.relevant_clause_ids)
            matched = len(relevant.intersection(item.hit_clause_ids[:cutoff]))
            hits.append(float(matched > 0))
            recalls.append(matched / len(relevant))
            coverage.append(float(matched == len(relevant)))
        cutoffs.append(
            RetrievalCutoffMetrics(
                cutoff=cutoff,
                hit_rate=round(statistics.fmean(hits), 6),
                clause_recall=round(statistics.fmean(recalls), 6),
                exact_gold_coverage=round(statistics.fmean(coverage), 6),
            )
        )

    reciprocals: list[float] = []
    ndcg_values: list[float] = []
    for item in checked:
        relevant = frozenset(item.relevant_clause_ids)
        ranks = tuple(
            rank
            for rank, clause_id in enumerate(item.hit_clause_ids[:10], start=1)
            if clause_id in relevant
        )
        reciprocals.append(1 / ranks[0] if ranks else 0.0)
        dcg = sum(1 / math.log2(rank + 1) for rank in ranks)
        ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(10, len(relevant)) + 1))
        ndcg_values.append(dcg / ideal)

    success_count = sum(item.success for item in checked)
    return RetrievalEvaluationMetrics(
        record_count=len(checked),
        success_count=success_count,
        failed_count=len(checked) - success_count,
        cutoffs=tuple(cutoffs),
        mrr_at_10=round(statistics.fmean(reciprocals), 6),
        ndcg_at_10=round(statistics.fmean(ndcg_values), 6),
        zero_result_rate=round(
            statistics.fmean(float(not item.hit_clause_ids) for item in checked), 6
        ),
    )
