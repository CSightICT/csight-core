"""Case-scoped deterministic policy evaluation use cases."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.platform.errors import CaseNotFoundError
from app.platform.policy_engine import PolicyEvaluationRun, evaluate_rule_set
from app.platform.tenant import Permission, Principal
from app.ports.policy_engine import PolicyEngineRepository, PolicyEvaluationRunDetail


class _DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class StartPolicyEvaluationCommand(_DTO):
    analysis_run_id: str = Field(min_length=1)
    as_of_date: date
    idempotency_key: str = Field(min_length=1, max_length=255, repr=False)
    correlation_id: str = Field(min_length=1, max_length=128)


class StartPolicyEvaluationResult(_DTO):
    run: PolicyEvaluationRun
    replayed: bool


class ExecutePolicyEvaluationCommand(_DTO):
    event_id: str
    tenant_id: str
    case_id: str
    policy_evaluation_run_id: str
    correlation_id: str


def canonical_request_hash(case_id: str, command: StartPolicyEvaluationCommand) -> str:
    payload = {
        "case_id": case_id,
        "analysis_run_id": command.analysis_run_id,
        "as_of_date": command.as_of_date.isoformat(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class StartPolicyEvaluation:
    def __init__(self, repository: PolicyEngineRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        command: StartPolicyEvaluationCommand,
    ) -> StartPolicyEvaluationResult:
        principal.require(Permission.ANALYSIS_CREATE)
        run, replayed = self._repository.create(
            tenant_id=principal.tenant_id,
            case_id=case_id,
            analysis_run_id=command.analysis_run_id,
            as_of_date=command.as_of_date,
            requested_by=principal.user_id,
            correlation_id=command.correlation_id,
            idempotency_key=command.idempotency_key,
            request_hash=canonical_request_hash(case_id, command),
        )
        return StartPolicyEvaluationResult(run=run, replayed=replayed)


class ListPolicyEvaluations:
    def __init__(self, repository: PolicyEngineRepository) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, case_id: str) -> tuple[PolicyEvaluationRun, ...]:
        principal.require(Permission.POLICY_READ)
        return self._repository.list(tenant_id=principal.tenant_id, case_id=case_id)


class GetPolicyEvaluation:
    def __init__(self, repository: PolicyEngineRepository) -> None:
        self._repository = repository

    def execute(
        self, *, principal: Principal, case_id: str, run_id: str
    ) -> PolicyEvaluationRunDetail:
        principal.require(Permission.POLICY_READ)
        detail = self._repository.get(
            tenant_id=principal.tenant_id,
            case_id=case_id,
            run_id=run_id,
        )
        if detail is None:
            raise CaseNotFoundError("The requested policy evaluation run was not found.")
        return detail


class ExecutePolicyEvaluation:
    def __init__(self, repository: PolicyEngineRepository) -> None:
        self._repository = repository

    def execute(self, command: ExecutePolicyEvaluationCommand) -> str:
        source = self._repository.claim(
            tenant_id=command.tenant_id,
            run_id=command.policy_evaluation_run_id,
        )
        if source is None:
            return "NOOP"
        try:
            result = evaluate_rule_set(source.rule_set, source.input_snapshot)
            if result.rule_set_hash != source.run.rule_set_hash:
                raise ValueError("rule-set hash mismatch")
            self._repository.succeed(
                tenant_id=source.run.tenant_id,
                run_id=source.run.id,
                result=result,
            )
            return "SUCCEEDED"
        except Exception as error:
            self._repository.fail(
                tenant_id=source.run.tenant_id,
                run_id=source.run.id,
                code="POLICY_EVALUATION_FAILED",
                message=str(error)[:1000] or "Policy evaluation failed.",
            )
            return "FAILED"


__all__ = [
    "ExecutePolicyEvaluation",
    "ExecutePolicyEvaluationCommand",
    "GetPolicyEvaluation",
    "ListPolicyEvaluations",
    "StartPolicyEvaluation",
    "StartPolicyEvaluationCommand",
    "StartPolicyEvaluationResult",
    "canonical_request_hash",
]
