"""Technology-neutral citation-pack and grounded-explanation contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.analysis.models import ProviderExecutionMetadata
from app.platform.errors import CSightError
from app.platform.policy_reference import ClauseType
from app.platform.query_builder import QueryStrategy


class GroundedExplanationProviderUnavailableError(CSightError):
    code = "GROUNDED_EXPLANATION_PROVIDER_UNAVAILABLE"
    default_message = "The grounded-explanation provider is unavailable."


class GroundedExplanationTimeoutError(CSightError):
    code = "GROUNDED_EXPLANATION_TIMEOUT"
    default_message = "The grounded-explanation provider timed out."


class GroundedExplanationInvalidOutputError(CSightError):
    code = "GROUNDED_EXPLANATION_INVALID_OUTPUT"
    default_message = "The grounded explanation failed structural validation."


class CitationAllowlistViolationError(CSightError):
    code = "CITATION_ALLOWLIST_VIOLATION"
    default_message = "The grounded explanation cited a reference outside its citation pack."


class GroundedExplanationRunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CitationSnapshot(_StrictModel):
    """Immutable policy-clause evidence as observed by one retrieval run."""

    citation_id: str = Field(pattern=r"^CIT-[0-9]{3}$")
    rank: int = Field(gt=0, le=999)
    policy_clause_row_id: str
    policy_clause_id: str
    document_id: str
    document_version: str
    title: str
    section_path: tuple[str, ...] = Field(min_length=1)
    clause_type: ClauseType
    text: str = Field(min_length=1, max_length=20_000, repr=False)
    effective_from: date
    effective_to: date | None
    source_type: str
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieval_mode: Literal["HYBRID"] = "HYBRID"
    query_strategy: QueryStrategy
    matched_query_ids: tuple[str, ...] = Field(min_length=1, max_length=3)
    retrieval_profile_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        if len(set(self.matched_query_ids)) != len(self.matched_query_ids):
            raise ValueError("matched_query_ids must not contain duplicates")
        return self


class CitationPack(_StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    tenant_id: str
    case_id: str
    retrieval_run_id: str
    retrieval_profile_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    citations: tuple[CitationSnapshot, ...] = Field(min_length=1, max_length=50)
    created_at: datetime

    @model_validator(mode="after")
    def validate_identity_and_order(self) -> Self:
        expected_ids = [f"CIT-{index:03d}" for index in range(1, len(self.citations) + 1)]
        if [item.citation_id for item in self.citations] != expected_ids:
            raise ValueError("citation identifiers must be contiguous and rank ordered")
        if [item.rank for item in self.citations] != list(range(1, len(self.citations) + 1)):
            raise ValueError("citation ranks must be contiguous and stable")
        if any(
            item.retrieval_profile_hash != self.retrieval_profile_hash for item in self.citations
        ):
            raise ValueError("citation retrieval profile must match the pack")
        return self

    @property
    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"id", "created_at"})
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


class GroundedPolicyStatement(_StrictModel):
    statement_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    text: str = Field(min_length=1, max_length=2_000)
    citation_ids: tuple[str, ...] = Field(min_length=1, max_length=20)
    support_status: Literal["SUPPORTED"] = "SUPPORTED"

    @field_validator("citation_ids", mode="before")
    @classmethod
    def normalize_duplicate_citations(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        return tuple(dict.fromkeys(value))


class UnresolvedPolicyCondition(_StrictModel):
    condition: str = Field(min_length=1, max_length=2_000)
    required_evidence: str = Field(min_length=1, max_length=128)


class GroundedPolicyExplanation(_StrictModel):
    """Decision-free output. Extra fields, including decision fields, fail closed."""

    schema_version: Literal["1.0"] = "1.0"
    summary: Literal["현재 검색된 정책 근거를 기준으로 확인할 항목을 정리했습니다."] = (
        "현재 검색된 정책 근거를 기준으로 확인할 항목을 정리했습니다."
    )
    policy_statements: tuple[GroundedPolicyStatement, ...] = Field(max_length=50)
    unresolved_conditions: tuple[UnresolvedPolicyCondition, ...] = Field(max_length=50)

    @model_validator(mode="after")
    def validate_statement_identity(self) -> Self:
        identifiers = [item.statement_id for item in self.policy_statements]
        if identifiers != [f"S{index}" for index in range(1, len(identifiers) + 1)]:
            raise ValueError("statement identifiers must be contiguous and stable")
        return self


class GroundedExplanationInput(_StrictModel):
    case_summary: str = Field(min_length=1, max_length=2_000, repr=False)
    citation_pack: CitationPack


class GroundedExplanationResponse(_StrictModel):
    explanation: GroundedPolicyExplanation
    metadata: ProviderExecutionMetadata


class GroundingValidationMetrics(_StrictModel):
    statement_count: int = Field(ge=0)
    cited_statement_count: int = Field(ge=0)
    citation_reference_count: int = Field(ge=0)
    unique_citation_count: int = Field(ge=0)
    citation_coverage_rate: float = Field(ge=0, le=1)
    citation_id_valid_rate: float = Field(ge=0, le=1)
    citation_allowlist_violation_count: int = Field(ge=0)
    unknown_citation_count: int = Field(ge=0)
    duplicate_citation_count: int = Field(ge=0)
    forbidden_decision_count: Literal[0] = 0


class GroundedExplanationRun(_StrictModel):
    id: str
    tenant_id: str
    case_id: str
    retrieval_run_id: str
    citation_pack_id: str
    execution_mode: AnalysisExecutionMode = AnalysisExecutionMode.PRIMARY
    model_route_plan_id: str | None = None
    route_enforcement_contract_version: str | None = None
    status: GroundedExplanationRunStatus
    idempotency_key: str
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    correlation_id: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None


def validate_grounded_explanation(
    explanation: GroundedPolicyExplanation,
    citation_pack: CitationPack,
) -> GroundingValidationMetrics:
    """Enforce the deterministic citation allowlist before persistence."""

    allowlist = {citation.citation_id for citation in citation_pack.citations}
    references = tuple(
        citation_id
        for statement in explanation.policy_statements
        for citation_id in statement.citation_ids
    )
    unknown = tuple(citation_id for citation_id in references if citation_id not in allowlist)
    if unknown:
        raise CitationAllowlistViolationError()
    statement_count = len(explanation.policy_statements)
    return GroundingValidationMetrics(
        statement_count=statement_count,
        cited_statement_count=statement_count,
        citation_reference_count=len(references),
        unique_citation_count=len(set(references)),
        citation_coverage_rate=1.0,
        citation_id_valid_rate=1.0,
        citation_allowlist_violation_count=0,
        unknown_citation_count=0,
        duplicate_citation_count=0,
    )


__all__ = [
    "CitationAllowlistViolationError",
    "CitationPack",
    "CitationSnapshot",
    "GroundedExplanationInput",
    "GroundedExplanationInvalidOutputError",
    "GroundedExplanationProviderUnavailableError",
    "GroundedExplanationResponse",
    "GroundedExplanationRun",
    "GroundedExplanationRunStatus",
    "GroundedExplanationTimeoutError",
    "GroundedPolicyExplanation",
    "GroundedPolicyStatement",
    "GroundingValidationMetrics",
    "UnresolvedPolicyCondition",
    "validate_grounded_explanation",
]
