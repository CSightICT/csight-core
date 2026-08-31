"""Replay-first and strategy-aware model-route snapshot contracts."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.application.policy_query_runs import (
    StartPolicyRetrievalRun,
    StartPolicyRetrievalRunCommand,
)
from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.model_routing import MODEL_ROUTE_ENFORCEMENT_CONTRACT_VERSION
from app.platform.query_builder import PolicyRetrievalRun, QueryStrategy, RetrievalRunStatus
from app.platform.tenant import Principal, Role

pytestmark = pytest.mark.unit

TENANT_ID = "11111111-1111-4111-8111-111111111111"
USER_ID = "22222222-2222-4222-8222-222222222222"
CASE_ID = "33333333-3333-4333-8333-333333333333"
ANALYSIS_ID = "44444444-4444-4444-8444-444444444444"
ROUTE_ID = "55555555-5555-4555-8555-555555555555"


def _principal() -> Principal:
    return Principal(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        email="admin@example.invalid",
        display_name="Admin",
        roles=frozenset({Role.ADMIN}),
    )


def _command(strategy: QueryStrategy) -> StartPolicyRetrievalRunCommand:
    return StartPolicyRetrievalRunCommand(
        analysis_run_id=ANALYSIS_ID,
        strategy=strategy,
        as_of_date=date(2026, 8, 31),
        top_k=3,
        idempotency_key=f"route-{strategy.value.lower()}",
        correlation_id="corr-route-start",
    )


def _run(*, strategy: QueryStrategy, route_id: str | None) -> PolicyRetrievalRun:
    return PolicyRetrievalRun(
        id="66666666-6666-4666-8666-666666666666",
        tenant_id=TENANT_ID,
        case_id=CASE_ID,
        analysis_run_id=ANALYSIS_ID,
        text_result_id="77777777-7777-4777-8777-777777777777",
        strategy=strategy,
        execution_mode=AnalysisExecutionMode.PRIMARY,
        model_route_plan_id=route_id,
        route_enforcement_contract_version=(
            MODEL_ROUTE_ENFORCEMENT_CONTRACT_VERSION if route_id is not None else None
        ),
        status=RetrievalRunStatus.QUEUED,
        as_of_date=date(2026, 8, 31),
        top_k=3,
        idempotency_key=f"route-{strategy.value.lower()}",
        request_hash="a" * 64,
        correlation_id="corr-route-start",
        created_at=datetime.now(UTC),
    )


def test_llm_start_resolves_and_snapshots_route_after_replay_check() -> None:
    repository = Mock()
    repository.get_by_idempotency_key.return_value = None
    repository.get_execution_mode.return_value = AnalysisExecutionMode.PRIMARY
    repository.create.return_value = (_run(strategy=QueryStrategy.LLM, route_id=ROUTE_ID), False)
    resolver = Mock()
    resolver.execute.return_value = SimpleNamespace(route_plan=SimpleNamespace(id=ROUTE_ID))

    result = StartPolicyRetrievalRun(
        repository,
        model_route_resolver=resolver,
    ).execute(principal=_principal(), case_id=CASE_ID, command=_command(QueryStrategy.LLM))

    assert result.replayed is False
    resolver.execute.assert_called_once()
    assert repository.method_calls[0][0] == "get_by_idempotency_key"
    create_kwargs = repository.create.call_args.kwargs
    assert create_kwargs["model_route_plan_id"] == ROUTE_ID
    assert (
        create_kwargs["route_enforcement_contract_version"]
        == MODEL_ROUTE_ENFORCEMENT_CONTRACT_VERSION
    )


@pytest.mark.parametrize("strategy", (QueryStrategy.RAW, QueryStrategy.DETERMINISTIC))
def test_non_llm_start_never_resolves_a_model_route(strategy: QueryStrategy) -> None:
    repository = Mock()
    repository.get_by_idempotency_key.return_value = None
    repository.get_execution_mode.return_value = AnalysisExecutionMode.PRIMARY
    repository.create.return_value = (_run(strategy=strategy, route_id=None), False)
    resolver = Mock()

    StartPolicyRetrievalRun(repository, model_route_resolver=resolver).execute(
        principal=_principal(),
        case_id=CASE_ID,
        command=_command(strategy),
    )

    resolver.execute.assert_not_called()
    assert repository.create.call_args.kwargs["model_route_plan_id"] is None


def test_replay_returns_before_mode_or_route_lookup() -> None:
    repository = Mock()
    replay = _run(strategy=QueryStrategy.LLM, route_id=ROUTE_ID)
    repository.get_by_idempotency_key.return_value = replay
    resolver = Mock()

    result = StartPolicyRetrievalRun(repository, model_route_resolver=resolver).execute(
        principal=_principal(),
        case_id=CASE_ID,
        command=_command(QueryStrategy.LLM),
    )

    assert result.replayed is True
    assert result.run == replay
    repository.get_execution_mode.assert_not_called()
    repository.create.assert_not_called()
    resolver.execute.assert_not_called()
