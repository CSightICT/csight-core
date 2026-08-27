"""Reliable identifier-only dispatcher for human review requests."""

from datetime import timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import HumanReviewRequestEventModel
from app.adapters.persistence.reliable_outbox import (
    DEFAULT_CLAIM_TTL,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_RETRY_BASE,
    DEFAULT_RETRY_MAX,
    ReliableOutboxSpec,
    ReliableSQLAlchemyOutboxDispatcher,
)
from app.application.outbox import DispatchOutboxResult
from app.ports.message_queue import MessageQueue

HUMAN_REVIEW_REQUESTED_TASK = "human_review.requested.v1"


class DispatchHumanReviewOutbox:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        queue: MessageQueue,
        claimed_by: str = "csight-human-review-dispatcher",
        batch_size: int = 100,
        claim_ttl: timedelta = DEFAULT_CLAIM_TTL,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_base: timedelta = DEFAULT_RETRY_BASE,
        retry_max: timedelta = DEFAULT_RETRY_MAX,
    ) -> None:
        self._dispatcher = ReliableSQLAlchemyOutboxDispatcher(
            session_factory=session_factory,
            queue=queue,
            spec=ReliableOutboxSpec(
                model=HumanReviewRequestEventModel,
                aggregate_id_attribute="policy_evaluation_run_id",
                queue_payload_key="policy_evaluation_run_id",
                topic=HUMAN_REVIEW_REQUESTED_TASK,
                dispatch_failure_code="HUMAN_REVIEW_OUTBOX_FAILED",
            ),
            claimed_by=claimed_by,
            batch_size=batch_size,
            claim_ttl=claim_ttl,
            max_attempts=max_attempts,
            retry_base=retry_base,
            retry_max=retry_max,
        )

    def execute(self) -> DispatchOutboxResult:
        return self._dispatcher.execute()


__all__ = ["HUMAN_REVIEW_REQUESTED_TASK", "DispatchHumanReviewOutbox"]
