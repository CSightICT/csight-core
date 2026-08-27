"""Durable consumer state transitions shared by async worker families."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import ForeignKeyConstraint, Table, UniqueConstraint

from app.adapters.persistence.async_events import (
    begin_consumer_attempt,
    consumer_failure_may_terminalize_run,
    event_allows_completion,
    mark_event_consumed,
    mark_event_failed,
    record_rejected_dispatch_recovery,
    recover_dispatch_failure,
    validate_request_event,
)
from app.adapters.persistence.models import (
    GroundedExplanationOutboxEventModel,
    GroundedExplanationRunModel,
    HumanReviewRequestEventModel,
    PolicyEvaluationOutboxEventModel,
    PolicyEvaluationRunModel,
    PolicyRetrievalOutboxEventModel,
    PolicyRetrievalRunModel,
)
from app.application.grounding import (
    ExecuteGroundedExplanation,
    ExecuteGroundedExplanationCommand,
)
from app.application.human_review import HumanReviewRequestedCommand
from app.application.policy_engine import ExecutePolicyEvaluation, ExecutePolicyEvaluationCommand
from app.application.policy_query_runs import (
    ExecutePolicyRetrievalRun,
    ExecutePolicyRetrievalRunCommand,
)
from app.platform.async_reliability import ExecutionLeaseActiveError
from app.platform.query_builder import QueryStrategy

pytestmark = pytest.mark.unit


def _event() -> PolicyEvaluationOutboxEventModel:
    now = datetime.now(UTC)
    return PolicyEvaluationOutboxEventModel(
        id=uuid4(),
        tenant_id=uuid4(),
        case_id=uuid4(),
        policy_evaluation_run_id=uuid4(),
        correlation_id="correlation-1",
        status="PROCESSING",
        attempt_count=1,
        available_at=now,
        claimed_at=now,
        claim_token=uuid4(),
        claimed_by="dispatcher-1",
        published_at=None,
        last_error=None,
        consumed_at=None,
        consumer_attempt_count=0,
        consumer_last_error=None,
        failure_code=None,
        failed_at=None,
        created_at=now,
    )


def test_processing_event_can_be_consumed_before_dispatcher_marks_publish() -> None:
    event = _event()
    now = datetime.now(UTC)

    begin_consumer_attempt(event)
    assert (
        validate_request_event(
            event,
            tenant_id=event.tenant_id,
            case_id=event.case_id,
            correlation_id=event.correlation_id,
            run_id=event.policy_evaluation_run_id,
            run_attribute="policy_evaluation_run_id",
        )
        is None
    )
    mark_event_consumed(event, now=now)

    assert event.status == "CONSUMED"
    assert event.published_at == now and event.consumed_at == now
    assert event.consumer_attempt_count == 1
    assert event.claim_token is None and event.claimed_at is None and event.claimed_by is None


def test_payload_mismatch_is_a_durable_redacted_failure() -> None:
    event = _event()
    event.status = "PENDING"
    event.attempt_count = 0
    event.claimed_at = None
    event.claim_token = None
    event.claimed_by = None
    error = validate_request_event(
        event,
        tenant_id=event.tenant_id,
        case_id=uuid4(),
        correlation_id=event.correlation_id,
        run_id=event.policy_evaluation_run_id,
        run_attribute="policy_evaluation_run_id",
    )
    assert error is not None and error.code == "ASYNC_EVENT_PAYLOAD_MISMATCH"

    mark_event_failed(
        event,
        now=datetime.now(UTC),
        code=error.code,
        message=str(error),
    )

    assert event.status == "FAILED"
    assert event.attempt_count == 1
    assert event.failure_code == "ASYNC_EVENT_PAYLOAD_MISMATCH"
    assert event.failed_at is not None
    assert event.claim_token is None and event.claimed_at is None and event.claimed_by is None


def test_active_execution_lease_carries_a_retry_deadline() -> None:
    retry_at = datetime.now(UTC)
    error = ExecutionLeaseActiveError(retry_at=retry_at)
    assert error.retry_at == retry_at


def test_inflight_consumer_can_recover_a_later_dispatch_terminal_failure() -> None:
    event = _event()
    failed_at = datetime.now(UTC)
    event.status = "FAILED"
    event.claimed_at = None
    event.claim_token = None
    event.claimed_by = None
    event.last_error = "Message publication failed permanently."
    event.failure_code = "POLICY_EVALUATION_OUTBOX_FAILED"
    event.failed_at = failed_at
    event.consumer_attempt_count = 1

    assert event_allows_completion(
        event,
        dispatch_failure_code="POLICY_EVALUATION_OUTBOX_FAILED",
    )
    assert recover_dispatch_failure(
        event,
        now=failed_at,
        dispatch_failure_code="POLICY_EVALUATION_OUTBOX_FAILED",
    )
    assert event.status == "PUBLISHED" and event.failure_code is None

    mark_event_consumed(event, now=failed_at)
    assert event.status == "CONSUMED"
    assert event.last_error is None and event.failed_at is None


def test_forged_delivery_cannot_recover_dispatch_failure() -> None:
    event = _event()
    failed_at = datetime.now(UTC)
    event.status = "FAILED"
    event.failure_code = "POLICY_EVALUATION_OUTBOX_FAILED"
    event.failed_at = failed_at
    event.last_error = "Message publication failed permanently."

    error = validate_request_event(
        event,
        tenant_id=event.tenant_id,
        case_id=uuid4(),
        correlation_id=event.correlation_id,
        run_id=event.policy_evaluation_run_id,
        run_attribute="policy_evaluation_run_id",
    )

    assert error is not None and error.code == "ASYNC_EVENT_PAYLOAD_MISMATCH"
    record_rejected_dispatch_recovery(event, message=str(error))
    assert event.status == "FAILED"
    assert event.failure_code == "POLICY_EVALUATION_OUTBOX_FAILED"
    assert event.failed_at == failed_at
    assert event.last_error == "Message publication failed permanently."
    assert event.consumer_last_error is not None


def test_stale_terminal_recorder_cannot_kill_a_newer_active_lease() -> None:
    now = datetime.now(UTC)

    assert not consumer_failure_may_terminalize_run(
        status="RUNNING",
        lease_expires_at=now + timedelta(minutes=5),
        now=now,
    )
    assert consumer_failure_may_terminalize_run(
        status="RUNNING",
        lease_expires_at=now - timedelta(microseconds=1),
        now=now,
    )
    assert consumer_failure_may_terminalize_run(
        status="QUEUED",
        lease_expires_at=None,
        now=now,
    )


@pytest.mark.parametrize(
    ("command_type", "run_field"),
    (
        (ExecutePolicyRetrievalRunCommand, "retrieval_run_id"),
        (ExecuteGroundedExplanationCommand, "grounded_explanation_run_id"),
        (ExecutePolicyEvaluationCommand, "policy_evaluation_run_id"),
        (HumanReviewRequestedCommand, "policy_evaluation_run_id"),
    ),
)
def test_worker_commands_reject_malformed_uuid_at_boundary(
    command_type: type[
        ExecutePolicyRetrievalRunCommand
        | ExecuteGroundedExplanationCommand
        | ExecutePolicyEvaluationCommand
        | HumanReviewRequestedCommand
    ],
    run_field: str,
) -> None:
    payload = {
        "event_id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "case_id": str(uuid4()),
        run_field: "not-a-uuid",
        "correlation_id": "correlation-1",
    }

    with pytest.raises(PydanticValidationError):
        command_type.model_validate(payload)


def test_policy_evaluation_succeed_persistence_error_is_retried_not_domain_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = MagicMock()
    run = SimpleNamespace(tenant_id=str(uuid4()), id=str(uuid4()), rule_set_hash="a" * 64)
    repository.claim.return_value = SimpleNamespace(
        run=run,
        claim_token=str(uuid4()),
        rule_set=object(),
        input_snapshot=object(),
    )
    repository.succeed.side_effect = RuntimeError("transient database failure")

    def evaluate_rule_set(_rule_set: object, _snapshot: object) -> SimpleNamespace:
        return SimpleNamespace(rule_set_hash=run.rule_set_hash)

    monkeypatch.setattr("app.application.policy_engine.evaluate_rule_set", evaluate_rule_set)
    command = ExecutePolicyEvaluationCommand(
        event_id=str(uuid4()),
        tenant_id=run.tenant_id,
        case_id=str(uuid4()),
        policy_evaluation_run_id=run.id,
        correlation_id="correlation-1",
    )

    with pytest.raises(RuntimeError, match="transient database failure"):
        ExecutePolicyEvaluation(repository).execute(command)

    repository.fail.assert_not_called()


def test_grounding_succeed_persistence_error_is_retried_not_domain_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = MagicMock()
    run = SimpleNamespace(tenant_id=str(uuid4()), id=str(uuid4()))
    repository.claim.return_value = SimpleNamespace(
        run=run,
        claim_token=str(uuid4()),
        case_summary="summary",
        citation_pack=object(),
    )
    repository.succeed.side_effect = RuntimeError("transient database failure")
    llm = MagicMock()
    llm.explain_policy_grounded.return_value = SimpleNamespace(
        explanation=object(),
        metadata=object(),
    )

    def validate_grounded_explanation(_explanation: object, _pack: object) -> object:
        return object()

    def grounded_explanation_input(**values: object) -> SimpleNamespace:
        return SimpleNamespace(**values)

    monkeypatch.setattr(
        "app.application.grounding.validate_grounded_explanation",
        validate_grounded_explanation,
    )
    monkeypatch.setattr(
        "app.application.grounding.GroundedExplanationInput",
        grounded_explanation_input,
    )
    prompt = SimpleNamespace(name="grounding", version="1", content_hash="b" * 64)
    command = ExecuteGroundedExplanationCommand(
        event_id=str(uuid4()),
        tenant_id=run.tenant_id,
        case_id=str(uuid4()),
        grounded_explanation_run_id=run.id,
        correlation_id="correlation-1",
    )

    with pytest.raises(RuntimeError, match="transient database failure"):
        ExecuteGroundedExplanation(repository=repository, llm=llm, prompt=prompt).execute(command)  # type: ignore[arg-type]

    repository.fail.assert_not_called()


def test_retrieval_succeed_persistence_error_is_retried_not_domain_failed() -> None:
    repository = MagicMock()
    run = SimpleNamespace(
        tenant_id=str(uuid4()),
        id=str(uuid4()),
        strategy=QueryStrategy.RAW,
        as_of_date=datetime.now(UTC).date(),
        top_k=3,
    )
    source = SimpleNamespace(
        run=run,
        claim_token=str(uuid4()),
        customer_message="damaged product",
        builder_input=SimpleNamespace(trusted_metadata=SimpleNamespace(product_category="GENERAL")),
    )
    repository.claim.return_value = source
    repository.succeed.side_effect = RuntimeError("transient database failure")
    search = MagicMock()
    search.execute.return_value = SimpleNamespace(hits=())
    command = ExecutePolicyRetrievalRunCommand(
        event_id=str(uuid4()),
        tenant_id=run.tenant_id,
        case_id=str(uuid4()),
        retrieval_run_id=run.id,
        correlation_id="correlation-1",
    )

    with pytest.raises(RuntimeError, match="transient database failure"):
        ExecutePolicyRetrievalRun(
            repository=repository,
            search=search,
            llm=MagicMock(),
            prompt=MagicMock(),
        ).execute(command)

    repository.fail.assert_not_called()


@pytest.mark.parametrize(
    ("model", "constraint_name"),
    (
        (PolicyRetrievalRunModel, "uq_policy_retrieval_runs_tenant_case_id"),
        (GroundedExplanationRunModel, "uq_grounded_explanation_runs_tenant_case_id"),
        (PolicyEvaluationRunModel, "uq_policy_evaluation_runs_tenant_case_id"),
    ),
)
def test_run_models_expose_tenant_case_aggregate_identity(
    model: type[PolicyRetrievalRunModel | GroundedExplanationRunModel | PolicyEvaluationRunModel],
    constraint_name: str,
) -> None:
    table = cast(Table, model.__table__)
    constraint = next(
        item
        for item in table.constraints
        if isinstance(item, UniqueConstraint) and item.name == constraint_name
    )
    assert tuple(column.name for column in constraint.columns) == ("tenant_id", "case_id", "id")


@pytest.mark.parametrize(
    ("model", "constraint_name", "run_column"),
    (
        (
            PolicyRetrievalOutboxEventModel,
            "fk_policy_retrieval_outbox_run_case",
            "retrieval_run_id",
        ),
        (
            GroundedExplanationOutboxEventModel,
            "fk_grounded_explanation_outbox_run_case",
            "grounded_explanation_run_id",
        ),
        (
            PolicyEvaluationOutboxEventModel,
            "fk_policy_evaluation_outbox_run_case",
            "policy_evaluation_run_id",
        ),
        (
            HumanReviewRequestEventModel,
            "fk_human_review_request_events_policy_run_case",
            "policy_evaluation_run_id",
        ),
    ),
)
def test_request_event_models_bind_case_to_the_exact_aggregate_run(
    model: type[
        PolicyRetrievalOutboxEventModel
        | GroundedExplanationOutboxEventModel
        | PolicyEvaluationOutboxEventModel
        | HumanReviewRequestEventModel
    ],
    constraint_name: str,
    run_column: str,
) -> None:
    table = cast(Table, model.__table__)
    constraint = next(
        item
        for item in table.constraints
        if isinstance(item, ForeignKeyConstraint) and item.name == constraint_name
    )
    assert tuple(column.name for column in constraint.columns) == (
        "tenant_id",
        "case_id",
        run_column,
    )
