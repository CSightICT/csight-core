"""Safe request and response contracts for policy clause retrieval."""

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.platform.policy_reference import ClauseType
from app.platform.policy_retrieval import (
    PolicyRetrievalResult,
    PolicySearchFilters,
    RetrievalMode,
)

MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class PolicySearchFilterRequest(BaseModel):
    model_config = MODEL_CONFIG

    policy_types: tuple[str, ...] = ()
    product_categories: tuple[str, ...] = ()
    defect_types: tuple[str, ...] = ()
    clause_types: tuple[ClauseType, ...] = ()
    actions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_allowlists(self) -> Self:
        PolicySearchFilters(
            policy_types=self.policy_types,
            product_categories=self.product_categories,
            defect_types=self.defect_types,
            clause_types=self.clause_types,
            actions=self.actions,
        )
        return self

    def to_domain(self) -> PolicySearchFilters:
        return PolicySearchFilters(
            policy_types=self.policy_types,
            product_categories=self.product_categories,
            defect_types=self.defect_types,
            clause_types=self.clause_types,
            actions=self.actions,
        )


class PolicySearchRequest(BaseModel):
    model_config = MODEL_CONFIG

    query: str = Field(min_length=2, max_length=2000)
    as_of_date: date
    mode: RetrievalMode = RetrievalMode.HYBRID
    top_k: int = Field(default=10, ge=1, le=20)
    filters: PolicySearchFilterRequest = Field(default_factory=PolicySearchFilterRequest)


class RetrievalProfileResponse(BaseModel):
    model_config = MODEL_CONFIG

    lexical: str
    embedding: str
    fusion: str
    index_version: str


class PolicySearchHitResponse(BaseModel):
    model_config = MODEL_CONFIG

    rank: int
    clause_id: str
    document_id: str
    document_version: str
    title: str
    section_path: tuple[str, ...]
    clause_type: ClauseType
    text: str
    lexical_rank: int | None
    lexical_score: float | None
    dense_rank: int | None
    dense_score: float | None
    fusion_score: float | None
    candidate_rank: int | None
    rerank_rank: int | None
    rerank_score: float | None
    reranker_profile: str | None
    effective_from: date
    effective_to: date | None
    document_status: str
    source_type: str
    requires_human_review: bool


class PolicySearchResponse(BaseModel):
    model_config = MODEL_CONFIG

    query_hash: str
    mode: RetrievalMode
    as_of_date: date
    retrieval_profile: RetrievalProfileResponse
    hits: tuple[PolicySearchHitResponse, ...]

    @classmethod
    def from_result(cls, result: PolicyRetrievalResult) -> Self:
        return cls(
            query_hash=result.query_hash,
            mode=result.mode,
            as_of_date=result.as_of_date,
            retrieval_profile=RetrievalProfileResponse(
                lexical=result.retrieval_profile.lexical.identifier,
                embedding=result.retrieval_profile.dense.identifier,
                fusion=result.retrieval_profile.fusion.identifier,
                index_version=result.retrieval_profile.index_version,
            ),
            hits=tuple(
                PolicySearchHitResponse(
                    rank=hit.rank,
                    clause_id=hit.clause.clause_id,
                    document_id=hit.clause.document_id,
                    document_version=hit.clause.document_version,
                    title=hit.clause.title,
                    section_path=hit.clause.section_path,
                    clause_type=hit.clause.clause_type,
                    text=hit.clause.text,
                    lexical_rank=hit.lexical_rank,
                    lexical_score=hit.lexical_score,
                    dense_rank=hit.dense_rank,
                    dense_score=hit.dense_score,
                    fusion_score=hit.fusion_score,
                    candidate_rank=hit.candidate_rank,
                    rerank_rank=hit.rerank_rank,
                    rerank_score=hit.rerank_score,
                    reranker_profile=hit.reranker_profile,
                    effective_from=hit.clause.effective_from,
                    effective_to=hit.clause.effective_to,
                    document_status=hit.clause.document_status.value,
                    source_type=hit.clause.source_type,
                    requires_human_review=hit.clause.requires_human_review,
                )
                for hit in result.hits
            ),
        )


__all__ = ["PolicySearchRequest", "PolicySearchResponse"]
