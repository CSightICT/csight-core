"""Fenced dispatcher for operator-authorized database dead-letter replays."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import OperationalFailureRecoveryEventModel
from app.adapters.persistence.reliable_outbox import exponential_retry_delay
from app.application.outbox import DispatchOutboxResult
from app.ports.message_queue import MessageQueue

_ALLOWED_TOPICS = frozenset(
    {
        "analysis.requested.v1",
        "policy_retrieval.requested.v1",
        "policy_query_build.requested.v2",
        "policy_search.requested.v2",
        "grounded_explanation.requested.v1",
        "policy_evaluation.requested.v1",
        "human_review.requested.v1",
        "case_resolution.requested.v1",
        "external_action.simulation_requested.v1",
    }
)
_ALLOWED_PAYLOAD_KEYS = frozenset(
    {
        "event_id",
        "tenant_id",
        "case_id",
        "correlation_id",
        "analysis_run_id",
        "stage_run_id",
        "retrieval_run_id",
        "grounded_explanation_run_id",
        "policy_evaluation_run_id",
        "resolution_id",
        "external_action_intent_id",
    }
)
_COMMON_PAYLOAD_KEYS = frozenset({"event_id", "tenant_id", "case_id", "correlation_id"})


@dataclass(frozen=True, slots=True)
class ClaimedRecoveryEvent:
    id: UUID
    tenant_id: UUID
    topic: str
    payload: dict[str, object]
    correlation_id: str
    attempt_count: int
    claim_token: UUID


class DispatchOperationalFailureRecoveryOutbox:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        queue: MessageQueue,
        claimed_by: str = "csight-failure-recovery-dispatcher",
        batch_size: int = 100,
        claim_ttl: timedelta = timedelta(seconds=30),
        max_attempts: int = 5,
        retry_base: timedelta = timedelta(seconds=5),
        retry_max: timedelta = timedelta(minutes=5),
        now_factory: Callable[[], datetime] | None = None,
        claim_token_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        if not claimed_by.strip():
            raise ValueError("claimed_by must not be blank")
        if batch_size < 1 or max_attempts < 1:
            raise ValueError("batch_size and max_attempts must be positive")
        if claim_ttl.total_seconds() <= 0:
            raise ValueError("claim_ttl must be positive")
        exponential_retry_delay(attempt_count=1, base=retry_base, maximum=retry_max)
        self._factory = session_factory
        self._queue = queue
        self._claimed_by = claimed_by
        self._batch_size = batch_size
        self._claim_ttl = claim_ttl
        self._max_attempts = max_attempts
        self._retry_base = retry_base
        self._retry_max = retry_max
        self._now_factory = now_factory or (lambda: datetime.now(UTC))
        self._claim_token_factory = claim_token_factory

    def execute(self) -> DispatchOutboxResult:
        claim_token = self._claim_token_factory()
        events = self._claim_batch(claim_token=claim_token, claimed_at=self._now())
        published = retried = failed = 0
        for event in events:
            if not _valid_envelope(event):
                failed += int(self._mark_failed(event, code="FAILURE_RECOVERY_PAYLOAD_INVALID"))
                continue
            try:
                self._queue.publish(
                    topic=event.topic,
                    payload=event.payload,
                    correlation_id=event.correlation_id,
                )
            except Exception:
                if event.attempt_count >= self._max_attempts:
                    failed += int(self._mark_failed(event, code="FAILURE_RECOVERY_OUTBOX_FAILED"))
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

    def _claim_batch(
        self,
        *,
        claim_token: UUID,
        claimed_at: datetime,
    ) -> tuple[ClaimedRecoveryEvent, ...]:
        stale_before = claimed_at - self._claim_ttl
        with self._factory.begin() as session:
            rows = session.scalars(
                select(OperationalFailureRecoveryEventModel)
                .where(
                    or_(
                        and_(
                            OperationalFailureRecoveryEventModel.status == "PENDING",
                            OperationalFailureRecoveryEventModel.available_at <= claimed_at,
                        ),
                        and_(
                            OperationalFailureRecoveryEventModel.status == "PROCESSING",
                            OperationalFailureRecoveryEventModel.claimed_at <= stale_before,
                        ),
                    )
                )
                .order_by(
                    OperationalFailureRecoveryEventModel.available_at,
                    OperationalFailureRecoveryEventModel.created_at,
                    OperationalFailureRecoveryEventModel.id,
                )
                .with_for_update(skip_locked=True)
                .limit(self._batch_size)
            ).all()
            events: list[ClaimedRecoveryEvent] = []
            for row in rows:
                row.status = "PROCESSING"
                row.attempt_count += 1
                row.claimed_at = claimed_at
                row.claim_token = claim_token
                row.claimed_by = self._claimed_by
                events.append(
                    ClaimedRecoveryEvent(
                        id=row.id,
                        tenant_id=row.tenant_id,
                        topic=row.topic,
                        payload=dict(row.payload),
                        correlation_id=row.correlation_id,
                        attempt_count=row.attempt_count,
                        claim_token=claim_token,
                    )
                )
        return tuple(events)

    def _mark_published(self, event: ClaimedRecoveryEvent) -> bool:
        now = self._now()
        with self._factory.begin() as session:
            result = cast(
                CursorResult[Any],
                session.execute(
                    _fenced_update(event).values(
                        status="PUBLISHED",
                        claimed_at=None,
                        claim_token=None,
                        claimed_by=None,
                        published_at=now,
                        last_error=None,
                        failure_code=None,
                        failed_at=None,
                    )
                ),
            )
        return result.rowcount == 1

    def _release_for_retry(self, event: ClaimedRecoveryEvent) -> bool:
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
                    _fenced_update(event).values(
                        status="PENDING",
                        available_at=now + delay,
                        claimed_at=None,
                        claim_token=None,
                        claimed_by=None,
                        published_at=None,
                        last_error="Recovery message publication failed; retry scheduled.",
                        failure_code=None,
                        failed_at=None,
                    )
                ),
            )
        return result.rowcount == 1

    def _mark_failed(self, event: ClaimedRecoveryEvent, *, code: str) -> bool:
        now = self._now()
        with self._factory.begin() as session:
            result = cast(
                CursorResult[Any],
                session.execute(
                    _fenced_update(event).values(
                        status="FAILED",
                        claimed_at=None,
                        claim_token=None,
                        claimed_by=None,
                        published_at=None,
                        last_error="Recovery message publication failed permanently.",
                        failure_code=code,
                        failed_at=now,
                    )
                ),
            )
        return result.rowcount == 1

    def _now(self) -> datetime:
        value = self._now_factory()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recovery dispatcher clock must return a timezone-aware datetime")
        return value.astimezone(UTC)


def _fenced_update(event: ClaimedRecoveryEvent) -> Any:
    return (
        update(OperationalFailureRecoveryEventModel)
        .where(
            OperationalFailureRecoveryEventModel.id == event.id,
            OperationalFailureRecoveryEventModel.tenant_id == event.tenant_id,
            OperationalFailureRecoveryEventModel.status == "PROCESSING",
            OperationalFailureRecoveryEventModel.claim_token == event.claim_token,
        )
        .execution_options(synchronize_session=False)
    )


def _valid_envelope(event: ClaimedRecoveryEvent) -> bool:
    if event.topic not in _ALLOWED_TOPICS:
        return False
    keys = frozenset(event.payload)
    if not keys >= _COMMON_PAYLOAD_KEYS or not keys <= _ALLOWED_PAYLOAD_KEYS:
        return False
    if event.payload.get("correlation_id") != event.correlation_id:
        return False
    for key, value in event.payload.items():
        if key == "correlation_id":
            if not isinstance(value, str) or not 1 <= len(value) <= 128:
                return False
            continue
        if not isinstance(value, str):
            return False
        try:
            UUID(value)
        except ValueError:
            return False
    return True


__all__ = [
    "ClaimedRecoveryEvent",
    "DispatchOperationalFailureRecoveryOutbox",
]
