"""HTTP schemas for append-only deterministic policy evaluations."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.platform.policy_engine import PolicyEvaluationRun
from app.ports.policy_engine import PolicyEvaluationRunDetail


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartPolicyEvaluationRequest(_Schema):
    analysis_run_id: str
    as_of_date: date


class PolicyEvaluationRunResponse(_Schema):
    policy_evaluation_run_id: str
    status: str
    location: str

    @classmethod
    def from_run(cls, run: PolicyEvaluationRun) -> "PolicyEvaluationRunResponse":
        return cls(
            policy_evaluation_run_id=run.id,
            status=run.status.value,
            location=f"/api/v1/cases/{run.case_id}/policy-evaluation-runs/{run.id}",
        )


class PolicyEvaluationRunSummary(_Schema):
    id: str
    case_id: str
    analysis_run_id: str
    status: str
    summary_status: str | None
    rule_set: dict[str, str]
    as_of_date: date
    correlation_id: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None
    failure_message: str | None

    @classmethod
    def from_run(cls, run: PolicyEvaluationRun) -> "PolicyEvaluationRunSummary":
        return cls(
            id=run.id,
            case_id=run.case_id,
            analysis_run_id=run.analysis_run_id,
            status=run.status.value,
            summary_status=run.summary_status.value if run.summary_status else None,
            rule_set={
                "name": run.rule_set_name,
                "version": run.rule_set_version,
                "hash": run.rule_set_hash,
            },
            as_of_date=run.as_of_date,
            correlation_id=run.correlation_id,
            created_at=run.created_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            failure_code=run.failure_code,
            failure_message=run.failure_message,
        )


class PolicyEvaluationRunListResponse(_Schema):
    items: tuple[PolicyEvaluationRunSummary, ...]


class PolicyEvaluationRunDetailResponse(_Schema):
    run: PolicyEvaluationRunSummary
    input_qualification: dict[str, str]
    rule_results: tuple[dict[str, object], ...]

    @classmethod
    def from_detail(cls, detail: PolicyEvaluationRunDetail) -> "PolicyEvaluationRunDetailResponse":
        results: tuple[dict[str, object], ...] = ()
        if detail.evaluation is not None:
            results = tuple(
                {
                    "rule_id": item.rule_id,
                    "rule_version": item.rule_version,
                    "status": item.status.value,
                    "condition_results": tuple(
                        condition.model_dump(mode="json") for condition in item.condition_results
                    ),
                    "effects": tuple(effect.model_dump(mode="json") for effect in item.effects),
                    "source_clause_ids": item.source_clause_ids,
                }
                for item in detail.evaluation.rule_results
            )
        return cls(
            run=PolicyEvaluationRunSummary.from_run(detail.run),
            input_qualification=detail.input_qualification,
            rule_results=results,
        )


__all__ = [
    "PolicyEvaluationRunDetailResponse",
    "PolicyEvaluationRunListResponse",
    "PolicyEvaluationRunResponse",
    "PolicyEvaluationRunSummary",
    "StartPolicyEvaluationRequest",
]
