"""Durable dispatcher for identifier-only grounded-explanation messages."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import (
    GroundedExplanationOutboxEventModel,
    GroundedExplanationRunModel,
)
from app.application.outbox import DispatchOutboxResult
from app.ports.message_queue import MessageQueue

GROUNDED_EXPLANATION_REQUESTED_TASK = "grounded_explanation.requested.v1"


class DispatchGroundedExplanationOutbox:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        queue: MessageQueue,
        batch_size: int = 100,
    ) -> None:
        self._factory = session_factory
        self._queue = queue
        self._batch_size = batch_size

    def execute(self) -> DispatchOutboxResult:
        now = datetime.now(UTC)
        with self._factory.begin() as session:
            events = session.scalars(
                select(GroundedExplanationOutboxEventModel)
                .where(
                    GroundedExplanationOutboxEventModel.status == "PENDING",
                    GroundedExplanationOutboxEventModel.available_at <= now,
                )
                .order_by(GroundedExplanationOutboxEventModel.created_at)
                .with_for_update(skip_locked=True)
                .limit(self._batch_size)
            ).all()
            for event in events:
                event.status = "PROCESSING"
                event.attempt_count += 1
        published = retried = failed = 0
        for event in events:
            payload = {
                "event_id": str(event.id),
                "tenant_id": str(event.tenant_id),
                "case_id": str(event.case_id),
                "grounded_explanation_run_id": str(event.grounded_explanation_run_id),
                "correlation_id": event.correlation_id,
            }
            try:
                self._queue.publish(
                    topic=GROUNDED_EXPLANATION_REQUESTED_TASK,
                    payload=payload,
                    correlation_id=event.correlation_id,
                )
            except Exception:
                terminal = event.attempt_count >= 5
                with self._factory.begin() as session:
                    session.execute(
                        update(GroundedExplanationOutboxEventModel)
                        .where(GroundedExplanationOutboxEventModel.id == event.id)
                        .values(status="FAILED" if terminal else "PENDING")
                    )
                    if terminal:
                        session.execute(
                            update(GroundedExplanationRunModel)
                            .where(
                                GroundedExplanationRunModel.tenant_id == event.tenant_id,
                                GroundedExplanationRunModel.id == event.grounded_explanation_run_id,
                                GroundedExplanationRunModel.status == "QUEUED",
                            )
                            .values(
                                status="FAILED",
                                started_at=now,
                                completed_at=now,
                                failure_code="GROUNDED_EXPLANATION_OUTBOX_FAILED",
                                failure_message="Grounded explanation dispatch failed.",
                            )
                        )
                failed += int(terminal)
                retried += int(not terminal)
            else:
                with self._factory.begin() as session:
                    session.execute(
                        update(GroundedExplanationOutboxEventModel)
                        .where(GroundedExplanationOutboxEventModel.id == event.id)
                        .values(status="PUBLISHED")
                    )
                published += 1
        return DispatchOutboxResult(
            claimed=len(events), published=published, retried=retried, failed=failed
        )


__all__ = ["GROUNDED_EXPLANATION_REQUESTED_TASK", "DispatchGroundedExplanationOutbox"]
