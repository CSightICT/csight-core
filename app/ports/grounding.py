"""Ports for append-only grounded policy explanation executions."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

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
    case_summary: str = Field(min_length=1, repr=False)
    citation_pack: CitationPack


class GroundedExplanationRunDetail(_DTO):
    run: GroundedExplanationRun
    citation_pack: CitationPack
    explanation: GroundedPolicyExplanation | None = None
    validation_metrics: GroundingValidationMetrics | None = None


class GroundedExplanationRunRepository(Protocol):
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
    ) -> tuple[GroundedExplanationRun, bool]: ...

    def list(self, *, tenant_id: str, case_id: str) -> tuple[GroundedExplanationRun, ...]: ...

    def get(
        self, *, tenant_id: str, case_id: str, run_id: str
    ) -> GroundedExplanationRunDetail | None: ...

    def claim(
        self, *, tenant_id: str, run_id: str
    ) -> GroundedExplanationExecutionSource | None: ...

    def succeed(
        self,
        *,
        tenant_id: str,
        run_id: str,
        explanation: GroundedPolicyExplanation,
        metrics: GroundingValidationMetrics,
        provider: ProviderExecutionMetadata,
        prompt_name: str,
        prompt_version: str,
        prompt_hash: str,
    ) -> None: ...

    def fail(self, *, tenant_id: str, run_id: str, code: str, message: str) -> None: ...


__all__ = [
    "GroundedExplanationExecutionSource",
    "GroundedExplanationRunDetail",
    "GroundedExplanationRunRepository",
]
