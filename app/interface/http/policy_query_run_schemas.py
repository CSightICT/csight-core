"""HTTP-only schemas for asynchronous Case-to-policy retrieval runs."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.platform.query_builder import PolicyRetrievalRun, QueryStrategy
from app.ports.policy_query_runs import PolicyRetrievalRunDetail


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartPolicyRetrievalRunRequest(_Schema):
    analysis_run_id: str = Field(min_length=1)
    strategy: QueryStrategy = QueryStrategy.RAW
    as_of_date: date
    top_k: int = Field(default=3, ge=1, le=20)


class PolicyRetrievalRunResponse(_Schema):
    id: str
    case_id: str
    analysis_run_id: str
    strategy: QueryStrategy
    status: str
    as_of_date: date
    top_k: int
    correlation_id: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None
    failure_message: str | None

    @classmethod
    def from_run(cls, run: PolicyRetrievalRun) -> "PolicyRetrievalRunResponse":
        return cls(
            **run.model_dump(
                exclude={"tenant_id", "text_result_id", "idempotency_key", "request_hash"}
            )
        )


class PolicyRetrievalRunListResponse(_Schema):
    items: tuple[PolicyRetrievalRunResponse, ...]


class PolicyRetrievalRunDetailResponse(_Schema):
    run: PolicyRetrievalRunResponse
    query_plan: dict[str, object] | None
    retrieval_profile: dict[str, object]
    hits: tuple[dict[str, object], ...]

    @classmethod
    def from_detail(cls, detail: PolicyRetrievalRunDetail) -> "PolicyRetrievalRunDetailResponse":
        return cls(
            run=PolicyRetrievalRunResponse.from_run(detail.run),
            query_plan=(detail.query_plan.model_dump(mode="json") if detail.query_plan else None),
            retrieval_profile={
                "base_mode": "HYBRID",
                "index_version": detail.index_version,
                "base_retrieval_profile_hash": detail.base_retrieval_profile_hash,
                "multi_query_fusion": detail.multi_query_fusion_profile,
                "reranker_enabled": False,
            },
            hits=tuple(
                {
                    "rank": hit.rank,
                    "clause_id": hit.hit.clause.clause_id,
                    "document_id": hit.hit.clause.document_id,
                    "document_version": hit.hit.clause.document_version,
                    "fusion_score": hit.fusion_score,
                    "best_query_rank": hit.best_query_rank,
                    "matched_query_ids": list(hit.matched_query_ids),
                    "per_query_ranks": [
                        value.model_dump(mode="json") for value in hit.per_query_ranks
                    ],
                }
                for hit in detail.hits
            ),
        )


__all__ = [
    "PolicyRetrievalRunDetailResponse",
    "PolicyRetrievalRunListResponse",
    "PolicyRetrievalRunResponse",
    "StartPolicyRetrievalRunRequest",
]
