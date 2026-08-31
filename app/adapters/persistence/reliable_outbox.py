"""Fenced SQLAlchemy dispatcher for identifier-only asynchronous outboxes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from app.application.outbox import DispatchOutboxResult
from app.ports.message_queue import MessageQueue

DEFAULT_BATCH_SIZE = 100
DEFAULT_CLAIM_TTL = timedelta(seconds=30)
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RETRY_BASE = timedelta(seconds=5)
DEFAULT_RETRY_MAX = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class ClaimedOutboxEvent:
    id: UUID
    tenant_id: UUID
    case_id: UUID
    aggregate_id: UUID
    correlation_id: str
    attempt_count: int
    claim_token: UUID
    topic: str | None = None


@dataclass(frozen=True, slots=True)
class TerminalRunFailure:
    model: type[Any]
    id_attribute: str
    failure_code: str
    failure_message: str


@dataclass(frozen=True, slots=True)
class ReliableOutboxSpec:
    model: type[Any]
    aggregate_id_attribute: str
    queue_payload_key: str
    topic: str
    dispatch_failure_code: str
    terminal_run_failure: TerminalRunFailure | None = None
    topic_attribute: str | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)


def exponential_retry_delay(
    *,
    attempt_count: int,
    base: timedelta = DEFAULT_RETRY_BASE,
    maximum: timedelta = DEFAULT_RETRY_MAX,
) -> timedelta:
    """Return a bounded exponential delay with no nondeterministic jitter."""

    if attempt_count < 1:
        raise ValueError("attempt_count must be positive")
    if base.total_seconds() <= 0:
        raise ValueError("base must be positive")
    if maximum < base:
        raise ValueError("maximum must be greater than or equal to base")
    multiplier = 1 << min(attempt_count - 1, 30)
    return min(base * multiplier, maximum)


class ReliableSQLAlchemyOutboxDispatcher:
    """Claim with a lease, publish after commit, and fence every terminal write."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        queue: MessageQueue,
        spec: ReliableOutboxSpec,
        claimed_by: str = "csight-outbox-dispatcher",
        batch_size: int = DEFAULT_BATCH_SIZE,
        claim_ttl: timedelta = DEFAULT_CLAIM_TTL,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_base: timedelta = DEFAULT_RETRY_BASE,
        retry_max: timedelta = DEFAULT_RETRY_MAX,
        now_factory: Callable[[], datetime] = utc_now,
        claim_token_factory: Callable[[], UUID] = uuid4,
        terminalize_run_on_failure: bool = True,
    ) -> None:
        if not claimed_by.strip():
            raise ValueError("claimed_by must not be blank")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if claim_ttl.total_seconds() <= 0:
            raise ValueError("claim_ttl must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        exponential_retry_delay(attempt_count=1, base=retry_base, maximum=retry_max)
        self._factory = session_factory
        self._queue = queue
        self._spec = spec
        self._claimed_by = claimed_by
        self._batch_size = batch_size
        self._claim_ttl = claim_ttl
        self._max_attempts = max_attempts
        self._retry_base = retry_base
        self._retry_max = retry_max
        self._now_factory = now_factory
        self._claim_token_factory = claim_token_factory
        self._terminalize_run_on_failure = terminalize_run_on_failure

    def execute(self) -> DispatchOutboxResult:
        claim_token = self._claim_token_factory()
        claimed_at = self._now()
        events = self._claim_batch(claim_token=claim_token, claimed_at=claimed_at)
        published = retried = failed = 0

        for event in events:
            try:
                self._queue.publish(
                    topic=event.topic or self._spec.topic,
                    payload=self._queue_payload(event),
                    correlation_id=event.correlation_id,
                )
            except Exception:
                if event.attempt_count >= self._max_attempts:
                    failed += int(self._mark_failed(event))
                else:
                    retried += int(self._release_for_retry(event))
                continue
            published += int(self._mark_published(event))

        return DispatchOutboxResult(
            claimed=len(events),
            published=published,
            retried=retried,
            failed=failed,
        )

    def _now(self) -> datetime:
        value = self._now_factory()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("dispatcher clock must return a timezone-aware datetime")
        return value.astimezone(UTC)

    def _claim_batch(
        self,
        *,
        claim_token: UUID,
        claimed_at: datetime,
    ) -> tuple[ClaimedOutboxEvent, ...]:
        model = self._spec.model
        stale_before = claimed_at - self._claim_ttl
        with self._factory.begin() as session:
            records = session.scalars(
                select(model)
                .where(
                    or_(
                        and_(model.status == "PENDING", model.available_at <= claimed_at),
                        and_(model.status == "PROCESSING", model.claimed_at <= stale_before),
                    )
                )
                .order_by(model.available_at, model.created_at, model.id)
                .with_for_update(skip_locked=True)
                .limit(self._batch_size)
            ).all()
            claimed: list[ClaimedOutboxEvent] = []
            for record in records:
                record.status = "PROCESSING"
                record.attempt_count += 1
                record.claimed_at = claimed_at
                record.claim_token = claim_token
                record.claimed_by = self._claimed_by
                claimed.append(
                    ClaimedOutboxEvent(
                        id=cast(UUID, record.id),
                        tenant_id=cast(UUID, record.tenant_id),
                        case_id=cast(UUID, record.case_id),
                        aggregate_id=cast(
                            UUID,
                            getattr(record, self._spec.aggregate_id_attribute),
                        ),
                        correlation_id=cast(str, record.correlation_id),
                        attempt_count=cast(int, record.attempt_count),
                        claim_token=claim_token,
                        topic=(
                            cast(str, getattr(record, self._spec.topic_attribute))
                            if self._spec.topic_attribute is not None
                            else None
                        ),
                    )
                )
        return tuple(claimed)

    def _queue_payload(self, event: ClaimedOutboxEvent) -> dict[str, object]:
        return {
            "event_id": str(event.id),
            "tenant_id": str(event.tenant_id),
            "case_id": str(event.case_id),
            self._spec.queue_payload_key: str(event.aggregate_id),
            "correlation_id": event.correlation_id,
        }

    def _mark_published(self, event: ClaimedOutboxEvent) -> bool:
        model = self._spec.model
        now = self._now()
        with self._factory.begin() as session:
            result = cast(
                CursorResult[Any],
                session.execute(
                    update(model)
                    .where(
                        model.id == event.id,
                        model.tenant_id == event.tenant_id,
                        model.status == "PROCESSING",
                        model.claim_token == event.claim_token,
                    )
                    .values(
                        status="PUBLISHED",
                        claimed_at=None,
                        claim_token=None,
                        claimed_by=None,
                        published_at=now,
                        last_error=None,
                        failure_code=None,
                        failed_at=None,
                    )
                    .execution_options(synchronize_session=False)
                ),
            )
        return result.rowcount == 1

    def _release_for_retry(self, event: ClaimedOutboxEvent) -> bool:
        model = self._spec.model
        now = self._now()
        delay = exponential_retry_delay(
            attempt_count=event.attempt_count,
            base=self._retry_base,
            maximum=self._retry_max,
        )
        with self._factory.begin() as session:
            result = cast(
                CursorResult[Any],
                session.execute(
                    update(model)
                    .where(
                        model.id == event.id,
                        model.tenant_id == event.tenant_id,
                        model.status == "PROCESSING",
                        model.claim_token == event.claim_token,
                    )
                    .values(
                        status="PENDING",
                        available_at=now + delay,
                        claimed_at=None,
                        claim_token=None,
                        claimed_by=None,
                        published_at=None,
                        last_error="Message publication failed; retry scheduled.",
                        failure_code=None,
                        failed_at=None,
                    )
                    .execution_options(synchronize_session=False)
                ),
            )
        return result.rowcount == 1

    def _mark_failed(self, event: ClaimedOutboxEvent) -> bool:
        model = self._spec.model
        now = self._now()
        with self._factory.begin() as session:
            result = cast(
                CursorResult[Any],
                session.execute(
                    update(model)
                    .where(
                        model.id == event.id,
                        model.tenant_id == event.tenant_id,
                        model.status == "PROCESSING",
                        model.claim_token == event.claim_token,
                    )
                    .values(
                        status="FAILED",
                        claimed_at=None,
                        claim_token=None,
                        claimed_by=None,
                        published_at=None,
                        last_error="Message publication failed permanently.",
                        failure_code=self._spec.dispatch_failure_code,
                        failed_at=now,
                    )
                    .execution_options(synchronize_session=False)
                ),
            )
            if result.rowcount != 1:
                return False
            if self._terminalize_run_on_failure:
                self._fail_unrecoverable_run(session=session, event=event, now=now)
        return True

    def _fail_unrecoverable_run(
        self,
        *,
        session: Session,
        event: ClaimedOutboxEvent,
        now: datetime,
    ) -> None:
        failure = self._spec.terminal_run_failure
        if failure is None:
            return
        model = failure.model
        run_id = getattr(model, failure.id_attribute)
        session.execute(
            update(model)
            .where(
                model.tenant_id == event.tenant_id,
                run_id == event.aggregate_id,
                or_(
                    model.status == "QUEUED",
                    and_(
                        model.status == "RUNNING",
                        model.lease_expires_at.is_not(None),
                        model.lease_expires_at <= now,
                    ),
                ),
            )
            .values(
                status="FAILED",
                started_at=func.coalesce(model.started_at, now),
                completed_at=now,
                failure_code=failure.failure_code,
                failure_message=failure.failure_message,
                claim_token=None,
                lease_expires_at=None,
            )
            .execution_options(synchronize_session=False)
        )


__all__ = [
    "ClaimedOutboxEvent",
    "ReliableOutboxSpec",
    "ReliableSQLAlchemyOutboxDispatcher",
    "TerminalRunFailure",
    "exponential_retry_delay",
]
