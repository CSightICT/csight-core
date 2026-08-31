"""Ports for append-only grounded policy explanation executions."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.analysis.models import ProviderExecutionMetadata
from app.platform.grounding import (
    CitationPack,
    GroundedExplanationRun,
    GroundedPolicyExplanation,
    GroundingValidationMetrics,
)


class _DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class GroundedExplanationExecutionSource(_DTO):
    run: GroundedExplanationRun
    claim_token: str = Field(min_length=1)
    case_summary: str = Field(min_length=1, repr=False)
    citation_pack: CitationPack


class GroundedExplanationRunDetail(_DTO):
    run: GroundedExplanationRun
    citation_pack: CitationPack
    explanation: GroundedPolicyExplanation | None = None
    validation_metrics: GroundingValidationMetrics | None = None


class GroundedExplanationRunRepository(Protocol):
    def get_by_idempotency_key(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> GroundedExplanationRun | None: ...

    def get_execution_mode(
        self,
        *,
        tenant_id: str,
        case_id: str,
        retrieval_run_id: str,
    ) -> AnalysisExecutionMode: ...

    def create(
        self,
        *,
        tenant_id: str,
        case_id: str,
        retrieval_run_id: str,
        requested_by: str,
        correlation_id: str,
        idempotency_key: str,
        request_hash: str,
        provider: ProviderExecutionMetadata,
        prompt_name: str,
        prompt_version: str,
        prompt_hash: str,
        execution_mode: AnalysisExecutionMode,
        model_route_plan_id: str | None,
        route_enforcement_contract_version: str | None,
    ) -> tuple[GroundedExplanationRun, bool]: ...

    def list(self, *, tenant_id: str, case_id: str) -> tuple[GroundedExplanationRun, ...]: ...

    def get(
        self, *, tenant_id: str, case_id: str, run_id: str
    ) -> GroundedExplanationRunDetail | None: ...

    def claim(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        run_id: str,
        correlation_id: str,
    ) -> GroundedExplanationExecutionSource | None: ...

    def succeed(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_id: str,
        claim_token: str,
        explanation: GroundedPolicyExplanation,
        metrics: GroundingValidationMetrics,
        provider: ProviderExecutionMetadata,
        prompt_name: str,
        prompt_version: str,
        prompt_hash: str,
    ) -> bool: ...

    def fail(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_id: str,
        claim_token: str,
        code: str,
        message: str,
    ) -> bool: ...

    def record_consumer_failure(
        self,
        *,
        event_id: str,
        code: str,
        message: str,
    ) -> None: ...


__all__ = [
    "GroundedExplanationExecutionSource",
    "GroundedExplanationRunDetail",
    "GroundedExplanationRunRepository",
]
