"""Opt-in PostgreSQL E2E tests for Analysis application and Outbox workflows."""

import os
from collections.abc import Generator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from alembic import command as alembic_command
from app.adapters.llm.mock import MockLLMProvider
from app.adapters.persistence.engine import clear_engine_cache, get_engine
from app.adapters.persistence.models import (
    AnalysisRequestIdempotencyRecordModel,
    AnalysisRunModel,
    AnalysisStageAttemptModel,
    AnalysisStageRunModel,
    CaseModel,
    LLMExtractionResultModel,
    OutboxEventModel,
    TenantModel,
    UserModel,
)
from app.adapters.persistence.unit_of_work import (
    SQLAlchemyAnalysisUnitOfWork,
    SQLAlchemyAnalysisUnitOfWorkFactory,
    create_analysis_unit_of_work_factory,
)
from app.adapters.runtime import Uuid4Generator
from app.application.analysis import (
    ExecuteTextExtraction,
    ExecuteTextExtractionCommand,
    ExecuteTextExtractionResult,
    ExecutionDisposition,
    GetAnalysisRun,
    StartTextAnalysis,
    StartTextAnalysisCommand,
    StartTextAnalysisResult,
)
from app.application.outbox import DispatchOutbox, DispatchOutboxResult
from app.bootstrap.settings import Settings
from app.domains.product_defect_cs.prompts import PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT
from app.platform.analysis import (
    TEXT_EXTRACTION_PIPELINE_VERSION,
    AnalysisAttemptStatus,
    AnalysisPipeline,
    AnalysisRunNotFoundError,
    AnalysisRunStatus,
    AnalysisStageAttempt,
    AnalysisStageStatus,
    LLMTextExtractionRequest,
    LLMTextExtractionResponse,
    MockProviderMode,
    OutboxEvent,
    OutboxStatus,
    PromptManifest,
)
from app.platform.case import Case, RequestedAction
from app.platform.errors import CaseNotFoundError, IdempotencyKeyReusedError
from app.platform.tenant import Principal, Role
from app.ports.analysis_repository import OutboxEventRepository

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 26, 6, 0, tzinfo=UTC)
QUEUE_PAYLOAD_KEYS = {
    "event_id",
    "tenant_id",
    "case_id",
    "analysis_run_id",
    "stage_run_id",
    "correlation_id",
}


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value

    def set(self, value: datetime) -> None:
        self._value = value

    def advance(self, delta: timedelta) -> None:
        self._value += delta


@dataclass(frozen=True, slots=True)
class PublishedMessage:
    topic: str
    payload: dict[str, object]
    correlation_id: str


class RecordingQueue:
    """Network-free queue that can model an ambiguous accepted publish."""

    def __init__(
        self,
        *,
        fail_on_calls: frozenset[int] = frozenset(),
        record_before_failure: bool = False,
    ) -> None:
        self._fail_on_calls = fail_on_calls
        self._record_before_failure = record_before_failure
        self.calls = 0
        self.messages: list[PublishedMessage] = []

    def publish(
        self,
        *,
        topic: str,
        payload: Mapping[str, object],
        correlation_id: str,
    ) -> str:
        self.calls += 1
        normalized = dict(payload)
        if set(normalized) != QUEUE_PAYLOAD_KEYS:
            raise AssertionError("the dispatcher did not publish exactly six reference IDs")
        if normalized["correlation_id"] != correlation_id:
            raise AssertionError("the queue correlation ID does not match its payload")
        message = PublishedMessage(
            topic=topic,
            payload=normalized,
            correlation_id=correlation_id,
        )
        should_fail = self.calls in self._fail_on_calls
        if self._record_before_failure or not should_fail:
            self.messages.append(message)
        if should_fail:
            raise RuntimeError("synthetic broker acknowledgement failure")
        event_id = normalized["event_id"]
        assert isinstance(event_id, str)
        return event_id

    def is_ready(self) -> bool:
        return True


class NoCallMockLLMProvider(MockLLMProvider):
    """Fail the test if an exhausted expired lease reaches the provider."""

    def __init__(self) -> None:
        super().__init__()
        self.extract_text_calls = 0

    def extract_text(
        self,
        request: LLMTextExtractionRequest,
        prompt: PromptManifest,
    ) -> LLMTextExtractionResponse:
        del request, prompt
        self.extract_text_calls += 1
        raise AssertionError("an exhausted expired lease must not call the provider")


class SyntheticStartWriteError(RuntimeError):
    pass


class FailingOutboxRepository:
    """Inject a write failure after Start has staged its other graph records."""

    def add(self, *, tenant_id: str, event: OutboxEvent) -> None:
        del tenant_id, event
        raise SyntheticStartWriteError("synthetic outbox write failure")


class FaultingAnalysisUnitOfWorkFactory:
    def __init__(self, delegate: SQLAlchemyAnalysisUnitOfWorkFactory) -> None:
        self._delegate = delegate

    def __call__(self) -> SQLAlchemyAnalysisUnitOfWork:
        unit_of_work = self._delegate()
        unit_of_work.outbox = cast(OutboxEventRepository, FailingOutboxRepository())
        return unit_of_work


@pytest.fixture(scope="module")
def application_engine() -> Generator[Engine, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test Analysis application E2E")

    settings = Settings()
    database_url = settings.database_url_value
    if not database_url:
        pytest.fail("DATABASE_URL is required for Analysis application E2E tests")

    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    alembic_command.upgrade(config, "head")

    engine = get_engine(settings)
    try:
        yield engine
    finally:
        clear_engine_cache()


@dataclass(frozen=True, slots=True)
class ApplicationContext:
    engine: Engine
    factory: SQLAlchemyAnalysisUnitOfWorkFactory
    principal_a: Principal
    principal_b: Principal
    case_a: Case
    conflict_case_a: Case
    case_b: Case


def _case(*, tenant_id: str, user_id: str, suffix: str) -> Case:
    return Case.create(
        case_id=str(uuid4()),
        tenant_id=tenant_id,
        order_ref=f"ORD-{suffix}",
        product_ref=f"SKU-{suffix}",
        customer_message="상품 옆면이 찌그러지고 누액이 있어 교환을 요청합니다.",
        requested_action=RequestedAction.EXCHANGE,
        attributes={"source": "synthetic-integration"},
        created_by=user_id,
        now=NOW,
    )


@pytest.fixture
def application_context(
    application_engine: Engine,
) -> Generator[ApplicationContext, None, None]:
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    user_a = str(uuid4())
    user_b = str(uuid4())
    with Session(application_engine) as session:
        session.add_all(
            [
                TenantModel(id=UUID(tenant_a), slug=f"analysis-{tenant_a}", name="Tenant A"),
                TenantModel(id=UUID(tenant_b), slug=f"analysis-{tenant_b}", name="Tenant B"),
                UserModel(
                    id=UUID(user_a),
                    tenant_id=UUID(tenant_a),
                    email=f"reviewer-{user_a}@example.test",
                    password_hash="synthetic-password-hash",
                    display_name="Reviewer A",
                ),
                UserModel(
                    id=UUID(user_b),
                    tenant_id=UUID(tenant_b),
                    email=f"reviewer-{user_b}@example.test",
                    password_hash="synthetic-password-hash",
                    display_name="Reviewer B",
                ),
            ]
        )
        session.commit()

    principal_a = Principal(
        user_id=user_a,
        tenant_id=tenant_a,
        email=f"reviewer-{user_a}@example.test",
        display_name="Reviewer A",
        roles=frozenset({Role.REVIEWER}),
    )
    principal_b = Principal(
        user_id=user_b,
        tenant_id=tenant_b,
        email=f"reviewer-{user_b}@example.test",
        display_name="Reviewer B",
        roles=frozenset({Role.REVIEWER}),
    )
    case_a = _case(tenant_id=tenant_a, user_id=user_a, suffix="A-1")
    conflict_case_a = _case(tenant_id=tenant_a, user_id=user_a, suffix="A-2")
    case_b = _case(tenant_id=tenant_b, user_id=user_b, suffix="B-1")
    factory = create_analysis_unit_of_work_factory(application_engine)
    with factory() as unit_of_work:
        for case in (case_a, conflict_case_a, case_b):
            unit_of_work.cases.add(tenant_id=case.tenant_id, case=case)
        unit_of_work.commit()

    context = ApplicationContext(
        engine=application_engine,
        factory=factory,
        principal_a=principal_a,
        principal_b=principal_b,
        case_a=case_a,
        conflict_case_a=conflict_case_a,
        case_b=case_b,
    )
    try:
        yield context
    finally:
        tenant_ids = [UUID(tenant_a), UUID(tenant_b)]
        with application_engine.begin() as connection:
            connection.execute(
                delete(OutboxEventModel).where(OutboxEventModel.tenant_id.in_(tenant_ids))
            )
            connection.execute(
                delete(AnalysisRequestIdempotencyRecordModel).where(
                    AnalysisRequestIdempotencyRecordModel.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(
                delete(LLMExtractionResultModel).where(
                    LLMExtractionResultModel.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(
                delete(AnalysisStageAttemptModel).where(
                    AnalysisStageAttemptModel.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(
                delete(AnalysisStageRunModel).where(AnalysisStageRunModel.tenant_id.in_(tenant_ids))
            )
            connection.execute(
                delete(AnalysisRunModel).where(AnalysisRunModel.tenant_id.in_(tenant_ids))
            )
            connection.execute(delete(CaseModel).where(CaseModel.tenant_id.in_(tenant_ids)))
            connection.execute(delete(UserModel).where(UserModel.tenant_id.in_(tenant_ids)))
            connection.execute(delete(TenantModel).where(TenantModel.id.in_(tenant_ids)))


def _start(
    context: ApplicationContext,
    *,
    case: Case,
    idempotency_key: str,
    clock: MutableClock,
) -> tuple[StartTextAnalysisCommand, StartTextAnalysisResult]:
    command = StartTextAnalysisCommand(
        pipeline=AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION,
        pipeline_version=TEXT_EXTRACTION_PIPELINE_VERSION,
        idempotency_key=idempotency_key,
        correlation_id=f"correlation-{idempotency_key}",
    )
    service = StartTextAnalysis(
        uow_factory=context.factory,
        provider=MockLLMProvider(),
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        clock=clock,
        id_generator=Uuid4Generator(),
    )
    result = service.execute(
        principal=context.principal_a,
        case_id=case.id,
        command=command,
    )
    return command, result


def _dispatch(
    context: ApplicationContext,
    *,
    queue: RecordingQueue,
    clock: MutableClock,
    max_attempts: int = 5,
) -> DispatchOutboxResult:
    return DispatchOutbox(
        uow_factory=context.factory,
        queue=queue,
        clock=clock,
        id_generator=Uuid4Generator(),
        claimed_by="integration-dispatcher",
        max_attempts=max_attempts,
        retry_base=timedelta(seconds=1),
        retry_max=timedelta(seconds=1),
        retry_jitter_ratio=0,
    ).execute()


def _execute(
    context: ApplicationContext,
    *,
    message: PublishedMessage,
    provider: MockLLMProvider,
    clock: MutableClock,
    max_attempts: int = 3,
) -> ExecuteTextExtractionResult:
    command = ExecuteTextExtractionCommand.model_validate(message.payload)
    return ExecuteTextExtraction(
        uow_factory=context.factory,
        provider=provider,
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        clock=clock,
        id_generator=Uuid4Generator(),
        claim_ttl=timedelta(minutes=5),
        max_attempts=max_attempts,
        retry_base=timedelta(seconds=2),
        retry_max=timedelta(seconds=2),
        retry_jitter_ratio=0,
    ).execute(command=command)


def test_start_is_atomic_replays_conflicts_and_hides_cross_tenant_run(
    application_context: ApplicationContext,
) -> None:
    clock = MutableClock(NOW)
    key = f"start-{uuid4()}"
    command, first = _start(
        application_context,
        case=application_context.case_a,
        idempotency_key=key,
        clock=clock,
    )
    run = first.run

    with Session(application_context.engine) as session:
        tenant_uuid = UUID(application_context.principal_a.tenant_id)
        run_uuid = UUID(run.id)
        assert (
            session.scalar(
                select(func.count())
                .select_from(AnalysisRunModel)
                .where(AnalysisRunModel.tenant_id == tenant_uuid, AnalysisRunModel.id == run_uuid)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(AnalysisStageRunModel)
                .where(
                    AnalysisStageRunModel.tenant_id == tenant_uuid,
                    AnalysisStageRunModel.analysis_run_id == run_uuid,
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(AnalysisRequestIdempotencyRecordModel)
                .where(
                    AnalysisRequestIdempotencyRecordModel.tenant_id == tenant_uuid,
                    AnalysisRequestIdempotencyRecordModel.analysis_run_id == run_uuid,
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEventModel)
                .where(
                    OutboxEventModel.tenant_id == tenant_uuid,
                    OutboxEventModel.aggregate_id == run_uuid,
                )
            )
            == 1
        )

    replay = StartTextAnalysis(
        uow_factory=application_context.factory,
        provider=MockLLMProvider(),
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        clock=clock,
        id_generator=Uuid4Generator(),
    ).execute(
        principal=application_context.principal_a,
        case_id=application_context.case_a.id,
        command=command.model_copy(update={"correlation_id": "replay-correlation"}),
    )
    assert replay.replayed is True
    assert replay.run == run

    with pytest.raises(IdempotencyKeyReusedError):
        _start(
            application_context,
            case=application_context.conflict_case_a,
            idempotency_key=key,
            clock=clock,
        )

    fault_key = f"atomic-rollback-{uuid4()}"
    with pytest.raises(SyntheticStartWriteError):
        StartTextAnalysis(
            uow_factory=FaultingAnalysisUnitOfWorkFactory(application_context.factory),
            provider=MockLLMProvider(),
            prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
            clock=clock,
            id_generator=Uuid4Generator(),
        ).execute(
            principal=application_context.principal_a,
            case_id=application_context.conflict_case_a.id,
            command=StartTextAnalysisCommand(
                pipeline=AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION,
                pipeline_version=TEXT_EXTRACTION_PIPELINE_VERSION,
                idempotency_key=fault_key,
                correlation_id="atomic-rollback-correlation",
            ),
        )

    with application_context.factory() as unit_of_work:
        assert (
            unit_of_work.analysis_runs.get(
                tenant_id=application_context.principal_b.tenant_id,
                case_id=application_context.case_b.id,
                analysis_run_id=run.id,
            )
            is None
        )

    reader = GetAnalysisRun(uow_factory=application_context.factory)
    with pytest.raises(AnalysisRunNotFoundError):
        reader.execute(
            principal=application_context.principal_b,
            case_id=application_context.case_b.id,
            analysis_run_id=run.id,
        )
    with pytest.raises(CaseNotFoundError):
        reader.execute(
            principal=application_context.principal_b,
            case_id=application_context.case_a.id,
            analysis_run_id=run.id,
        )

    with Session(application_context.engine) as session:
        tenant_uuid = UUID(application_context.principal_a.tenant_id)
        counts = {
            "runs": session.scalar(
                select(func.count())
                .select_from(AnalysisRunModel)
                .where(AnalysisRunModel.tenant_id == tenant_uuid)
            ),
            "stages": session.scalar(
                select(func.count())
                .select_from(AnalysisStageRunModel)
                .where(AnalysisStageRunModel.tenant_id == tenant_uuid)
            ),
            "idempotency": session.scalar(
                select(func.count())
                .select_from(AnalysisRequestIdempotencyRecordModel)
                .where(AnalysisRequestIdempotencyRecordModel.tenant_id == tenant_uuid)
            ),
            "outbox": session.scalar(
                select(func.count())
                .select_from(OutboxEventModel)
                .where(OutboxEventModel.tenant_id == tenant_uuid)
            ),
        }
        assert counts == {"runs": 1, "stages": 1, "idempotency": 1, "outbox": 1}
        assert (
            session.scalar(
                select(func.count())
                .select_from(AnalysisRequestIdempotencyRecordModel)
                .where(
                    AnalysisRequestIdempotencyRecordModel.tenant_id == tenant_uuid,
                    AnalysisRequestIdempotencyRecordModel.idempotency_key == fault_key,
                )
            )
            == 0
        )


def test_ambiguous_publish_releases_pending_then_duplicate_delivery_is_idempotent(
    application_context: ApplicationContext,
) -> None:
    clock = MutableClock(NOW)
    _command, started = _start(
        application_context,
        case=application_context.case_a,
        idempotency_key=f"success-{uuid4()}",
        clock=clock,
    )
    queue = RecordingQueue(fail_on_calls=frozenset({1}), record_before_failure=True)

    first_dispatch = _dispatch(application_context, queue=queue, clock=clock)
    assert first_dispatch.model_dump() == {
        "claimed": 1,
        "published": 0,
        "retried": 1,
        "failed": 0,
    }
    with Session(application_context.engine) as session:
        event = session.scalars(
            select(OutboxEventModel).where(OutboxEventModel.aggregate_id == UUID(started.run.id))
        ).one()
        assert event.status == OutboxStatus.PENDING.value
        assert event.attempt_count == 1
        assert event.available_at > clock.now()
        retry_at = event.available_at

    clock.set(retry_at)
    second_dispatch = _dispatch(application_context, queue=queue, clock=clock)
    assert second_dispatch.model_dump() == {
        "claimed": 1,
        "published": 1,
        "retried": 0,
        "failed": 0,
    }
    assert len(queue.messages) == 2
    assert queue.messages[0] == queue.messages[1]
    assert queue.messages[0].topic == "analysis.requested.v1"
    assert set(queue.messages[0].payload) == QUEUE_PAYLOAD_KEYS
    assert set(queue.messages[0].payload).isdisjoint(
        {"customer_message", "prompt", "raw_response", "jwt", "signed_url"}
    )

    clock.advance(timedelta(seconds=1))
    succeeded = _execute(
        application_context,
        message=queue.messages[0],
        provider=MockLLMProvider(),
        clock=clock,
    )
    duplicate = _execute(
        application_context,
        message=queue.messages[1],
        provider=MockLLMProvider(),
        clock=clock,
    )
    assert succeeded.disposition is ExecutionDisposition.SUCCEEDED
    assert duplicate.disposition is ExecutionDisposition.NOOP

    empty_dispatch = _dispatch(application_context, queue=queue, clock=clock)
    assert empty_dispatch.claimed == 0
    assert len(queue.messages) == 2
    with Session(application_context.engine) as session:
        run_uuid = UUID(started.run.id)
        assert (
            session.scalar(
                select(func.count())
                .select_from(LLMExtractionResultModel)
                .where(LLMExtractionResultModel.analysis_run_id == run_uuid)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(AnalysisStageAttemptModel)
                .where(AnalysisStageAttemptModel.analysis_run_id == run_uuid)
            )
            == 1
        )
        event = session.scalars(
            select(OutboxEventModel).where(OutboxEventModel.aggregate_id == run_uuid)
        ).one()
        assert event.status == OutboxStatus.PUBLISHED.value
        assert event.attempt_count == 2


def test_transient_provider_retry_dispatches_future_event_then_succeeds(
    application_context: ApplicationContext,
) -> None:
    clock = MutableClock(NOW)
    _command, started = _start(
        application_context,
        case=application_context.case_a,
        idempotency_key=f"transient-{uuid4()}",
        clock=clock,
    )
    queue = RecordingQueue()
    assert _dispatch(application_context, queue=queue, clock=clock).published == 1

    clock.advance(timedelta(seconds=1))
    transient = _execute(
        application_context,
        message=queue.messages[0],
        provider=MockLLMProvider(mode=MockProviderMode.TRANSIENT_ERROR),
        clock=clock,
        max_attempts=3,
    )
    assert transient.disposition is ExecutionDisposition.RETRY_WAITING
    assert transient.retry_at == clock.now() + timedelta(seconds=2)

    with Session(application_context.engine) as session:
        run_uuid = UUID(started.run.id)
        run = session.get(AnalysisRunModel, run_uuid)
        stage = session.scalars(
            select(AnalysisStageRunModel).where(AnalysisStageRunModel.analysis_run_id == run_uuid)
        ).one()
        retry_event = session.scalars(
            select(OutboxEventModel).where(
                OutboxEventModel.aggregate_id == run_uuid,
                OutboxEventModel.status == OutboxStatus.PENDING.value,
            )
        ).one()
        assert run is not None and run.status == AnalysisRunStatus.RETRY_WAITING.value
        assert stage.status == AnalysisStageStatus.RETRY_WAITING.value
        assert stage.next_attempt_at == transient.retry_at
        assert retry_event.available_at == transient.retry_at

    assert transient.retry_at is not None
    clock.set(transient.retry_at)
    assert _dispatch(application_context, queue=queue, clock=clock).published == 1
    assert len(queue.messages) == 2
    succeeded = _execute(
        application_context,
        message=queue.messages[1],
        provider=MockLLMProvider(),
        clock=clock,
        max_attempts=3,
    )
    assert succeeded.disposition is ExecutionDisposition.SUCCEEDED

    with Session(application_context.engine) as session:
        run_uuid = UUID(started.run.id)
        run = session.get(AnalysisRunModel, run_uuid)
        stage = session.scalars(
            select(AnalysisStageRunModel).where(AnalysisStageRunModel.analysis_run_id == run_uuid)
        ).one()
        attempts = session.scalars(
            select(AnalysisStageAttemptModel)
            .where(AnalysisStageAttemptModel.analysis_run_id == run_uuid)
            .order_by(AnalysisStageAttemptModel.attempt_number)
        ).all()
        assert run is not None and run.status == AnalysisRunStatus.SUCCEEDED.value
        assert stage.status == AnalysisStageStatus.SUCCEEDED.value
        assert stage.attempt_count == 2
        assert [attempt.status for attempt in attempts] == [
            AnalysisAttemptStatus.RETRY_WAITING.value,
            AnalysisAttemptStatus.SUCCEEDED.value,
        ]
        assert (
            session.scalar(
                select(func.count())
                .select_from(LLMExtractionResultModel)
                .where(LLMExtractionResultModel.analysis_run_id == run_uuid)
            )
            == 1
        )


def test_active_lease_redelivery_schedules_recovery_and_fences_late_worker(
    application_context: ApplicationContext,
) -> None:
    clock = MutableClock(NOW)
    _command, started = _start(
        application_context,
        case=application_context.case_a,
        idempotency_key=f"worker-lost-{uuid4()}",
        clock=clock,
    )
    queue = RecordingQueue()
    assert _dispatch(application_context, queue=queue, clock=clock).published == 1
    original_message = queue.messages[0]

    clock.advance(timedelta(seconds=1))
    original_claimed_at = clock.now()
    original_lease_expires_at = original_claimed_at + timedelta(seconds=5)
    original_claim_token = str(uuid4())
    with application_context.factory() as unit_of_work:
        run = unit_of_work.analysis_runs.get(
            tenant_id=application_context.principal_a.tenant_id,
            case_id=application_context.case_a.id,
            analysis_run_id=started.run.id,
        )
        stages = unit_of_work.stage_runs.list(
            tenant_id=application_context.principal_a.tenant_id,
            analysis_run_id=started.run.id,
        )
        assert run is not None and len(stages) == 1
        claimed = unit_of_work.stage_runs.claim_for_execution(
            tenant_id=application_context.principal_a.tenant_id,
            analysis_run_id=started.run.id,
            stage_run_id=stages[0].id,
            claim_token=original_claim_token,
            now=original_claimed_at,
            claim_expires_at=original_lease_expires_at,
        )
        assert claimed is not None
        assert (
            unit_of_work.analysis_runs.transition(
                tenant_id=application_context.principal_a.tenant_id,
                analysis_run_id=started.run.id,
                expected_status=AnalysisRunStatus.QUEUED,
                target_status=AnalysisRunStatus.RUNNING,
                now=original_claimed_at,
            )
            is not None
        )
        unit_of_work.stage_attempts.add(
            tenant_id=application_context.principal_a.tenant_id,
            attempt=AnalysisStageAttempt(
                id=str(uuid4()),
                tenant_id=application_context.principal_a.tenant_id,
                analysis_run_id=started.run.id,
                stage_run_id=claimed.id,
                attempt_number=1,
                status=AnalysisAttemptStatus.RUNNING,
                claim_token=original_claim_token,
                provider_name=claimed.provider_name,
                model_name=claimed.model_name,
                model_version=claimed.model_version,
                model_revision=claimed.model_revision,
                prompt_name=claimed.prompt_name,
                prompt_version=claimed.prompt_version,
                prompt_content_hash=claimed.prompt_content_hash,
                input_schema_version=claimed.input_schema_version,
                output_schema_version=claimed.output_schema_version,
                started_at=original_claimed_at,
                created_at=original_claimed_at,
            ),
        )
        unit_of_work.commit()

    clock.advance(timedelta(seconds=1))
    duplicate = _execute(
        application_context,
        message=original_message,
        provider=MockLLMProvider(),
        clock=clock,
    )
    assert duplicate.disposition is ExecutionDisposition.NOOP
    assert duplicate.status is AnalysisStageStatus.RUNNING

    with Session(application_context.engine) as session:
        run_uuid = UUID(started.run.id)
        recovery_events = session.scalars(
            select(OutboxEventModel).where(
                OutboxEventModel.aggregate_id == run_uuid,
                OutboxEventModel.status == OutboxStatus.PENDING.value,
            )
        ).all()
        assert len(recovery_events) == 1
        assert recovery_events[0].available_at == original_lease_expires_at
        assert recovery_events[0].attempt_count == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(AnalysisStageAttemptModel)
                .where(
                    AnalysisStageAttemptModel.analysis_run_id == run_uuid,
                    AnalysisStageAttemptModel.status == AnalysisAttemptStatus.RUNNING.value,
                )
            )
            == 1
        )

    clock.set(original_lease_expires_at + timedelta(milliseconds=1))
    assert _dispatch(application_context, queue=queue, clock=clock).published == 1
    assert len(queue.messages) == 2
    recovered = _execute(
        application_context,
        message=queue.messages[1],
        provider=MockLLMProvider(),
        clock=clock,
    )
    assert recovered.disposition is ExecutionDisposition.SUCCEEDED

    with Session(application_context.engine) as session:
        run_uuid = UUID(started.run.id)
        attempts = session.scalars(
            select(AnalysisStageAttemptModel)
            .where(AnalysisStageAttemptModel.analysis_run_id == run_uuid)
            .order_by(AnalysisStageAttemptModel.attempt_number)
        ).all()
        assert [attempt.status for attempt in attempts] == [
            AnalysisAttemptStatus.ABANDONED.value,
            AnalysisAttemptStatus.SUCCEEDED.value,
        ]
        assert attempts[0].failure_code == "ANALYSIS_ATTEMPT_LEASE_EXPIRED"
        stage = session.scalars(
            select(AnalysisStageRunModel).where(AnalysisStageRunModel.analysis_run_id == run_uuid)
        ).one()
        assert stage.status == AnalysisStageStatus.SUCCEEDED.value
        assert stage.attempt_count == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(LLMExtractionResultModel)
                .where(LLMExtractionResultModel.analysis_run_id == run_uuid)
            )
            == 1
        )

    late_at = clock.now() + timedelta(seconds=1)
    with application_context.factory() as unit_of_work:
        assert (
            unit_of_work.stage_runs.transition_if_claimed(
                tenant_id=application_context.principal_a.tenant_id,
                analysis_run_id=started.run.id,
                stage_run_id=claimed.id,
                claim_token=original_claim_token,
                target_status=AnalysisStageStatus.SUCCEEDED,
                now=late_at,
            )
            is None
        )
        assert (
            unit_of_work.stage_attempts.finalize_if_claimed(
                tenant_id=application_context.principal_a.tenant_id,
                stage_run_id=claimed.id,
                attempt_number=1,
                claim_token=original_claim_token,
                target_status=AnalysisAttemptStatus.SUCCEEDED,
                completed_at=late_at,
            )
            is None
        )


def test_expired_final_attempt_lease_fails_without_provider_or_retry(
    application_context: ApplicationContext,
) -> None:
    clock = MutableClock(NOW)
    _command, started = _start(
        application_context,
        case=application_context.case_a,
        idempotency_key=f"expired-final-attempt-{uuid4()}",
        clock=clock,
    )
    queue = RecordingQueue()
    assert _dispatch(application_context, queue=queue, clock=clock).published == 1
    original_message = queue.messages[0]

    clock.advance(timedelta(seconds=1))
    claimed_at = clock.now()
    lease_expires_at = claimed_at + timedelta(seconds=5)
    claim_token = str(uuid4())
    with application_context.factory() as unit_of_work:
        run = unit_of_work.analysis_runs.get(
            tenant_id=application_context.principal_a.tenant_id,
            case_id=application_context.case_a.id,
            analysis_run_id=started.run.id,
        )
        stages = unit_of_work.stage_runs.list(
            tenant_id=application_context.principal_a.tenant_id,
            analysis_run_id=started.run.id,
        )
        assert run is not None and len(stages) == 1
        claimed = unit_of_work.stage_runs.claim_for_execution(
            tenant_id=application_context.principal_a.tenant_id,
            analysis_run_id=started.run.id,
            stage_run_id=stages[0].id,
            claim_token=claim_token,
            now=claimed_at,
            claim_expires_at=lease_expires_at,
        )
        assert claimed is not None
        assert claimed.attempt_summary.attempt_count == 1
        assert (
            unit_of_work.analysis_runs.transition(
                tenant_id=application_context.principal_a.tenant_id,
                analysis_run_id=started.run.id,
                expected_status=AnalysisRunStatus.QUEUED,
                target_status=AnalysisRunStatus.RUNNING,
                now=claimed_at,
            )
            is not None
        )
        unit_of_work.stage_attempts.add(
            tenant_id=application_context.principal_a.tenant_id,
            attempt=AnalysisStageAttempt(
                id=str(uuid4()),
                tenant_id=application_context.principal_a.tenant_id,
                analysis_run_id=started.run.id,
                stage_run_id=claimed.id,
                attempt_number=1,
                status=AnalysisAttemptStatus.RUNNING,
                claim_token=claim_token,
                provider_name=claimed.provider_name,
                model_name=claimed.model_name,
                model_version=claimed.model_version,
                model_revision=claimed.model_revision,
                prompt_name=claimed.prompt_name,
                prompt_version=claimed.prompt_version,
                prompt_content_hash=claimed.prompt_content_hash,
                input_schema_version=claimed.input_schema_version,
                output_schema_version=claimed.output_schema_version,
                started_at=claimed_at,
                created_at=claimed_at,
            ),
        )
        unit_of_work.commit()

    clock.set(lease_expires_at + timedelta(milliseconds=1))
    provider = NoCallMockLLMProvider()
    failed = _execute(
        application_context,
        message=original_message,
        provider=provider,
        clock=clock,
        max_attempts=1,
    )
    assert failed.disposition is ExecutionDisposition.FAILED
    assert failed.status is AnalysisStageStatus.FAILED
    assert provider.extract_text_calls == 0
    assert len(queue.messages) == 1

    with Session(application_context.engine) as session:
        run_uuid = UUID(started.run.id)
        run = session.get(AnalysisRunModel, run_uuid)
        stage = session.scalars(
            select(AnalysisStageRunModel).where(AnalysisStageRunModel.analysis_run_id == run_uuid)
        ).one()
        attempts = session.scalars(
            select(AnalysisStageAttemptModel)
            .where(AnalysisStageAttemptModel.analysis_run_id == run_uuid)
            .order_by(AnalysisStageAttemptModel.attempt_number)
        ).all()
        outbox_events = session.scalars(
            select(OutboxEventModel).where(OutboxEventModel.aggregate_id == run_uuid)
        ).all()

        assert run is not None and run.status == AnalysisRunStatus.FAILED.value
        assert run.failure_code == "ANALYSIS_MAX_RETRIES_EXCEEDED"
        assert run.failure_retryable is False
        assert stage.status == AnalysisStageStatus.FAILED.value
        assert stage.failure_code == "ANALYSIS_MAX_RETRIES_EXCEEDED"
        assert stage.failure_retryable is False
        assert stage.attempt_count == 1
        assert stage.claim_token is None
        assert stage.lease_expires_at is None
        assert len(attempts) == 1
        assert attempts[0].attempt_number == 1
        assert attempts[0].status == AnalysisAttemptStatus.ABANDONED.value
        assert attempts[0].failure_code == "ANALYSIS_MAX_RETRIES_EXCEEDED"
        assert attempts[0].failure_retryable is False
        assert len(outbox_events) == 1
        assert outbox_events[0].status == OutboxStatus.PUBLISHED.value
        assert (
            session.scalar(
                select(func.count())
                .select_from(LLMExtractionResultModel)
                .where(LLMExtractionResultModel.analysis_run_id == run_uuid)
            )
            == 0
        )


def test_permanent_provider_failure_is_immediate_and_creates_no_retry_event(
    application_context: ApplicationContext,
) -> None:
    clock = MutableClock(NOW)
    _command, started = _start(
        application_context,
        case=application_context.case_a,
        idempotency_key=f"permanent-{uuid4()}",
        clock=clock,
    )
    queue = RecordingQueue()
    assert _dispatch(application_context, queue=queue, clock=clock).published == 1
    clock.advance(timedelta(seconds=1))

    failed = _execute(
        application_context,
        message=queue.messages[0],
        provider=MockLLMProvider(mode=MockProviderMode.PERMANENT_ERROR),
        clock=clock,
        max_attempts=3,
    )
    assert failed.disposition is ExecutionDisposition.FAILED

    with Session(application_context.engine) as session:
        run_uuid = UUID(started.run.id)
        run = session.get(AnalysisRunModel, run_uuid)
        stage = session.scalars(
            select(AnalysisStageRunModel).where(AnalysisStageRunModel.analysis_run_id == run_uuid)
        ).one()
        attempt = session.scalars(
            select(AnalysisStageAttemptModel).where(
                AnalysisStageAttemptModel.analysis_run_id == run_uuid
            )
        ).one()
        assert run is not None and run.status == AnalysisRunStatus.FAILED.value
        assert run.failure_code == "LLM_PROVIDER_REQUEST_REJECTED"
        assert stage.status == AnalysisStageStatus.FAILED.value
        assert stage.failure_code == "LLM_PROVIDER_REQUEST_REJECTED"
        assert attempt.status == AnalysisAttemptStatus.FAILED.value
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEventModel)
                .where(OutboxEventModel.aggregate_id == run_uuid)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(LLMExtractionResultModel)
                .where(LLMExtractionResultModel.analysis_run_id == run_uuid)
            )
            == 0
        )


def test_transient_provider_fails_with_max_retry_code_on_last_attempt(
    application_context: ApplicationContext,
) -> None:
    clock = MutableClock(NOW)
    _command, started = _start(
        application_context,
        case=application_context.case_a,
        idempotency_key=f"max-retry-{uuid4()}",
        clock=clock,
    )
    queue = RecordingQueue()
    assert _dispatch(application_context, queue=queue, clock=clock).published == 1
    clock.advance(timedelta(seconds=1))
    first = _execute(
        application_context,
        message=queue.messages[0],
        provider=MockLLMProvider(mode=MockProviderMode.TRANSIENT_ERROR),
        clock=clock,
        max_attempts=2,
    )
    assert first.disposition is ExecutionDisposition.RETRY_WAITING
    assert first.retry_at is not None

    clock.set(first.retry_at)
    assert _dispatch(application_context, queue=queue, clock=clock).published == 1
    second = _execute(
        application_context,
        message=queue.messages[1],
        provider=MockLLMProvider(mode=MockProviderMode.TRANSIENT_ERROR),
        clock=clock,
        max_attempts=2,
    )
    assert second.disposition is ExecutionDisposition.FAILED

    with Session(application_context.engine) as session:
        run_uuid = UUID(started.run.id)
        run = session.get(AnalysisRunModel, run_uuid)
        stage = session.scalars(
            select(AnalysisStageRunModel).where(AnalysisStageRunModel.analysis_run_id == run_uuid)
        ).one()
        attempts = session.scalars(
            select(AnalysisStageAttemptModel)
            .where(AnalysisStageAttemptModel.analysis_run_id == run_uuid)
            .order_by(AnalysisStageAttemptModel.attempt_number)
        ).all()
        assert run is not None and run.failure_code == "ANALYSIS_MAX_RETRIES_EXCEEDED"
        assert run.status == AnalysisRunStatus.FAILED.value
        assert stage.failure_code == "ANALYSIS_MAX_RETRIES_EXCEEDED"
        assert stage.status == AnalysisStageStatus.FAILED.value
        assert [attempt.status for attempt in attempts] == [
            AnalysisAttemptStatus.RETRY_WAITING.value,
            AnalysisAttemptStatus.FAILED.value,
        ]
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEventModel)
                .where(OutboxEventModel.aggregate_id == run_uuid)
            )
            == 2
        )


def test_outbox_terminal_exhaustion_fails_queued_run_and_stage(
    application_context: ApplicationContext,
) -> None:
    clock = MutableClock(NOW)
    _command, started = _start(
        application_context,
        case=application_context.case_a,
        idempotency_key=f"outbox-terminal-{uuid4()}",
        clock=clock,
    )
    queue = RecordingQueue(fail_on_calls=frozenset({1}))
    exhausted = _dispatch(
        application_context,
        queue=queue,
        clock=clock,
        max_attempts=1,
    )
    assert exhausted.model_dump() == {
        "claimed": 1,
        "published": 0,
        "retried": 0,
        "failed": 1,
    }
    assert queue.messages == []

    with Session(application_context.engine) as session:
        run_uuid = UUID(started.run.id)
        run = session.get(AnalysisRunModel, run_uuid)
        stage = session.scalars(
            select(AnalysisStageRunModel).where(AnalysisStageRunModel.analysis_run_id == run_uuid)
        ).one()
        event = session.scalars(
            select(OutboxEventModel).where(OutboxEventModel.aggregate_id == run_uuid)
        ).one()
        assert run is not None and run.status == AnalysisRunStatus.FAILED.value
        assert run.failure_code == "OUTBOX_DISPATCH_FAILED"
        assert stage.status == AnalysisStageStatus.FAILED.value
        assert stage.attempt_count == 0
        assert stage.failure_code == "OUTBOX_DISPATCH_FAILED"
        assert event.status == OutboxStatus.FAILED.value
        assert event.attempt_count == 1

    duplicate_dispatch = _dispatch(
        application_context,
        queue=queue,
        clock=clock,
        max_attempts=1,
    )
    assert duplicate_dispatch.claimed == 0
