from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import MagicMock

import pytest

from app.adapters.llm.mock import MockLLMProvider
from app.application.analysis import (
    ExecuteTextExtraction,
    ExecuteTextExtractionCommand,
    ExecutionDisposition,
    StartTextAnalysis,
    StartTextAnalysisCommand,
    canonical_analysis_request_hash,
    deterministic_retry_delay,
)
from app.application.outbox import DispatchOutbox
from app.domains.product_defect_cs.prompts import (
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
)
from app.platform.analysis import (
    TEXT_EXTRACTION_PIPELINE_VERSION,
    TEXT_EXTRACTION_V2_PIPELINE_VERSION,
    AnalysisAdmissionLimitExceededError,
    AnalysisAttemptStatus,
    AnalysisAttemptSummary,
    AnalysisExecutionMode,
    AnalysisFailure,
    AnalysisPipeline,
    AnalysisRequestedEvent,
    AnalysisRequestIdempotencyRecord,
    AnalysisRun,
    AnalysisRunStatus,
    AnalysisStageRun,
    AnalysisStageStatus,
    AnalysisStageType,
    AnalysisTrigger,
    MockProviderMode,
    OutboxEvent,
    OutboxStatus,
)
from app.platform.case import Case, RequestedAction
from app.platform.model_activation import (
    ActiveModelReleaseRequiredError,
    ModelReleaseIdentityMismatchError,
    ModelReleaseTask,
)
from app.platform.model_routing import PinnedModelRoutePlanRequiredError
from app.platform.tenant import Principal, Role
from app.ports.analysis_repository import (
    AnalysisAdmissionCounts,
    AnalysisRequestIdempotencyClaim,
    AnalysisUnitOfWorkFactory,
)
from app.ports.message_queue import MessageQueue
from app.ports.model_activation import ModelReleaseExecutionGuard
from app.ports.model_routing import ActiveModelRouteResolver, PinnedModelRouteExecutionGuard

NOW = datetime(2026, 8, 26, 3, 0, tzinfo=UTC)


class StaticClock:
    def now(self) -> datetime:
        return NOW


class SequenceIds:
    def __init__(self, values: Iterable[str]) -> None:
        self._values = iter(values)

    def new_id(self) -> str:
        return next(self._values)


class RecordingQueue:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[tuple[str, dict[str, object], str]] = []

    def publish(
        self,
        *,
        topic: str,
        payload: object,
        correlation_id: str,
    ) -> str:
        if self.fail:
            raise RuntimeError("broker unavailable")
        normalized = dict(cast("dict[str, object]", payload))
        self.messages.append((topic, normalized, correlation_id))
        return "message-1"

    def is_ready(self) -> bool:
        return not self.fail


def _uow() -> MagicMock:
    uow = MagicMock()
    uow.__enter__.return_value = uow
    uow.__exit__.return_value = None
    uow.analysis_runs.lock_admission_counts.return_value = AnalysisAdmissionCounts(
        global_nonterminal=0,
        tenant_nonterminal=0,
    )
    return uow


def _factory(*uows: MagicMock) -> AnalysisUnitOfWorkFactory:
    factory = MagicMock(side_effect=uows)
    return cast(AnalysisUnitOfWorkFactory, factory)


def _claim_new_analysis(
    *,
    tenant_id: str,
    record: AnalysisRequestIdempotencyRecord,
) -> AnalysisRequestIdempotencyClaim:
    del tenant_id
    return AnalysisRequestIdempotencyClaim(claimed=True, record=record)


def _principal() -> Principal:
    return Principal(
        user_id="user-1",
        tenant_id="tenant-1",
        email="admin@example.com",
        display_name="Admin",
        roles=frozenset({Role.ADMIN}),
    )


def _case() -> Case:
    return Case.create(
        case_id="case-1",
        tenant_id="tenant-1",
        order_ref="order-1",
        product_ref="product-1",
        customer_message="제품 옆면이 깨졌어요. 환불해 주세요.",
        requested_action=RequestedAction.REFUND,
        attributes={},
        created_by="user-1",
        now=NOW,
    )


def _run(status: AnalysisRunStatus = AnalysisRunStatus.RUNNING) -> AnalysisRun:
    return AnalysisRun(
        id="run-1",
        tenant_id="tenant-1",
        case_id="case-1",
        pipeline=AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION,
        pipeline_version=TEXT_EXTRACTION_PIPELINE_VERSION,
        trigger=AnalysisTrigger.USER_REQUEST,
        status=status,
        requested_by="user-1",
        correlation_id="correlation-1",
        idempotency_key="idempotency-1",
        request_hash="a" * 64,
        requested_at=NOW,
        started_at=NOW if status is not AnalysisRunStatus.QUEUED else None,
        created_at=NOW,
        updated_at=NOW,
    )


def _stage(
    status: AnalysisStageStatus = AnalysisStageStatus.RUNNING,
    *,
    attempt_count: int = 1,
    claim_token: str | None = "claim-1",
) -> AnalysisStageRun:
    has_claim = status is AnalysisStageStatus.RUNNING and claim_token is not None
    provider = MockLLMProvider().provider_metadata
    prompt = PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT
    return AnalysisStageRun(
        id="stage-1",
        tenant_id="tenant-1",
        analysis_run_id="run-1",
        stage_type=AnalysisStageType.TEXT_EXTRACTION,
        status=status,
        attempt_summary=AnalysisAttemptSummary(
            attempt_count=attempt_count,
            last_attempt_started_at=NOW if attempt_count else None,
        ),
        provider_name=provider.provider,
        model_name=provider.name,
        model_version=provider.version,
        model_revision=provider.revision,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        prompt_content_hash=prompt.content_hash,
        input_schema_version=prompt.input_schema_version,
        output_schema_version=prompt.output_schema_version,
        claim_token=claim_token if has_claim else None,
        claim_expires_at=NOW + timedelta(minutes=5) if has_claim else None,
        started_at=NOW if status is not AnalysisStageStatus.QUEUED else None,
        created_at=NOW,
        updated_at=NOW,
    )


def _command() -> ExecuteTextExtractionCommand:
    return ExecuteTextExtractionCommand(
        event_id="event-1",
        tenant_id="tenant-1",
        case_id="case-1",
        analysis_run_id="run-1",
        stage_run_id="stage-1",
        correlation_id="correlation-1",
    )


def _configure_claim_uow(uow: MagicMock, *, stage: AnalysisStageRun) -> None:
    uow.analysis_runs.get_for_update.return_value = _run()
    uow.stage_runs.get.return_value = stage
    uow.extraction_results.get_by_run.return_value = None
    uow.cases.get.return_value = _case()
    uow.stage_runs.claim_for_execution.return_value = stage


def _configure_completion_uow(uow: MagicMock, *, stage: AnalysisStageRun) -> None:
    uow.analysis_runs.get_for_update.return_value = _run()
    uow.stage_runs.get.return_value = stage
    uow.extraction_results.get_by_run.return_value = None
    uow.stage_runs.transition_if_claimed.return_value = stage
    uow.stage_attempts.finalize_if_claimed.return_value = object()
    uow.analysis_runs.transition.return_value = _run(AnalysisRunStatus.SUCCEEDED)


def _analysis_service(
    *,
    uow_factory: AnalysisUnitOfWorkFactory,
    provider: MockLLMProvider,
    ids: Iterable[str],
    max_attempts: int = 3,
    model_release_guard: ModelReleaseExecutionGuard | None = None,
    model_route_guard: PinnedModelRouteExecutionGuard | None = None,
) -> ExecuteTextExtraction:
    return ExecuteTextExtraction(
        uow_factory=uow_factory,
        provider=provider,
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        prompt_v2=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
        clock=StaticClock(),
        id_generator=SequenceIds(ids),
        max_attempts=max_attempts,
        retry_jitter_ratio=0,
        model_release_guard=model_release_guard,
        model_route_guard=model_route_guard,
    )


def _outbox_event(*, attempt_count: int = 1) -> OutboxEvent:
    event = AnalysisRequestedEvent(
        event_id="event-1",
        tenant_id="tenant-1",
        case_id="case-1",
        analysis_run_id="run-1",
        stage_run_id="stage-1",
        correlation_id="correlation-1",
        occurred_at=NOW,
    )
    return OutboxEvent(
        id=event.event_id,
        tenant_id=event.tenant_id,
        aggregate_type="analysis_run",
        aggregate_id=event.analysis_run_id,
        event_type=event.event_type,
        event_version=event.event_version,
        payload=event.model_dump(mode="json"),
        status=OutboxStatus.PROCESSING,
        attempt_count=attempt_count,
        available_at=NOW,
        claimed_at=NOW,
        claimed_by="dispatcher-1",
        claim_token="dispatch-claim",
        created_at=NOW,
        updated_at=NOW,
    )


def test_start_creates_run_stage_idempotency_and_reference_only_outbox_atomically() -> None:
    uow = _uow()
    uow.cases.get.return_value = _case()
    candidate_record = AnalysisRequestIdempotencyRecord(
        id="unused",
        tenant_id="tenant-1",
        case_id="case-1",
        idempotency_key="idempotency-1",
        request_hash="b" * 64,
        analysis_run_id="unused",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    uow.request_idempotency.claim.return_value = AnalysisRequestIdempotencyClaim(
        claimed=True,
        record=candidate_record,
    )
    command = StartTextAnalysisCommand(
        pipeline=AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION,
        pipeline_version=TEXT_EXTRACTION_PIPELINE_VERSION,
        idempotency_key="idempotency-1",
        correlation_id="correlation-1",
    )
    service = StartTextAnalysis(
        uow_factory=_factory(uow),
        provider=MockLLMProvider(),
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        clock=StaticClock(),
        id_generator=SequenceIds(("run-1", "stage-1", "event-1", "claim-1")),
    )

    result = service.execute(principal=_principal(), case_id="case-1", command=command)

    assert result.run.id == "run-1"
    assert result.run.status is AnalysisRunStatus.QUEUED
    assert result.run.execution_mode is AnalysisExecutionMode.PRIMARY
    uow.analysis_runs.lock_admission_counts.assert_called_once_with(tenant_id="tenant-1")
    uow.analysis_runs.add.assert_called_once()
    uow.stage_runs.add.assert_called_once()
    persisted_event = uow.outbox.add.call_args.kwargs["event"]
    assert persisted_event.aggregate_type == "analysis_run"
    assert set(AnalysisRequestedEvent.model_validate(persisted_event.payload).queue_payload()) == {
        "event_id",
        "tenant_id",
        "case_id",
        "analysis_run_id",
        "stage_run_id",
        "correlation_id",
    }
    uow.commit.assert_called_once()


def test_canonical_hash_ignores_retry_correlation_but_includes_case() -> None:
    first = StartTextAnalysisCommand(
        pipeline=AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION,
        pipeline_version=TEXT_EXTRACTION_PIPELINE_VERSION,
        idempotency_key="key-a",
        correlation_id="correlation-a",
    )
    second = first.model_copy(
        update={"idempotency_key": "key-b", "correlation_id": "correlation-b"}
    )

    assert canonical_analysis_request_hash(case_id="case-1", command=first) == (
        canonical_analysis_request_hash(case_id="case-1", command=second)
    )
    assert canonical_analysis_request_hash(case_id="case-1", command=first) == (
        "99453e020aa62209b159a226f538d8a27cb08ee12836cdbcb543c68b98b614c7"
    )
    assert canonical_analysis_request_hash(case_id="case-1", command=first) != (
        canonical_analysis_request_hash(case_id="case-2", command=first)
    )


def test_shadow_mode_is_persisted_and_is_an_idempotency_dimension() -> None:
    uow = _uow()
    uow.cases.get.return_value = _case()
    uow.request_idempotency.claim.side_effect = _claim_new_analysis
    primary = StartTextAnalysisCommand(
        pipeline=AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION,
        pipeline_version=TEXT_EXTRACTION_PIPELINE_VERSION,
        idempotency_key="idempotency-1",
        correlation_id="correlation-1",
    )
    shadow = primary.model_copy(update={"execution_mode": AnalysisExecutionMode.SHADOW})
    service = StartTextAnalysis(
        uow_factory=_factory(uow),
        provider=MockLLMProvider(),
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        clock=StaticClock(),
        id_generator=SequenceIds(("run-1", "stage-1", "event-1", "claim-1")),
    )

    result = service.execute(principal=_principal(), case_id="case-1", command=shadow)

    assert result.run.execution_mode is AnalysisExecutionMode.SHADOW
    assert canonical_analysis_request_hash(case_id="case-1", command=shadow) != (
        canonical_analysis_request_hash(case_id="case-1", command=primary)
    )


def test_new_analysis_is_rejected_at_serialized_nonterminal_limit() -> None:
    uow = _uow()
    uow.cases.get.return_value = _case()
    uow.request_idempotency.claim.side_effect = _claim_new_analysis
    uow.analysis_runs.lock_admission_counts.return_value = AnalysisAdmissionCounts(
        global_nonterminal=4,
        tenant_nonterminal=2,
    )
    service = StartTextAnalysis(
        uow_factory=_factory(uow),
        provider=MockLLMProvider(),
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        clock=StaticClock(),
        id_generator=SequenceIds(("run-1", "stage-1", "event-1", "claim-1")),
    )

    with pytest.raises(AnalysisAdmissionLimitExceededError) as raised:
        service.execute(
            principal=_principal(),
            case_id="case-1",
            command=StartTextAnalysisCommand(
                pipeline=AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION,
                pipeline_version=TEXT_EXTRACTION_PIPELINE_VERSION,
                idempotency_key="idempotency-1",
                correlation_id="correlation-1",
            ),
        )

    assert raised.value.global_limit == 4
    assert raised.value.tenant_limit == 4
    uow.analysis_runs.add.assert_not_called()
    uow.commit.assert_not_called()


def test_existing_idempotent_replay_bypasses_full_admission_budget() -> None:
    uow = _uow()
    uow.cases.get.return_value = _case()
    command = StartTextAnalysisCommand(
        pipeline=AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION,
        pipeline_version=TEXT_EXTRACTION_PIPELINE_VERSION,
        idempotency_key="idempotency-1",
        correlation_id="correlation-1",
    )
    request_hash = canonical_analysis_request_hash(case_id="case-1", command=command)
    uow.request_idempotency.claim.return_value = AnalysisRequestIdempotencyClaim(
        claimed=False,
        record=AnalysisRequestIdempotencyRecord(
            id="existing-claim",
            tenant_id="tenant-1",
            case_id="case-1",
            idempotency_key="idempotency-1",
            request_hash=request_hash,
            analysis_run_id="run-1",
            created_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        ),
    )
    uow.analysis_runs.get.return_value = _run(AnalysisRunStatus.QUEUED)
    uow.analysis_runs.lock_admission_counts.side_effect = AssertionError(
        "replay must return before admission"
    )
    service = StartTextAnalysis(
        uow_factory=_factory(uow),
        provider=MockLLMProvider(),
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        clock=StaticClock(),
        id_generator=SequenceIds(("unused-run", "unused-stage", "unused-event", "unused-claim")),
    )

    result = service.execute(principal=_principal(), case_id="case-1", command=command)

    assert result.replayed is True
    assert result.run.id == "run-1"
    uow.analysis_runs.lock_admission_counts.assert_not_called()
    uow.analysis_runs.add.assert_not_called()


def test_v2_start_snapshots_active_route_only_after_new_idempotency_claim() -> None:
    uow = _uow()
    uow.cases.get.return_value = _case()
    uow.request_idempotency.claim.side_effect = _claim_new_analysis
    resolver = MagicMock()
    resolver.execute.return_value.route_plan.id = "route-plan-1"
    service = StartTextAnalysis(
        uow_factory=_factory(uow),
        provider=MockLLMProvider(),
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        prompt_v2=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
        clock=StaticClock(),
        id_generator=SequenceIds(("run-1", "stage-1", "event-1", "claim-1")),
        model_route_resolver=cast(ActiveModelRouteResolver, resolver),
    )
    command = StartTextAnalysisCommand(
        pipeline=AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION,
        pipeline_version=TEXT_EXTRACTION_V2_PIPELINE_VERSION,
        execution_mode=AnalysisExecutionMode.SHADOW,
        idempotency_key="idempotency-v2-route",
        correlation_id="correlation-v2-route",
    )

    service.execute(principal=_principal(), case_id="case-1", command=command)

    resolver.execute.assert_called_once_with(
        tenant_id="tenant-1",
        task=ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
        execution_mode=AnalysisExecutionMode.SHADOW,
    )
    stage = uow.stage_runs.add.call_args.kwargs["stage_run"]
    assert stage.model_route_plan_id == "route-plan-1"


def test_v2_idempotent_replay_returns_before_route_resolution_or_provider_call() -> None:
    uow = _uow()
    uow.cases.get.return_value = _case()
    command = StartTextAnalysisCommand(
        pipeline=AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION,
        pipeline_version=TEXT_EXTRACTION_V2_PIPELINE_VERSION,
        idempotency_key="idempotency-v2-route",
        correlation_id="correlation-v2-route",
    )
    request_hash = canonical_analysis_request_hash(case_id="case-1", command=command)
    uow.request_idempotency.claim.return_value = AnalysisRequestIdempotencyClaim(
        claimed=False,
        record=AnalysisRequestIdempotencyRecord(
            id="existing-claim",
            tenant_id="tenant-1",
            case_id="case-1",
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
            analysis_run_id="run-1",
            created_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        ),
    )
    uow.analysis_runs.get.return_value = _run(AnalysisRunStatus.QUEUED).model_copy(
        update={"pipeline_version": TEXT_EXTRACTION_V2_PIPELINE_VERSION}
    )
    resolver = MagicMock()
    resolver.execute.side_effect = AssertionError("replay must not resolve the current route")
    provider = MockLLMProvider()
    provider.extract_text_v2 = MagicMock(wraps=provider.extract_text_v2)
    service = StartTextAnalysis(
        uow_factory=_factory(uow),
        provider=provider,
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        prompt_v2=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
        clock=StaticClock(),
        id_generator=SequenceIds(("unused-run", "unused-stage", "unused-event", "unused-claim")),
        model_route_resolver=cast(ActiveModelRouteResolver, resolver),
    )

    result = service.execute(principal=_principal(), case_id="case-1", command=command)

    assert result.replayed is True
    resolver.execute.assert_not_called()
    provider.extract_text_v2.assert_not_called()
    uow.stage_runs.add.assert_not_called()


def test_execute_text_extraction_persists_success_with_fenced_completion() -> None:
    claimed = _stage()
    claim_uow = _uow()
    completion_uow = _uow()
    _configure_claim_uow(claim_uow, stage=claimed)
    _configure_completion_uow(completion_uow, stage=claimed)
    service = _analysis_service(
        uow_factory=_factory(claim_uow, completion_uow),
        provider=MockLLMProvider(),
        ids=("claim-1", "attempt-1", "result-1"),
    )

    result = service.execute(command=_command())

    assert result.disposition is ExecutionDisposition.SUCCEEDED
    assert result.status is AnalysisStageStatus.SUCCEEDED
    completion_uow.extraction_results.add.assert_called_once()
    completion_uow.stage_runs.transition_if_claimed.assert_called_once()
    completion_uow.stage_attempts.finalize_if_claimed.assert_called_once()
    completion_uow.commit.assert_called_once()


def test_execute_text_extraction_is_noop_after_terminal_completion() -> None:
    uow = _uow()
    uow.analysis_runs.get_for_update.return_value = _run(AnalysisRunStatus.SUCCEEDED)
    uow.stage_runs.get.return_value = _stage(
        AnalysisStageStatus.SUCCEEDED,
        claim_token=None,
    )
    provider = MockLLMProvider()
    service = _analysis_service(
        uow_factory=_factory(uow),
        provider=provider,
        ids=("unused-claim",),
    )

    result = service.execute(command=_command())

    assert result.disposition is ExecutionDisposition.NOOP
    assert result.status is AnalysisStageStatus.SUCCEEDED
    uow.stage_runs.claim_for_execution.assert_not_called()


def test_terminal_stage_redelivery_reconciles_orphaned_running_parent() -> None:
    terminal_stage = _stage(
        AnalysisStageStatus.SUCCEEDED,
        claim_token=None,
    )
    uow = _uow()
    uow.analysis_runs.get_for_update.return_value = _run()
    uow.stage_runs.get.return_value = terminal_stage
    uow.stage_runs.list.return_value = (terminal_stage,)
    uow.analysis_runs.transition.return_value = _run(AnalysisRunStatus.SUCCEEDED)
    provider = MockLLMProvider()
    service = _analysis_service(
        uow_factory=_factory(uow),
        provider=provider,
        ids=("unused-claim",),
    )

    result = service.execute(command=_command())

    assert result.disposition is ExecutionDisposition.NOOP
    assert result.status is AnalysisStageStatus.SUCCEEDED
    uow.analysis_runs.transition.assert_called_once_with(
        tenant_id="tenant-1",
        analysis_run_id="run-1",
        expected_status=AnalysisRunStatus.RUNNING,
        target_status=AnalysisRunStatus.SUCCEEDED,
        now=NOW,
        failure=None,
    )
    uow.stage_runs.claim_for_execution.assert_not_called()
    uow.commit.assert_called_once()


def test_active_claim_duplicate_schedules_durable_lease_expiry_wakeup() -> None:
    active_stage = _stage()
    uow = _uow()
    _configure_claim_uow(uow, stage=active_stage)
    uow.stage_runs.claim_for_execution.return_value = None
    service = _analysis_service(
        uow_factory=_factory(uow),
        provider=MockLLMProvider(),
        ids=("duplicate-claim-token", "lease-recovery-event"),
    )

    result = service.execute(command=_command())

    assert result.disposition is ExecutionDisposition.NOOP
    assert result.status is AnalysisStageStatus.RUNNING
    recovery_event = uow.outbox.add.call_args.kwargs["event"]
    assert recovery_event.id == "lease-recovery-event"
    assert recovery_event.available_at == active_stage.claim_expires_at
    assert set(AnalysisRequestedEvent.model_validate(recovery_event.payload).queue_payload()) == {
        "event_id",
        "tenant_id",
        "case_id",
        "analysis_run_id",
        "stage_run_id",
        "correlation_id",
    }
    uow.commit.assert_called_once()


def test_expired_final_worker_lease_fails_without_starting_an_unbounded_attempt() -> None:
    expired_stage = _stage(attempt_count=3).model_copy(
        update={"claim_expires_at": NOW - timedelta(seconds=1)}
    )
    uow = _uow()
    uow.analysis_runs.get_for_update.return_value = _run()
    uow.stage_runs.get.return_value = expired_stage
    uow.extraction_results.get_by_run.return_value = None
    uow.stage_attempts.finalize_if_claimed.return_value = object()
    uow.stage_runs.transition_if_claimed.return_value = expired_stage.model_copy(
        update={"status": AnalysisStageStatus.FAILED}
    )
    uow.analysis_runs.transition.return_value = _run(AnalysisRunStatus.FAILED)
    provider = MockLLMProvider()
    service = _analysis_service(
        uow_factory=_factory(uow),
        provider=provider,
        ids=("unused-new-claim",),
        max_attempts=3,
    )

    result = service.execute(command=_command())

    assert result.disposition is ExecutionDisposition.FAILED
    assert result.status is AnalysisStageStatus.FAILED
    uow.stage_runs.claim_for_execution.assert_not_called()
    uow.cases.get.assert_not_called()
    attempt_transition = uow.stage_attempts.finalize_if_claimed.call_args.kwargs
    assert attempt_transition["target_status"] is AnalysisAttemptStatus.ABANDONED
    assert attempt_transition["failure"].code == "ANALYSIS_MAX_RETRIES_EXCEEDED"
    stage_transition = uow.stage_runs.transition_if_claimed.call_args.kwargs
    assert stage_transition["target_status"] is AnalysisStageStatus.FAILED
    assert stage_transition["failure"].retryable is False
    uow.commit.assert_called_once()


def test_transient_provider_error_schedules_future_outbox_in_same_transaction() -> None:
    claimed = _stage()
    claim_uow = _uow()
    failure_uow = _uow()
    _configure_claim_uow(claim_uow, stage=claimed)
    _configure_completion_uow(failure_uow, stage=claimed)
    service = _analysis_service(
        uow_factory=_factory(claim_uow, failure_uow),
        provider=MockLLMProvider(mode=MockProviderMode.TRANSIENT_ERROR),
        ids=("claim-1", "attempt-1", "retry-event-1"),
    )

    result = service.execute(command=_command())

    assert result.disposition is ExecutionDisposition.RETRY_WAITING
    assert result.retry_at == NOW + timedelta(seconds=5)
    assert failure_uow.stage_runs.transition_if_claimed.call_args.kwargs["target_status"] is (
        AnalysisStageStatus.RETRY_WAITING
    )
    retry_event = failure_uow.outbox.add.call_args.kwargs["event"]
    assert retry_event.available_at == result.retry_at
    assert retry_event.status is OutboxStatus.PENDING
    failure_uow.commit.assert_called_once()


@pytest.mark.parametrize(
    ("mode", "max_attempts", "expected_code"),
    [
        (MockProviderMode.TRANSIENT_ERROR, 1, "ANALYSIS_MAX_RETRIES_EXCEEDED"),
        (MockProviderMode.PERMANENT_ERROR, 3, "LLM_PROVIDER_REQUEST_REJECTED"),
    ],
)
def test_provider_permanent_or_exhausted_error_fails_without_new_outbox(
    mode: MockProviderMode,
    max_attempts: int,
    expected_code: str,
) -> None:
    claimed = _stage()
    claim_uow = _uow()
    failure_uow = _uow()
    _configure_claim_uow(claim_uow, stage=claimed)
    _configure_completion_uow(failure_uow, stage=claimed)
    service = _analysis_service(
        uow_factory=_factory(claim_uow, failure_uow),
        provider=MockLLMProvider(mode=mode),
        ids=("claim-1", "attempt-1"),
        max_attempts=max_attempts,
    )

    result = service.execute(command=_command())

    assert result.disposition is ExecutionDisposition.FAILED
    transition = failure_uow.stage_runs.transition_if_claimed.call_args.kwargs
    assert transition["target_status"] is AnalysisStageStatus.FAILED
    assert transition["failure"].code == expected_code
    failure_uow.outbox.add.assert_not_called()


def test_v2_release_guard_failure_terminalizes_without_calling_provider() -> None:
    prompt = PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2
    claimed = _stage().model_copy(
        update={
            "prompt_name": prompt.name,
            "prompt_version": prompt.version,
            "prompt_content_hash": prompt.content_hash,
            "input_schema_version": prompt.input_schema_version,
            "output_schema_version": prompt.output_schema_version,
        }
    )
    claim_uow = _uow()
    failure_uow = _uow()
    _configure_claim_uow(claim_uow, stage=claimed)
    claim_uow.extraction_results_v2.get_by_run.return_value = None
    _configure_completion_uow(failure_uow, stage=claimed)
    failure_uow.extraction_results_v2.get_by_run.return_value = None
    provider = MockLLMProvider()
    provider.extract_text_v2 = MagicMock(wraps=provider.extract_text_v2)
    guard = MagicMock()
    guard.execute.side_effect = ActiveModelReleaseRequiredError()
    service = _analysis_service(
        uow_factory=_factory(claim_uow, failure_uow),
        provider=provider,
        ids=("claim-1", "attempt-1"),
        model_release_guard=cast(ModelReleaseExecutionGuard, guard),
    )

    result = service.execute(command=_command())

    assert result.disposition is ExecutionDisposition.FAILED
    provider.extract_text_v2.assert_not_called()
    transition = failure_uow.stage_runs.transition_if_claimed.call_args.kwargs
    assert transition["failure"].code == "ACTIVE_MODEL_RELEASE_REQUIRED"
    assert transition["failure"].retryable is False
    failure_uow.outbox.add.assert_not_called()


@pytest.mark.parametrize(
    ("guard_error", "expected_code"),
    [
        (PinnedModelRoutePlanRequiredError(), "PINNED_MODEL_ROUTE_PLAN_REQUIRED"),
        (ModelReleaseIdentityMismatchError(), "MODEL_RELEASE_IDENTITY_MISMATCH"),
    ],
)
def test_v2_pinned_route_guard_failure_terminalizes_without_calling_provider(
    guard_error: Exception,
    expected_code: str,
) -> None:
    prompt = PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2
    claimed = _stage().model_copy(
        update={
            "model_route_plan_id": "route-plan-1",
            "prompt_name": prompt.name,
            "prompt_version": prompt.version,
            "prompt_content_hash": prompt.content_hash,
            "input_schema_version": prompt.input_schema_version,
            "output_schema_version": prompt.output_schema_version,
        }
    )
    claim_uow = _uow()
    failure_uow = _uow()
    _configure_claim_uow(claim_uow, stage=claimed)
    claim_uow.extraction_results_v2.get_by_run.return_value = None
    _configure_completion_uow(failure_uow, stage=claimed)
    failure_uow.extraction_results_v2.get_by_run.return_value = None
    provider = MockLLMProvider()
    provider.extract_text_v2 = MagicMock(wraps=provider.extract_text_v2)
    guard = MagicMock()
    guard.execute.side_effect = guard_error
    service = _analysis_service(
        uow_factory=_factory(claim_uow, failure_uow),
        provider=provider,
        ids=("claim-1", "attempt-1"),
        model_route_guard=cast(PinnedModelRouteExecutionGuard, guard),
    )

    result = service.execute(command=_command())

    assert result.disposition is ExecutionDisposition.FAILED
    guard.execute.assert_called_once_with(
        tenant_id="tenant-1",
        route_plan_id="route-plan-1",
        task=ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
        execution_mode=AnalysisExecutionMode.PRIMARY,
    )
    provider.extract_text_v2.assert_not_called()
    transition = failure_uow.stage_runs.transition_if_claimed.call_args.kwargs
    assert transition["failure"].code == expected_code
    assert transition["failure"].retryable is False


def test_retry_delay_is_deterministic_exponential_and_bounded() -> None:
    base = timedelta(seconds=2)
    maximum = timedelta(seconds=10)
    first = deterministic_retry_delay(
        attempt_number=1,
        seed="stage-1",
        base=base,
        maximum=maximum,
        jitter_ratio=0.2,
    )
    second = deterministic_retry_delay(
        attempt_number=2,
        seed="stage-1",
        base=base,
        maximum=maximum,
        jitter_ratio=0.2,
    )
    capped = deterministic_retry_delay(
        attempt_number=20,
        seed="stage-1",
        base=base,
        maximum=maximum,
        jitter_ratio=0.2,
    )

    assert first == deterministic_retry_delay(
        attempt_number=1,
        seed="stage-1",
        base=base,
        maximum=maximum,
        jitter_ratio=0.2,
    )
    assert second > first
    assert capped <= timedelta(seconds=10)


def test_dispatch_outbox_publishes_exact_six_key_payload_and_marks_published() -> None:
    claim_uow = _uow()
    mark_uow = _uow()
    event = _outbox_event()
    claim_uow.outbox.claim_batch.return_value = (event,)
    mark_uow.outbox.mark_published.return_value = event.model_copy(
        update={
            "status": OutboxStatus.PUBLISHED,
            "claim_token": None,
            "claimed_at": None,
            "claimed_by": None,
            "published_at": NOW,
        }
    )
    queue = RecordingQueue()
    service = DispatchOutbox(
        uow_factory=_factory(claim_uow, mark_uow),
        queue=cast(MessageQueue, queue),
        clock=StaticClock(),
        id_generator=SequenceIds(("dispatch-claim",)),
        claimed_by="dispatcher-1",
    )

    result = service.execute()

    assert result.model_dump() == {"claimed": 1, "published": 1, "retried": 0, "failed": 0}
    assert len(queue.messages) == 1
    topic, payload, correlation_id = queue.messages[0]
    assert topic == "analysis.requested.v1"
    assert correlation_id == "correlation-1"
    assert set(payload) == {
        "event_id",
        "tenant_id",
        "case_id",
        "analysis_run_id",
        "stage_run_id",
        "correlation_id",
    }


def test_dispatch_outbox_releases_transient_publish_failure_with_backoff() -> None:
    claim_uow = _uow()
    release_uow = _uow()
    event = _outbox_event()
    claim_uow.outbox.claim_batch.return_value = (event,)
    release_uow.outbox.release_for_retry.return_value = event.model_copy(
        update={
            "status": OutboxStatus.PENDING,
            "claim_token": None,
            "claimed_at": None,
            "claimed_by": None,
        }
    )
    service = DispatchOutbox(
        uow_factory=_factory(claim_uow, release_uow),
        queue=cast(MessageQueue, RecordingQueue(fail=True)),
        clock=StaticClock(),
        id_generator=SequenceIds(("dispatch-claim",)),
        claimed_by="dispatcher-1",
        retry_jitter_ratio=0,
    )

    result = service.execute()

    assert result.retried == 1
    release = release_uow.outbox.release_for_retry.call_args.kwargs
    assert release["available_at"] == NOW + timedelta(seconds=5)
    assert "broker unavailable" not in release["last_error"]


def test_dispatch_outbox_exhaustion_fails_event_and_queued_run_and_stage() -> None:
    claim_uow = _uow()
    failure_uow = _uow()
    event = _outbox_event(attempt_count=1)
    claim_uow.outbox.claim_batch.return_value = (event,)
    failure_uow.outbox.mark_failed.return_value = event.model_copy(
        update={
            "status": OutboxStatus.FAILED,
            "claim_token": None,
            "claimed_at": None,
            "claimed_by": None,
            "last_error": "Message publication failed permanently.",
        }
    )
    failure_uow.analysis_runs.get_for_update.return_value = _run(AnalysisRunStatus.QUEUED)
    failure_uow.stage_runs.get.return_value = _stage(
        AnalysisStageStatus.QUEUED,
        attempt_count=0,
        claim_token=None,
    )
    failure_uow.stage_runs.list.return_value = (
        _stage(AnalysisStageStatus.FAILED, attempt_count=0, claim_token=None),
    )
    service = DispatchOutbox(
        uow_factory=_factory(claim_uow, failure_uow),
        queue=cast(MessageQueue, RecordingQueue(fail=True)),
        clock=StaticClock(),
        id_generator=SequenceIds(("dispatch-claim",)),
        claimed_by="dispatcher-1",
        max_attempts=1,
    )

    result = service.execute()

    assert result.failed == 1
    run_transition = failure_uow.analysis_runs.transition.call_args.kwargs
    stage_transition = failure_uow.stage_runs.transition.call_args.kwargs
    assert run_transition["target_status"] is AnalysisRunStatus.FAILED
    assert stage_transition["target_status"] is AnalysisStageStatus.FAILED
    assert run_transition["failure"] == AnalysisFailure(
        code="OUTBOX_DISPATCH_FAILED",
        message="The analysis request could not be dispatched.",
        retryable=False,
    )
