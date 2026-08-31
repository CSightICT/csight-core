"""Technology-neutral contracts for versioned policy retrieval.

This module deliberately contains no web, database, HTTP client, or model-runtime
imports. Retrieval returns reference clauses only; it never decides a case.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.platform.errors import CSightError
from app.platform.policy_reference import (
    DEFECT_TYPES,
    POLICY_TYPES,
)
from app.platform.policy_reference import (
    ClauseType as PolicyClauseType,
)
from app.platform.policy_reference import (
    DocumentStatus as PolicyDocumentStatus,
)

POLICY_ACTIONS = frozenset({"REVIEW"})
PRODUCT_CATEGORIES = frozenset({"GENERAL"})
POLICY_SIMILARITY_REFERENCE_THRESHOLD = 0.65


class EmbeddingProviderUnavailableError(CSightError):
    code = "EMBEDDING_PROVIDER_UNAVAILABLE"
    default_message = "The embedding provider is unavailable."


class PolicyDocumentVersionContentMismatchError(CSightError):
    code = "POLICY_DOCUMENT_VERSION_CONTENT_MISMATCH"
    default_message = "The immutable policy document version has different content."


class PolicyIndexUnavailableError(CSightError):
    code = "POLICY_INDEX_UNAVAILABLE"
    default_message = "No active policy retrieval index is available."


class RetrievalMode(StrEnum):
    LEXICAL = "LEXICAL"
    DENSE = "DENSE"
    HYBRID = "HYBRID"
    HYBRID_RERANKED = "HYBRID_RERANKED"


class PolicyIngestionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class PolicyIndexStatus(StrEnum):
    BUILDING = "BUILDING"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"
    RETIRED = "RETIRED"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class PolicySearchFilters(_StrictModel):
    policy_types: tuple[str, ...] = ()
    product_categories: tuple[str, ...] = ()
    defect_types: tuple[str, ...] = ()
    clause_types: tuple[PolicyClauseType, ...] = ()
    actions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_allowlists(self) -> Self:
        if any(value not in POLICY_TYPES for value in self.policy_types):
            raise ValueError("unsupported policy_type filter")
        if any(value not in PRODUCT_CATEGORIES for value in self.product_categories):
            raise ValueError("unsupported product_category filter")
        if any(value not in DEFECT_TYPES for value in self.defect_types):
            raise ValueError("unsupported defect_type filter")
        if any(value not in POLICY_ACTIONS for value in self.actions):
            raise ValueError("unsupported action filter")
        return self

    @property
    def count(self) -> int:
        return sum(
            len(values)
            for values in (
                self.policy_types,
                self.product_categories,
                self.defect_types,
                self.clause_types,
                self.actions,
            )
        )


class PolicySearchQuery(_StrictModel):
    tenant_id: str = Field(min_length=1)
    query: str = Field(min_length=2, max_length=2000)
    as_of_date: date
    mode: RetrievalMode = RetrievalMode.HYBRID
    # Internal evaluation may inspect a larger candidate pool. The public HTTP
    # contract keeps its independent top_k <= 20 boundary.
    top_k: int = Field(default=10, ge=1, le=50)
    least_similar_k: int = Field(default=0, ge=0, le=3)
    filters: PolicySearchFilters = Field(default_factory=PolicySearchFilters)

    @property
    def query_hash(self) -> str:
        return hashlib.sha256(self.query.encode("utf-8")).hexdigest()


class PolicyClauseRecord(_StrictModel):
    row_id: str
    tenant_id: str
    document_id: str
    document_version: str
    title: str
    clause_id: str
    section_path: tuple[str, ...]
    clause_type: PolicyClauseType
    text: str
    parent_clause_id: str | None = None
    policy_type: str
    product_categories: tuple[str, ...]
    defect_types: tuple[str, ...]
    actions: tuple[str, ...]
    requires_human_review: bool
    effective_from: date
    effective_to: date | None
    document_status: PolicyDocumentStatus
    source_type: str
    source_hash: str

    @property
    def dedupe_key(self) -> tuple[str, str, str, str]:
        return (self.tenant_id, self.document_id, self.document_version, self.clause_id)


class PolicySearchHit(_StrictModel):
    clause: PolicyClauseRecord
    lexical_rank: int | None = None
    lexical_score: float | None = None
    dense_rank: int | None = None
    dense_score: float | None = None
    fusion_rank: int | None = None
    fusion_score: float | None = None
    candidate_rank: int | None = None
    rerank_rank: int | None = None
    rerank_score: float | None = None
    reranker_profile: str | None = None

    @property
    def rank(self) -> int:
        return self.rerank_rank or self.fusion_rank or self.lexical_rank or self.dense_rank or 0


class LexicalProfile(_StrictModel):
    name: str = "ko_policy_lexical"
    version: str = "1.0.0"
    normalization_version: str = "nfkc-lower-v1"
    tokenizer_version: str = "ko-policy-tokenizer-v1"
    stopword_version: str = "minimal-v1"
    ngram_version: str = "hangul-bigram-v1"
    k1: float = Field(default=1.2, gt=0)
    b: float = Field(default=0.75, ge=0, le=1)

    @property
    def identifier(self) -> str:
        return f"{self.name}:{self.version}"


class DenseProfile(_StrictModel):
    name: str = "qwen3_embedding_0.6b"
    version: str = "1.0.0"
    provider_name: str = "host_sentence_transformers"
    model_artifact: str
    model_revision: str
    embedding_dimension: int = Field(gt=0)
    pooling_strategy: str
    normalize_embeddings: bool = True
    query_instruction: str
    max_query_tokens: int = Field(gt=0)
    max_document_tokens: int = Field(gt=0)
    document_template_name: str = "policy_clause_passage"
    document_template_version: str = "1.0.0"

    @property
    def identifier(self) -> str:
        return f"{self.name}:{self.version}"


class HybridFusionProfile(_StrictModel):
    name: str = "policy_rrf"
    version: str = "1.0.0"
    rrf_k: int = Field(default=60, gt=0)
    lexical_weight: float = Field(default=1.0, gt=0)
    dense_weight: float = Field(default=1.0, gt=0)

    @property
    def identifier(self) -> str:
        return f"{self.name}:{self.version}"


class PolicyRetrievalProfile(_StrictModel):
    lexical: LexicalProfile
    dense: DenseProfile
    fusion: HybridFusionProfile
    embedding_profile_id: str
    index_version: str


class PolicyRetrievalResult(_StrictModel):
    query_hash: str
    mode: RetrievalMode
    as_of_date: date
    retrieval_profile: PolicyRetrievalProfile
    hits: tuple[PolicySearchHit, ...]
    nearest_dense_hits: tuple[PolicySearchHit, ...] = ()
    least_similar_hits: tuple[PolicySearchHit, ...] = ()
    latency_ms: float = Field(ge=0)


class EmbeddingVector(_StrictModel):
    values: tuple[float, ...]
    model: str
    model_revision: str
    normalized: bool
    token_count: int | None = None
    truncated: bool = False

    @model_validator(mode="after")
    def validate_vector(self) -> Self:
        if not self.values:
            raise ValueError("embedding vector must not be empty")
        if any(not math.isfinite(value) for value in self.values):
            raise ValueError("embedding vector contains NaN or infinity")
        norm = math.sqrt(sum(value * value for value in self.values))
        if self.normalized and not math.isclose(norm, 1.0, rel_tol=5e-3, abs_tol=5e-3):
            raise ValueError("normalized embedding must have unit norm")
        return self

    @property
    def dimension(self) -> int:
        return len(self.values)


class PolicyIngestionRun(_StrictModel):
    id: str
    corpus_name: str
    corpus_version: str
    corpus_source_hash: str
    manifest_hash: str
    status: PolicyIngestionStatus
    expected_document_count: int
    ingested_document_count: int
    expected_clause_count: int
    ingested_clause_count: int
    builder_version: str
    schema_version: str
    started_at: datetime
    completed_at: datetime | None = None
    failure_code: str | None = None


class PolicyEmbeddingProfile(_StrictModel):
    id: str
    profile: DenseProfile
    query_instruction_hash: str
    document_template_hash: str


class PolicyIndexVersion(_StrictModel):
    id: str
    tenant_id: str
    index_name: str
    index_version: str
    status: PolicyIndexStatus
    embedding_profile_id: str
    expected_clause_count: int
    indexed_clause_count: int
    activated_at: datetime | None = None


def stable_json_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def serialize_policy_clause(clause: PolicyClauseRecord) -> str:
    """Serialize one passage under the immutable policy_clause_passage:1.0.0 contract."""

    return "\n".join(
        (
            f"문서: {clause.title}",
            f"섹션: {' > '.join(clause.section_path)}",
            f"정책 유형: {clause.policy_type}",
            f"조항 유형: {clause.clause_type.value}",
            f"본문: {clause.text}",
        )
    )


__all__ = [
    "DenseProfile",
    "EmbeddingProviderUnavailableError",
    "EmbeddingVector",
    "HybridFusionProfile",
    "LexicalProfile",
    "PolicyClauseRecord",
    "PolicyClauseType",
    "PolicyDocumentStatus",
    "PolicyDocumentVersionContentMismatchError",
    "PolicyEmbeddingProfile",
    "PolicyIndexStatus",
    "PolicyIndexUnavailableError",
    "PolicyIndexVersion",
    "PolicyIngestionRun",
    "PolicyIngestionStatus",
    "PolicyRetrievalProfile",
    "PolicyRetrievalResult",
    "PolicySearchFilters",
    "PolicySearchHit",
    "PolicySearchQuery",
    "RetrievalMode",
    "serialize_policy_clause",
    "stable_json_hash",
]
