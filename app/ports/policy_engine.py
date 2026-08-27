"""Ports for immutable policy rules and append-only evaluations."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.platform.policy_engine import (
    PolicyEvaluation,
    PolicyEvaluationInput,
    PolicyEvaluationRun,
    PolicyRuleSet,
)


class _DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PolicyEvaluationExecutionSource(_DTO):
    run: PolicyEvaluationRun
    claim_token: str = Field(min_length=1)
    rule_set: PolicyRuleSet
    input_snapshot: PolicyEvaluationInput


class PolicyEvaluationRunDetail(_DTO):
    run: PolicyEvaluationRun
    input_qualification: dict[str, str]
    evaluation: PolicyEvaluation | None = None


class PolicyEngineRepository(Protocol):
    def create(
        self,
        *,
        tenant_id: str,
        case_id: str,
        analysis_run_id: str,
        as_of_date: date,
        requested_by: str,
        correlation_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> tuple[PolicyEvaluationRun, bool]: ...

    def list(self, *, tenant_id: str, case_id: str) -> tuple[PolicyEvaluationRun, ...]: ...

    def get(
        self, *, tenant_id: str, case_id: str, run_id: str
    ) -> PolicyEvaluationRunDetail | None: ...

    def claim(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        run_id: str,
        correlation_id: str,
    ) -> PolicyEvaluationExecutionSource | None: ...

    def succeed(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_id: str,
        claim_token: str,
        result: PolicyEvaluation,
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
    "PolicyEngineRepository",
    "PolicyEvaluationExecutionSource",
    "PolicyEvaluationRunDetail",
]
