"""Ports for append-only Case-to-policy retrieval executions."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.query_builder import (
    MultiQueryHit,
    PolicyQueryBuilderInput,
    PolicyQueryPlan,
    PolicyRetrievalRun,
    PolicySimilarityDiagnostic,
)


class PolicyRetrievalExecutionSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    run: PolicyRetrievalRun
    claim_token: str = Field(min_length=1)
    customer_message: str = Field(min_length=1, repr=False)
    builder_input: PolicyQueryBuilderInput


class PolicyRetrievalRunDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    run: PolicyRetrievalRun
    query_plan: PolicyQueryPlan | None = None
    hits: tuple[MultiQueryHit, ...] = ()
    policy_similarity: tuple[PolicySimilarityDiagnostic, ...] = ()
    index_version: str
    base_retrieval_profile_hash: str
    multi_query_fusion_profile: str


class PolicyRetrievalRunRepository(Protocol):
    def get_by_idempotency_key(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> PolicyRetrievalRun | None: ...

    def get_execution_mode(
        self,
        *,
        tenant_id: str,
        case_id: str,
        analysis_run_id: str,
    ) -> AnalysisExecutionMode: ...

    def create(
        self,
        *,
        tenant_id: str,
        case_id: str,
        analysis_run_id: str,
        strategy: str,
        as_of_date: str,
        top_k: int,
        requested_by: str,
        correlation_id: str,
        idempotency_key: str,
        request_hash: str,
        execution_mode: AnalysisExecutionMode,
        model_route_plan_id: str | None,
        route_enforcement_contract_version: str | None,
    ) -> tuple[PolicyRetrievalRun, bool]: ...

    def list(self, *, tenant_id: str, case_id: str) -> tuple[PolicyRetrievalRun, ...]: ...

    def get(
        self, *, tenant_id: str, case_id: str, run_id: str
    ) -> PolicyRetrievalRunDetail | None: ...

    def claim(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        run_id: str,
        correlation_id: str,
    ) -> PolicyRetrievalExecutionSource | None: ...

    def succeed(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_id: str,
        claim_token: str,
        plan: PolicyQueryPlan,
        hits: tuple[MultiQueryHit, ...],
        raw_query_hash: str | None,
        diagnostics: tuple[PolicySimilarityDiagnostic, ...] = (),
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
    "PolicyRetrievalExecutionSource",
    "PolicyRetrievalRunDetail",
    "PolicyRetrievalRunRepository",
]
