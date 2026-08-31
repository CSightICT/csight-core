"""Technology-neutral policy query-plan and multi-query fusion contracts."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.platform.analysis.enums import ExtractionIssueType
from app.platform.analysis.llm_v2 import CompletenessResult, LLMTextExtractionResultV2
from app.platform.analysis.models import ProviderExecutionMetadata
from app.platform.errors import CSightError
from app.platform.policy_reference import POLICY_TYPES, ClauseType
from app.platform.policy_retrieval import (
    POLICY_SIMILARITY_REFERENCE_THRESHOLD,
    PRODUCT_CATEGORIES,
    PolicySearchHit,
)


class PolicyQueryBuilderProviderUnavailableError(CSightError):
    code = "POLICY_QUERY_BUILDER_PROVIDER_UNAVAILABLE"
    default_message = "The policy query builder provider is unavailable."


class PolicyQueryBuilderTimeoutError(CSightError):
    code = "POLICY_QUERY_BUILDER_TIMEOUT"
    default_message = "The policy query builder provider timed out."


class PolicyQueryBuilderInvalidOutputError(CSightError):
    code = "POLICY_QUERY_BUILDER_INVALID_OUTPUT"
    default_message = "The policy query builder returned invalid output."


class QueryStrategy(StrEnum):
    RAW = "RAW"
    DETERMINISTIC = "DETERMINISTIC"
    LLM = "LLM"


class PolicyQueryPurpose(StrEnum):
    PRIMARY_POLICY = "PRIMARY_POLICY"
    EVIDENCE_REQUIREMENT = "EVIDENCE_REQUIREMENT"
    EXCEPTION = "EXCEPTION"
    ESCALATION = "ESCALATION"
    DEFINITION = "DEFINITION"
    PROCEDURE = "PROCEDURE"


class RetrievalRunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class QueryFilterHints(_StrictModel):
    """Validated soft hints. Core-owned hard filters deliberately do not exist here."""

    policy_types: tuple[str, ...] = Field(default=(), max_length=10)
    product_categories: tuple[str, ...] = Field(default=(), max_length=10)
    defect_types: tuple[ExtractionIssueType, ...] = Field(default=(), max_length=20)
    clause_types: tuple[ClauseType, ...] = Field(default=(), max_length=6)

    @model_validator(mode="after")
    def validate_allowlists_and_sets(self) -> Self:
        if any(value not in POLICY_TYPES for value in self.policy_types):
            raise ValueError("unsupported policy type hint")
        if any(value not in PRODUCT_CATEGORIES for value in self.product_categories):
            raise ValueError("unsupported product category hint")
        for values, name in (
            (self.policy_types, "policy_types"),
            (self.product_categories, "product_categories"),
            (self.defect_types, "defect_types"),
            (self.clause_types, "clause_types"),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must not contain duplicates")
        return self


class PolicyQuery(_StrictModel):
    query_id: str = Field(pattern=r"^Q[1-3]$")
    purpose: PolicyQueryPurpose
    text: str = Field(min_length=1, max_length=2_000)


class PolicyQueryPlan(_StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    queries: tuple[PolicyQuery, ...] = Field(min_length=1, max_length=3)
    filter_hints: QueryFilterHints = QueryFilterHints()
    unresolved_terms: tuple[str, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def validate_unique_queries(self) -> Self:
        identifiers = [item.query_id for item in self.queries]
        texts = [" ".join(item.text.casefold().split()) for item in self.queries]
        if identifiers != [f"Q{index}" for index in range(1, len(identifiers) + 1)]:
            raise ValueError("query identifiers must be contiguous and stable")
        if len(set(texts)) != len(texts):
            raise ValueError("query text must not contain duplicates")
        if len(set(self.unresolved_terms)) != len(self.unresolved_terms):
            raise ValueError("unresolved_terms must not contain duplicates")
        return self

    @property
    def content_hash(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


class TrustedCaseMetadata(_StrictModel):
    product_category: str
    days_since_purchase: int | None = Field(default=None, ge=0, le=3650)
    available_image_count: int = Field(default=0, ge=0, le=1000)
    exception_context: bool = False
    escalation_context: bool = False

    @field_validator("product_category")
    @classmethod
    def validate_product_category(cls, value: str) -> str:
        if value not in PRODUCT_CATEGORIES:
            raise ValueError("unsupported trusted product category")
        return value


class PolicyQueryBuilderInput(_StrictModel):
    extraction: LLMTextExtractionResultV2
    completeness: CompletenessResult
    trusted_metadata: TrustedCaseMetadata


class PolicyQueryBuilderResponse(_StrictModel):
    plan: PolicyQueryPlan
    metadata: ProviderExecutionMetadata


class MultiQueryFusionProfile(_StrictModel):
    name: Literal["policy_multi_query_rrf"] = "policy_multi_query_rrf"
    version: Literal["1.0.0"] = "1.0.0"
    rrf_k: int = Field(default=20, gt=0)
    query_weight: float = Field(default=1.0, gt=0)

    @property
    def identifier(self) -> str:
        return f"{self.name}:{self.version}"


class QueryRank(_StrictModel):
    query_id: str
    rank: int = Field(gt=0)


class MultiQueryHit(_StrictModel):
    hit: PolicySearchHit
    rank: int = Field(gt=0)
    fusion_score: float = Field(gt=0)
    best_query_rank: int = Field(gt=0)
    matched_query_ids: tuple[str, ...]
    per_query_ranks: tuple[QueryRank, ...]


POLICY_SIMILARITY_THRESHOLD_VERSION = "policy_similarity_reference/1.0.0"


class PolicySimilarityGroup(StrEnum):
    NEAREST = "NEAREST"
    LEAST = "LEAST"


class PolicySimilarityDiagnostic(_StrictModel):
    """Display-only cosine evidence; it never approves or rejects a case."""

    hit: PolicySearchHit
    group: PolicySimilarityGroup
    rank: int = Field(ge=1, le=3)
    cosine_similarity: float = Field(ge=-1.0, le=1.0)
    reference_threshold: float = Field(
        default=POLICY_SIMILARITY_REFERENCE_THRESHOLD,
        ge=-1.0,
        le=1.0,
    )
    threshold_version: Literal["policy_similarity_reference/1.0.0"] = (
        POLICY_SIMILARITY_THRESHOLD_VERSION
    )
    matched_query_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]


def build_policy_similarity_diagnostics(
    *,
    nearest_results: tuple[tuple[str, tuple[PolicySearchHit, ...]], ...],
    least_results: tuple[tuple[str, tuple[PolicySearchHit, ...]], ...],
) -> tuple[PolicySimilarityDiagnostic, ...]:
    """Deduplicate multi-query dense evidence into stable nearest/least groups."""

    def score(hit: PolicySearchHit) -> float:
        return hit.dense_score if hit.dense_score is not None else -1.0

    def collect(
        results: tuple[tuple[str, tuple[PolicySearchHit, ...]], ...],
    ) -> dict[tuple[str, str, str, str], tuple[PolicySearchHit, set[str]]]:
        grouped: dict[tuple[str, str, str, str], tuple[PolicySearchHit, set[str]]] = {}
        for query_id, hits in results:
            for hit in hits:
                existing = grouped.get(hit.clause.dedupe_key)
                if existing is None:
                    grouped[hit.clause.dedupe_key] = (hit, {query_id})
                    continue
                selected, query_ids = existing
                query_ids.add(query_id)
                if score(hit) > score(selected):
                    grouped[hit.clause.dedupe_key] = (hit, query_ids)
        return grouped

    nearest = collect(nearest_results)
    least = collect(least_results)
    nearest_items = sorted(
        nearest.values(),
        key=lambda item: (
            abs(score(item[0]) - POLICY_SIMILARITY_REFERENCE_THRESHOLD),
            -score(item[0]),
            item[0].clause.document_id,
            item[0].clause.clause_id,
        ),
    )[:3]
    nearest_keys = {item[0].clause.dedupe_key for item in nearest_items}
    least_items = sorted(
        (item for key, item in least.items() if key not in nearest_keys),
        key=lambda item: (
            score(item[0]),
            item[0].clause.document_id,
            item[0].clause.clause_id,
        ),
    )[:3]

    diagnostics: list[PolicySimilarityDiagnostic] = []
    for group, items in (
        (PolicySimilarityGroup.NEAREST, nearest_items),
        (PolicySimilarityGroup.LEAST, least_items),
    ):
        for rank, (hit, query_ids) in enumerate(items, start=1):
            if group is PolicySimilarityGroup.NEAREST:
                reasons = (
                    "ABOVE_REFERENCE_THRESHOLD"
                    if score(hit) >= POLICY_SIMILARITY_REFERENCE_THRESHOLD
                    else "BELOW_REFERENCE_THRESHOLD",
                )
            else:
                reasons = ("LOWEST_COSINE_SIMILARITY", "POLICY_CONTEXT_MISMATCH")
            diagnostics.append(
                PolicySimilarityDiagnostic(
                    hit=hit,
                    group=group,
                    rank=rank,
                    cosine_similarity=score(hit),
                    matched_query_ids=tuple(sorted(query_ids)),
                    reason_codes=reasons,
                )
            )
    return tuple(diagnostics)


def fuse_multi_query_hits(
    *,
    results: tuple[tuple[str, tuple[PolicySearchHit, ...]], ...],
    profile: MultiQueryFusionProfile | None = None,
    top_k: int,
) -> tuple[MultiQueryHit, ...]:
    """Fuse fixed HYBRID result lists with deterministic, version-aware RRF."""

    profile = profile or MultiQueryFusionProfile()
    grouped: dict[tuple[str, str, str, str], list[tuple[str, int, PolicySearchHit]]] = {}
    for query_id, hits in results:
        for rank, hit in enumerate(hits, start=1):
            grouped.setdefault(hit.clause.dedupe_key, []).append((query_id, rank, hit))
    scored: list[tuple[float, int, str, str, str, list[tuple[str, int, PolicySearchHit]]]] = []
    for (_tenant, document_id, version, clause_id), values in grouped.items():
        score = sum(profile.query_weight / (profile.rrf_k + rank) for _, rank, _ in values)
        if not math.isfinite(score):
            raise ValueError("multi-query fusion produced a non-finite score")
        scored.append(
            (score, min(rank for _, rank, _ in values), document_id, version, clause_id, values)
        )
    scored.sort(key=lambda item: (-item[0], item[1], item[2], item[3], item[4]))
    return tuple(
        MultiQueryHit(
            hit=values[0][2],
            rank=rank,
            fusion_score=score,
            best_query_rank=best_rank,
            matched_query_ids=tuple(query_id for query_id, _, _ in sorted(values)),
            per_query_ranks=tuple(
                QueryRank(query_id=query_id, rank=query_rank)
                for query_id, query_rank, _ in sorted(values)
            ),
        )
        for rank, (score, best_rank, _document, _version, _clause, values) in enumerate(
            scored[:top_k], start=1
        )
    )


class PolicyRetrievalRun(_StrictModel):
    id: str
    tenant_id: str
    case_id: str
    analysis_run_id: str
    text_result_id: str
    strategy: QueryStrategy
    status: RetrievalRunStatus
    as_of_date: date
    top_k: int = Field(gt=0, le=50)
    idempotency_key: str
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    correlation_id: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None


__all__ = [
    "MultiQueryFusionProfile",
    "MultiQueryHit",
    "PolicyQuery",
    "PolicyQueryBuilderInput",
    "PolicyQueryBuilderInvalidOutputError",
    "PolicyQueryBuilderProviderUnavailableError",
    "PolicyQueryBuilderResponse",
    "PolicyQueryBuilderTimeoutError",
    "PolicyQueryPlan",
    "PolicyQueryPurpose",
    "PolicyRetrievalRun",
    "PolicySimilarityDiagnostic",
    "PolicySimilarityGroup",
    "QueryFilterHints",
    "QueryStrategy",
    "RetrievalRunStatus",
    "TrustedCaseMetadata",
    "build_policy_similarity_diagnostics",
    "fuse_multi_query_hits",
]
