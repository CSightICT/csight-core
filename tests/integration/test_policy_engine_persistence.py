"""Opt-in PostgreSQL append-only policy evaluation integration flow."""

import os
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.models import (
    AnalysisRunModel,
    LLMExtractionResultV2Model,
    PolicyConditionEvaluationResultModel,
    PolicyEvaluationEffectModel,
    PolicyEvaluationRunModel,
    PolicyRuleEvaluationResultModel,
    TenantModel,
)
from app.adapters.persistence.policy_engine import SQLAlchemyPolicyEngineRepository
from app.adapters.persistence.session import create_session_factory
from app.application.policy_engine import ExecutePolicyEvaluation, ExecutePolicyEvaluationCommand
from app.bootstrap.settings import Settings
from app.platform.errors import CaseNotFoundError, IdempotencyKeyReusedError, ValidationError
from app.platform.policy_engine import PolicyRuleSet

pytestmark = pytest.mark.integration


def _rule_sets() -> tuple[PolicyRuleSet, ...]:
    path = Path("data/policy_rules/normalized/policy_rule_sets_v1.jsonl")
    return tuple(
        PolicyRuleSet.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    )


def test_append_only_policy_execution_replay_duplicate_and_tenant_scope() -> None:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test policy evaluation persistence")
    settings = Settings()
    factory = create_session_factory(get_engine(settings))
    with factory() as session:
        source = session.execute(
            select(
                AnalysisRunModel.tenant_id,
                AnalysisRunModel.case_id,
                AnalysisRunModel.id,
                AnalysisRunModel.requested_by,
            )
            .join(
                LLMExtractionResultV2Model,
                LLMExtractionResultV2Model.analysis_run_id == AnalysisRunModel.id,
            )
            .join(TenantModel, TenantModel.id == AnalysisRunModel.tenant_id)
            .where(
                AnalysisRunModel.status == "SUCCEEDED",
                TenantModel.slug == "csight-demo-brand",
            )
            .order_by(AnalysisRunModel.created_at.desc())
            .limit(1)
        ).one_or_none()
        other_tenant = session.scalar(
            select(TenantModel.id).where(TenantModel.slug == "csight-demo-retail")
        )
    if source is None or other_tenant is None:
        pytest.skip("local synthetic v2 analysis and both policy tenants are required")
    tenant_id, case_id, analysis_id, requested_by = map(str, source)
    repository = SQLAlchemyPolicyEngineRepository(factory)
    key = f"policy-integration-{uuid4()}"
    run, replayed = repository.create(
        tenant_id=tenant_id,
        case_id=case_id,
        analysis_run_id=analysis_id,
        as_of_date=date(2026, 2, 1),
        requested_by=requested_by,
        correlation_id=f"corr-{uuid4()}",
        idempotency_key=key,
        request_hash="b" * 64,
    )
    replay, was_replayed = repository.create(
        tenant_id=tenant_id,
        case_id=case_id,
        analysis_run_id=analysis_id,
        as_of_date=date(2026, 2, 1),
        requested_by=requested_by,
        correlation_id=f"corr-{uuid4()}",
        idempotency_key=key,
        request_hash="b" * 64,
    )
    assert replayed is False and was_replayed is True and replay.id == run.id
    with pytest.raises(IdempotencyKeyReusedError):
        repository.create(
            tenant_id=tenant_id,
            case_id=case_id,
            analysis_run_id=analysis_id,
            as_of_date=date(2026, 2, 1),
            requested_by=requested_by,
            correlation_id=f"corr-{uuid4()}",
            idempotency_key=key,
            request_hash="c" * 64,
        )
    with pytest.raises(ValidationError, match="No active policy rule set"):
        repository.create(
            tenant_id=tenant_id,
            case_id=case_id,
            analysis_run_id=analysis_id,
            as_of_date=date(2025, 12, 31),
            requested_by=requested_by,
            correlation_id=f"corr-{uuid4()}",
            idempotency_key=f"policy-no-active-{uuid4()}",
            request_hash="d" * 64,
        )
    with pytest.raises(CaseNotFoundError):
        repository.create(
            tenant_id=tenant_id,
            case_id=case_id,
            analysis_run_id=str(uuid4()),
            as_of_date=date(2026, 2, 1),
            requested_by=requested_by,
            correlation_id=f"corr-{uuid4()}",
            idempotency_key=f"policy-invalid-analysis-{uuid4()}",
            request_hash="e" * 64,
        )

    command = ExecutePolicyEvaluationCommand(
        event_id=str(uuid4()),
        tenant_id=tenant_id,
        case_id=case_id,
        policy_evaluation_run_id=run.id,
        correlation_id=run.correlation_id,
    )
    use_case = ExecutePolicyEvaluation(repository)
    assert use_case.execute(command) == "SUCCEEDED"
    assert use_case.execute(command) == "NOOP"
    detail = repository.get(tenant_id=tenant_id, case_id=case_id, run_id=run.id)
    assert detail is not None and detail.run.status.value == "SUCCEEDED"
    assert detail.evaluation is not None and len(detail.evaluation.rule_results) == 12
    assert detail.input_qualification["llm"] in {"LOCAL_POC", "MOCK_QUALIFIED"}
    assert detail.input_qualification["vision"] == "MOCK_QUALIFIED"
    assert detail.input_qualification["alignment"] == "NOT_AVAILABLE"
    assert repository.get(tenant_id=str(other_tenant), case_id=case_id, run_id=run.id) is None

    with factory() as session:
        run_uuid = run.id
        rule_results = session.scalar(
            select(func.count(PolicyRuleEvaluationResultModel.id)).where(
                PolicyRuleEvaluationResultModel.policy_evaluation_run_id == run_uuid
            )
        )
        condition_results = session.scalar(
            select(func.count(PolicyConditionEvaluationResultModel.id))
            .join(
                PolicyRuleEvaluationResultModel,
                PolicyRuleEvaluationResultModel.id
                == PolicyConditionEvaluationResultModel.policy_rule_evaluation_result_id,
            )
            .where(PolicyRuleEvaluationResultModel.policy_evaluation_run_id == run_uuid)
        )
        effects = session.scalar(
            select(func.count(PolicyEvaluationEffectModel.id))
            .join(
                PolicyRuleEvaluationResultModel,
                PolicyRuleEvaluationResultModel.id
                == PolicyEvaluationEffectModel.policy_rule_evaluation_result_id,
            )
            .where(PolicyRuleEvaluationResultModel.policy_evaluation_run_id == run_uuid)
        )
        persisted_runs = session.scalar(
            select(func.count(PolicyEvaluationRunModel.id)).where(
                PolicyEvaluationRunModel.idempotency_key == key
            )
        )
    assert rule_results == 12
    assert condition_results == 12
    assert effects is not None and effects > 0
    assert persisted_runs == 1


def test_rule_ingestion_blocks_content_conflict_cross_tenant_and_wrong_source_version() -> None:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test policy rule ingestion")
    repository = SQLAlchemyPolicyEngineRepository(create_session_factory(get_engine(Settings())))
    first, second = _rule_sets()
    changed_rule = first.rules[0].model_copy(update={"priority": first.rules[0].priority - 1})
    changed_set = first.model_copy(update={"rules": (changed_rule, *first.rules[1:])})
    with pytest.raises(ValidationError, match="content mismatch"):
        repository.ingest((changed_set,))

    cross_tenant_rule = first.rules[0].model_copy(
        update={"source_references": second.rules[0].source_references}
    )
    cross_tenant_set = first.model_copy(
        update={
            "rule_set_version": "1.0.0-cross-tenant-probe",
            "rules": (cross_tenant_rule, *first.rules[1:]),
        }
    )
    with pytest.raises(ValidationError, match="source clause mismatch"):
        repository.ingest((cross_tenant_set,))

    wrong_source = (
        first.rules[0].source_references[0].model_copy(update={"document_version": "999.0.0"})
    )
    wrong_source_rule = first.rules[0].model_copy(update={"source_references": (wrong_source,)})
    wrong_source_set = first.model_copy(
        update={
            "rule_set_version": "1.0.0-wrong-source-probe",
            "rules": (wrong_source_rule, *first.rules[1:]),
        }
    )
    with pytest.raises(ValidationError, match="source clause mismatch"):
        repository.ingest((wrong_source_set,))
