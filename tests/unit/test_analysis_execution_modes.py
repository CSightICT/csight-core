"""Focused contracts for analysis execution modes and admission serialization."""

from datetime import date
from typing import cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.adapters.persistence.analysis_repositories import SQLAlchemyAnalysisRunRepository
from app.application.policy_engine import StartPolicyEvaluation, StartPolicyEvaluationCommand
from app.bootstrap.settings import Settings
from app.platform.analysis import (
    AnalysisExecutionMode,
    ShadowAnalysisDownstreamForbiddenError,
)
from app.platform.errors import ForbiddenError
from app.platform.tenant import Principal, Role
from app.ports.policy_engine import PolicyEngineRepository
from tests.unit.test_policy_evaluation_http import _run  # pyright: ignore[reportPrivateUsage]

pytestmark = pytest.mark.unit


def _principal() -> Principal:
    return Principal(
        user_id="user-1",
        tenant_id="tenant-1",
        email="admin@example.test",
        display_name="Admin",
        roles=frozenset({Role.ADMIN}),
    )


def test_shadow_analysis_cannot_start_policy_workflow() -> None:
    repository = MagicMock()
    repository.get_analysis_execution_mode.return_value = AnalysisExecutionMode.SHADOW
    service = StartPolicyEvaluation(cast(PolicyEngineRepository, repository))

    with pytest.raises(ShadowAnalysisDownstreamForbiddenError):
        service.execute(
            principal=_principal(),
            case_id="case-1",
            command=StartPolicyEvaluationCommand(
                analysis_run_id="analysis-1",
                as_of_date=date(2026, 8, 29),
                idempotency_key="policy-key",
                correlation_id="correlation-1",
            ),
        )

    repository.get_analysis_execution_mode.assert_called_once_with(
        tenant_id="tenant-1",
        case_id="case-1",
        analysis_run_id="analysis-1",
    )
    repository.create.assert_not_called()


def test_admission_repository_takes_global_lock_then_runs_one_count_query() -> None:
    session = MagicMock(spec=Session)
    lock_result = MagicMock()
    count_result = MagicMock()
    count_result.one.return_value = (3, 2)
    session.execute.side_effect = (lock_result, count_result)
    repository = SQLAlchemyAnalysisRunRepository(session)

    counts = repository.lock_admission_counts(tenant_id="11111111-1111-1111-1111-111111111111")

    assert counts.global_nonterminal == 3
    assert counts.tenant_nonterminal == 2
    assert session.execute.call_count == 2
    lock_sql = str(session.execute.call_args_list[0].args[0])
    count_sql = str(session.execute.call_args_list[1].args[0])
    assert "pg_advisory_xact_lock" in lock_sql
    assert count_sql.count("count(") == 2
    assert "analysis_runs.status IN" in count_sql
    assert "FILTER (WHERE analysis_runs.tenant_id" in count_sql


@pytest.mark.parametrize("replayed", [False, True])
def test_explicit_shadow_feedback_can_start_policy_workflow(replayed: bool) -> None:
    repository = MagicMock()
    repository.get_analysis_execution_mode.return_value = AnalysisExecutionMode.SHADOW
    repository.create.return_value = (_run(), replayed)
    service = StartPolicyEvaluation(repository, shadow_feedback_enabled=True)
    result = service.execute(
        principal=_principal(),
        case_id="case-1",
        command=StartPolicyEvaluationCommand(
            analysis_run_id="analysis-1",
            as_of_date=date(2026, 9, 10),
            idempotency_key="feedback",
            correlation_id="feedback-test",
        ),
    )
    assert result.replayed is replayed
    assert repository.create.call_args.kwargs["tenant_id"] == "tenant-1"


def test_shadow_feedback_still_requires_analysis_permission() -> None:
    repository = MagicMock()
    service = StartPolicyEvaluation(repository, shadow_feedback_enabled=True)
    principal = _principal().model_copy(update={"roles": frozenset({Role.QUALITY_VIEWER})})
    with pytest.raises(ForbiddenError):
        service.execute(
            principal=principal,
            case_id="case-1",
            command=StartPolicyEvaluationCommand(
                analysis_run_id="analysis-1",
                as_of_date=date(2026, 9, 10),
                idempotency_key="feedback",
                correlation_id="feedback-test",
            ),
        )
    repository.create.assert_not_called()


@pytest.mark.parametrize("environment", ["production", "pilot"])
def test_shadow_feedback_cannot_be_enabled_outside_local(environment: str) -> None:
    with pytest.raises(ValueError, match="SHADOW human feedback"):
        Settings(environment=environment, shadow_human_feedback_enabled=True)
