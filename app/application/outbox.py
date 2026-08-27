"""Reliable outbox dispatch for reference-only analysis messages."""

from datetime import UTC, timedelta

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.application.analysis import (
    ANALYSIS_REQUESTED_EVENT_TYPE,
    DEFAULT_RETRY_BASE,
    DEFAULT_RETRY_JITTER_RATIO,
    DEFAULT_RETRY_MAX,
    aggregate_run_status,
    deterministic_retry_delay,
)
from app.platform.analysis import (
    AnalysisFailure,
    AnalysisRequestedEvent,
    AnalysisRunStatus,
    AnalysisStageStatus,
    OutboxEvent,
)
from app.ports.analysis_repository import AnalysisUnitOfWorkFactory
from app.ports.message_queue import MessageQueue
from app.ports.runtime import Clock, IdGenerator

DEFAULT_OUTBOX_BATCH_SIZE = 100
DEFAULT_OUTBOX_CLAIM_TTL = timedelta(seconds=30)
DEFAULT_OUTBOX_MAX_ATTEMPTS = 5


class DispatchOutboxResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claimed: int = Field(ge=0)
    published: int = Field(ge=0)
    retried: int = Field(ge=0)
    failed: int = Field(ge=0)


class DispatchOutbox:
    def __init__(
        self,
        *,
        uow_factory: AnalysisUnitOfWorkFactory,
        queue: MessageQueue,
        clock: Clock,
        id_generator: IdGenerator,
        claimed_by: str,
        batch_size: int = DEFAULT_OUTBOX_BATCH_SIZE,
        claim_ttl: timedelta = DEFAULT_OUTBOX_CLAIM_TTL,
        max_attempts: int = DEFAULT_OUTBOX_MAX_ATTEMPTS,
        retry_base: timedelta = DEFAULT_RETRY_BASE,
        retry_max: timedelta = DEFAULT_RETRY_MAX,
        retry_jitter_ratio: float = DEFAULT_RETRY_JITTER_RATIO,
        topic: str = ANALYSIS_REQUESTED_EVENT_TYPE,
    ) -> None:
        if not claimed_by.strip():
            raise ValueError("claimed_by must not be blank")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if claim_ttl.total_seconds() <= 0:
            raise ValueError("claim_ttl must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if topic != ANALYSIS_REQUESTED_EVENT_TYPE:
            raise ValueError("unsupported outbox topic")
        deterministic_retry_delay(
            attempt_number=1,
            seed="outbox-configuration",
            base=retry_base,
            maximum=retry_max,
            jitter_ratio=retry_jitter_ratio,
        )
        self._uow_factory = uow_factory
        self._queue = queue
        self._clock = clock
        self._id_generator = id_generator
        self._claimed_by = claimed_by
        self._batch_size = batch_size
        self._claim_ttl = claim_ttl
        self._max_attempts = max_attempts
        self._retry_base = retry_base
        self._retry_max = retry_max
        self._retry_jitter_ratio = retry_jitter_ratio
        self._topic = topic

    def execute(self) -> DispatchOutboxResult:
        now = self._clock.now().astimezone(UTC)
        claim_token = self._id_generator.new_id()
        with self._uow_factory() as uow:
            events = uow.outbox.claim_batch(
                now=now,
                stale_before=now - self._claim_ttl,
                claim_token=claim_token,
                claimed_by=self._claimed_by,
                limit=self._batch_size,
            )
            uow.flush()
            uow.commit()

        published = 0
        retried = 0
        failed = 0
        for event in events:
            try:
                requested_event = _validated_requested_event(event)
            except (ValidationError, ValueError):
                if self._mark_terminal_failure(event=event, claim_token=claim_token):
                    failed += 1
                continue

            try:
                self._queue.publish(
                    topic=self._topic,
                    payload=requested_event.queue_payload(),
                    correlation_id=requested_event.correlation_id,
                )
            except Exception:
                if event.attempt_count >= self._max_attempts:
                    if self._mark_terminal_failure(event=event, claim_token=claim_token):
                        failed += 1
                elif self._release_for_retry(event=event, claim_token=claim_token):
                    retried += 1
                continue

            published_at = self._clock.now().astimezone(UTC)
            with self._uow_factory() as uow:
                marked = uow.outbox.mark_published(
                    tenant_id=event.tenant_id,
                    event_id=event.id,
                    claim_token=claim_token,
                    published_at=published_at,
                )
                if marked is None:
                    uow.rollback()
                    continue
                uow.flush()
                uow.commit()
            published += 1

        return DispatchOutboxResult(
            claimed=len(events),
            published=published,
            retried=retried,
            failed=failed,
        )

    def _release_for_retry(self, *, event: OutboxEvent, claim_token: str) -> bool:
        now = self._clock.now().astimezone(UTC)
        delay = deterministic_retry_delay(
            attempt_number=event.attempt_count,
            seed=event.id,
            base=self._retry_base,
            maximum=self._retry_max,
            jitter_ratio=self._retry_jitter_ratio,
        )
        with self._uow_factory() as uow:
            released = uow.outbox.release_for_retry(
                tenant_id=event.tenant_id,
                event_id=event.id,
                claim_token=claim_token,
                available_at=now + delay,
                last_error="Message publication failed.",
                now=now,
            )
            if released is None:
                uow.rollback()
                return False
            uow.flush()
            uow.commit()
        return True

    def _mark_terminal_failure(self, *, event: OutboxEvent, claim_token: str) -> bool:
        now = self._clock.now().astimezone(UTC)
        failure = AnalysisFailure(
            code="OUTBOX_DISPATCH_FAILED",
            message="The analysis request could not be dispatched.",
            retryable=False,
        )
        requested_event: AnalysisRequestedEvent | None
        try:
            requested_event = _validated_requested_event(event)
        except (ValidationError, ValueError):
            requested_event = None

        with self._uow_factory() as uow:
            marked = uow.outbox.mark_failed(
                tenant_id=event.tenant_id,
                event_id=event.id,
                claim_token=claim_token,
                last_error="Message publication failed permanently.",
                now=now,
            )
            if marked is None:
                uow.rollback()
                return False

            if requested_event is not None:
                run = uow.analysis_runs.get_for_update(
                    tenant_id=requested_event.tenant_id,
                    case_id=requested_event.case_id,
                    analysis_run_id=requested_event.analysis_run_id,
                )
                stage = uow.stage_runs.get(
                    tenant_id=requested_event.tenant_id,
                    analysis_run_id=requested_event.analysis_run_id,
                    stage_run_id=requested_event.stage_run_id,
                )
                if stage is not None and stage.status in {
                    AnalysisStageStatus.QUEUED,
                    AnalysisStageStatus.RETRY_WAITING,
                }:
                    uow.stage_runs.transition(
                        tenant_id=requested_event.tenant_id,
                        analysis_run_id=requested_event.analysis_run_id,
                        stage_run_id=requested_event.stage_run_id,
                        expected_status=stage.status,
                        target_status=AnalysisStageStatus.FAILED,
                        now=now,
                        failure=failure,
                    )
                    stages = uow.stage_runs.list(
                        tenant_id=requested_event.tenant_id,
                        analysis_run_id=requested_event.analysis_run_id,
                    )
                    target_run = aggregate_run_status(stages)
                    if run is not None and target_run is not run.status:
                        uow.analysis_runs.transition(
                            tenant_id=requested_event.tenant_id,
                            analysis_run_id=requested_event.analysis_run_id,
                            expected_status=run.status,
                            target_status=target_run,
                            now=now,
                            failure=failure if target_run is AnalysisRunStatus.FAILED else None,
                        )
            uow.flush()
            uow.commit()
        return True


def _validated_requested_event(event: OutboxEvent) -> AnalysisRequestedEvent:
    requested_event = AnalysisRequestedEvent.model_validate(event.payload)
    if event.event_type != ANALYSIS_REQUESTED_EVENT_TYPE:
        raise ValueError("unsupported outbox event type")
    if event.event_version != requested_event.event_version:
        raise ValueError("outbox event version mismatch")
    if event.id != requested_event.event_id:
        raise ValueError("outbox event identifier mismatch")
    if event.tenant_id != requested_event.tenant_id:
        raise ValueError("outbox tenant mismatch")
    if event.aggregate_id != requested_event.analysis_run_id:
        raise ValueError("outbox aggregate mismatch")
    return requested_event


__all__ = ["DispatchOutbox", "DispatchOutboxResult"]
