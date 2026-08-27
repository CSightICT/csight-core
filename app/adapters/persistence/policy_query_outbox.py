"""Reliable dispatcher adapter for identifier-only policy retrieval messages."""

from datetime import timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import (
    PolicyRetrievalOutboxEventModel,
    PolicyRetrievalRunModel,
)
from app.adapters.persistence.reliable_outbox import (
    DEFAULT_CLAIM_TTL,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_RETRY_BASE,
    DEFAULT_RETRY_MAX,
    ReliableOutboxSpec,
    ReliableSQLAlchemyOutboxDispatcher,
    TerminalRunFailure,
)
from app.application.outbox import DispatchOutboxResult
from app.ports.message_queue import MessageQueue

POLICY_RETRIEVAL_REQUESTED_TASK = "policy_retrieval.requested.v1"


class DispatchPolicyRetrievalOutbox:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        queue: MessageQueue,
        claimed_by: str = "csight-policy-retrieval-dispatcher",
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
                model=PolicyRetrievalOutboxEventModel,
                aggregate_id_attribute="retrieval_run_id",
                queue_payload_key="retrieval_run_id",
                topic=POLICY_RETRIEVAL_REQUESTED_TASK,
                dispatch_failure_code="POLICY_RETRIEVAL_OUTBOX_FAILED",
                terminal_run_failure=TerminalRunFailure(
                    model=PolicyRetrievalRunModel,
                    id_attribute="id",
                    failure_code="POLICY_RETRIEVAL_OUTBOX_FAILED",
                    failure_message="Policy retrieval dispatch failed.",
                ),
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


__all__ = ["POLICY_RETRIEVAL_REQUESTED_TASK", "DispatchPolicyRetrievalOutbox"]
