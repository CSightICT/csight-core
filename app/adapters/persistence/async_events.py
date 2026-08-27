"""Shared state transitions for durable asynchronous request events."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.adapters.persistence.models import (
    CaseResolutionRequestEventModel,
    ExternalActionSimulationRequestEventModel,
    GroundedExplanationOutboxEventModel,
    HumanReviewRequestEventModel,
    PolicyEvaluationOutboxEventModel,
    PolicyRetrievalOutboxEventModel,
)
from app.platform.async_reliability import AsyncEventIntegrityError

type AsyncRequestEvent = (
    PolicyRetrievalOutboxEventModel
    | GroundedExplanationOutboxEventModel
    | PolicyEvaluationOutboxEventModel
    | HumanReviewRequestEventModel
    | CaseResolutionRequestEventModel
    | ExternalActionSimulationRequestEventModel
)


def begin_consumer_attempt(event: AsyncRequestEvent) -> None:
    event.consumer_attempt_count += 1
    event.consumer_last_error = None


def validate_request_event(
    event: AsyncRequestEvent,
    *,
    tenant_id: UUID,
    case_id: UUID,
    correlation_id: str,
    run_id: UUID,
    run_attribute: str,
) -> AsyncEventIntegrityError | None:
    actual_run_id = getattr(event, run_attribute, None)
    if (
        event.tenant_id != tenant_id
        or event.case_id != case_id
        or event.correlation_id != correlation_id
        or actual_run_id != run_id
    ):
        return AsyncEventIntegrityError(
            code="ASYNC_EVENT_PAYLOAD_MISMATCH",
            message="The broker delivery does not match its durable request event.",
        )
    if event.status not in {"PROCESSING", "PUBLISHED"}:
        return AsyncEventIntegrityError(
            code="ASYNC_EVENT_STATE_INVALID",
            message="The durable request event is not consumable.",
        )
    return None


def consumer_failure_may_terminalize_run(
    *,
    status: str,
    lease_expires_at: datetime | None,
    now: datetime,
) -> bool:
    """Fence stale terminal recorders from a newer active execution lease."""

    return status == "QUEUED" or (
        status == "RUNNING" and (lease_expires_at is None or lease_expires_at <= now)
    )


def record_rejected_dispatch_recovery(
    event: AsyncRequestEvent,
    *,
    message: str,
) -> None:
    """Preserve a terminal dispatcher cause while auditing a forged recovery attempt."""

    marker = f"Dispatch recovery rejected: {message}"[:1000]
    previous = event.consumer_last_error
    event.consumer_last_error = f"{previous[:700]} | {marker}"[:1000] if previous else marker


def mark_event_consumed(event: AsyncRequestEvent, *, now: datetime) -> None:
    event.status = "CONSUMED"
    event.published_at = event.published_at or now
    event.consumed_at = now
    event.claimed_at = None
    event.claim_token = None
    event.claimed_by = None
    event.last_error = None
    event.consumer_last_error = None
    event.failure_code = None
    event.failed_at = None


def recover_dispatch_failure(
    event: AsyncRequestEvent,
    *,
    now: datetime,
    dispatch_failure_code: str,
) -> bool:
    """Let a confirmed broker delivery win over a later dispatcher failure."""

    if event.status != "FAILED" or event.failure_code != dispatch_failure_code:
        return False
    event.status = "PUBLISHED"
    event.published_at = event.published_at or event.failed_at or now
    event.last_error = None
    event.failure_code = None
    event.failed_at = None
    return True


def event_allows_completion(
    event: AsyncRequestEvent,
    *,
    dispatch_failure_code: str,
) -> bool:
    return event.status in {"PROCESSING", "PUBLISHED"} or (
        event.status == "FAILED" and event.failure_code == dispatch_failure_code
    )


def mark_event_failed(
    event: AsyncRequestEvent,
    *,
    now: datetime,
    code: str,
    message: str,
) -> None:
    event.status = "FAILED"
    # A forged/early broker delivery can expose a still-PENDING row whose
    # publisher attempt counter is zero.  Normalize the terminal audit record
    # so the fail-closed transition itself satisfies the database invariant.
    event.attempt_count = max(1, event.attempt_count)
    event.published_at = event.published_at or now
    event.claimed_at = None
    event.claim_token = None
    event.claimed_by = None
    event.consumer_last_error = message[:1000]
    event.failure_code = code[:128]
    event.failed_at = now


__all__ = [
    "AsyncRequestEvent",
    "begin_consumer_attempt",
    "consumer_failure_may_terminalize_run",
    "event_allows_completion",
    "mark_event_consumed",
    "mark_event_failed",
    "record_rejected_dispatch_recovery",
    "recover_dispatch_failure",
    "validate_request_event",
]
