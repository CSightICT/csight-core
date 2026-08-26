"""Technology-neutral policy reranking contracts and validation boundaries."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.platform.errors import CSightError
from app.platform.policy_retrieval import PolicyClauseRecord, stable_json_hash

PAIR_TEMPLATE_NAME = "policy_rerank_pair"
PAIR_TEMPLATE_VERSION = "1.0.0"
DOCUMENT_TEMPLATE = (
    "문서: {title}\n섹션: {section_path}\n정책 유형: {policy_type}\n"
    "조항 유형: {clause_type}\n본문: {text}"
)


class RerankerProviderUnavailableError(CSightError):
    code = "RERANKER_PROVIDER_UNAVAILABLE"
    default_message = "The policy reranker provider is unavailable."


class RerankerProviderInvalidResponseError(CSightError):
    code = "RERANKER_PROVIDER_INVALID_RESPONSE"
    default_message = "The policy reranker returned an invalid response."


class RerankerProfileUnavailableError(CSightError):
    code = "RERANKER_PROFILE_UNAVAILABLE"
    default_message = "No active policy reranker execution profile is available."


class MockRerankerMode(StrEnum):
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    TRANSIENT_ERROR = "TRANSIENT_ERROR"
    PERMANENT_ERROR = "PERMANENT_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"
    UNKNOWN_CANDIDATE = "UNKNOWN_CANDIDATE"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class PolicyRerankerProfile(_StrictModel):
    profile_name: str = "qwen3_policy_reranker"
    profile_version: str = "1.0.0"
    provider_name: str
    model_artifact: str
    model_revision: str
    instruction: str
    instruction_hash: str
    query_template_name: str = PAIR_TEMPLATE_NAME
    query_template_version: str = PAIR_TEMPLATE_VERSION
    query_template_hash: str
    document_template_name: str = PAIR_TEMPLATE_NAME
    document_template_version: str = PAIR_TEMPLATE_VERSION
    document_template_hash: str
    max_query_tokens: int = Field(gt=0)
    max_document_tokens: int = Field(gt=0)
    max_pair_tokens: int = Field(gt=0)
    candidate_k: int = Field(gt=0, le=50)
    final_k: int = Field(gt=0, le=20)
    batch_size: int = Field(gt=0, le=50)
    device: str
    score_semantics: str

    @model_validator(mode="after")
    def validate_limits(self) -> Self:
        if self.final_k > self.candidate_k:
            raise ValueError("final_k must not exceed candidate_k")
        if self.max_query_tokens + self.max_document_tokens > self.max_pair_tokens:
            raise ValueError("query/document token budgets exceed pair token budget")
        return self

    @property
    def identifier(self) -> str:
        return f"{self.profile_name}:{self.profile_version}"

    @property
    def profile_hash(self) -> str:
        return stable_json_hash(self.model_dump(mode="json"))


class PolicyRetrievalExecutionProfile(_StrictModel):
    profile_name: str
    profile_version: str
    base_index_version: str
    candidate_mode: str
    candidate_k: int = Field(gt=0, le=50)
    final_k: int = Field(gt=0, le=20)
    status: str
    profile_hash: str
    reranker: PolicyRerankerProfile

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        if self.candidate_mode != "HYBRID_RRF":
            raise ValueError("reranker candidate mode must be HYBRID_RRF")
        if self.candidate_k != self.reranker.candidate_k:
            raise ValueError("execution and reranker candidate_k differ")
        if self.final_k != self.reranker.final_k:
            raise ValueError("execution and reranker final_k differ")
        if self.status != "ACTIVE":
            raise ValueError("execution profile is not active")
        return self

    @property
    def identifier(self) -> str:
        return f"{self.profile_name}:{self.profile_version}"


class RerankCandidate(_StrictModel):
    candidate_id: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=50_000)
    original_rank: int = Field(gt=0)


class PolicyRerankRequest(_StrictModel):
    query: str = Field(min_length=2, max_length=2000)
    candidates: tuple[RerankCandidate, ...] = Field(min_length=1, max_length=50)
    profile: PolicyRerankerProfile

    @model_validator(mode="after")
    def validate_candidate_ids(self) -> Self:
        candidate_ids = tuple(value.candidate_id for value in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("rerank request contains duplicate candidate IDs")
        if tuple(value.original_rank for value in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("candidate original ranks must be contiguous")
        return self


class RerankScore(_StrictModel):
    candidate_id: str
    original_rank: int = Field(gt=0)
    rerank_rank: int = Field(gt=0)
    rerank_score: float

    @model_validator(mode="after")
    def validate_score(self) -> Self:
        if not math.isfinite(self.rerank_score):
            raise ValueError("reranker score must be finite")
        return self


class PolicyRerankResult(_StrictModel):
    model: str
    model_revision: str
    profile_version: str
    scores: tuple[RerankScore, ...]
    latency_ms: float = Field(ge=0)


def serialize_rerank_document(clause: PolicyClauseRecord) -> str:
    """Serialize filtered clause content without tenant or internal database IDs."""

    return DOCUMENT_TEMPLATE.format(
        title=clause.title,
        section_path=" > ".join(clause.section_path),
        policy_type=clause.policy_type,
        clause_type=clause.clause_type.value,
        text=clause.text,
    )


def validate_rerank_result(
    *, request: PolicyRerankRequest, result: PolicyRerankResult
) -> tuple[RerankScore, ...]:
    """Enforce the candidate allowlist and immutable set before using model output."""

    expected = {value.candidate_id: value.original_rank for value in request.candidates}
    received_ids = tuple(value.candidate_id for value in result.scores)
    if len(received_ids) != len(set(received_ids)):
        raise RerankerProviderInvalidResponseError("Duplicate candidate in reranker response.")
    if frozenset(received_ids) != frozenset(expected):
        raise RerankerProviderInvalidResponseError("Reranker candidate allowlist mismatch.")
    if tuple(sorted(value.rerank_rank for value in result.scores)) != tuple(
        range(1, len(expected) + 1)
    ):
        raise RerankerProviderInvalidResponseError("Reranker ranks are invalid.")
    for value in result.scores:
        if expected[value.candidate_id] != value.original_rank:
            raise RerankerProviderInvalidResponseError("Original candidate rank changed.")
        if not 0.0 <= value.rerank_score <= 1.0:
            raise RerankerProviderInvalidResponseError("Reranker score is out of range.")
    return tuple(sorted(result.scores, key=lambda value: value.rerank_rank))


__all__ = [
    "DOCUMENT_TEMPLATE",
    "PAIR_TEMPLATE_NAME",
    "PAIR_TEMPLATE_VERSION",
    "MockRerankerMode",
    "PolicyRerankRequest",
    "PolicyRerankResult",
    "PolicyRerankerProfile",
    "PolicyRetrievalExecutionProfile",
    "RerankCandidate",
    "RerankScore",
    "RerankerProfileUnavailableError",
    "RerankerProviderInvalidResponseError",
    "RerankerProviderUnavailableError",
    "serialize_rerank_document",
    "validate_rerank_result",
]
