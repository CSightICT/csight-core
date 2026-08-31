"""Reliable identifier-only policy-evaluation dispatcher."""

from datetime import timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import (
    PolicyEvaluationOutboxEventModel,
    PolicyEvaluationRunModel,
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

POLICY_EVALUATION_REQUESTED_TASK = "policy_evaluation.requested.v1"


class DispatchPolicyEvaluationOutbox:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        queue: MessageQueue,
        claimed_by: str = "csight-policy-evaluation-dispatcher",
        batch_size: int = 100,
        claim_ttl: timedelta = DEFAULT_CLAIM_TTL,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retry_base: timedelta = DEFAULT_RETRY_BASE,
        retry_max: timedelta = DEFAULT_RETRY_MAX,
        terminalize_run_on_failure: bool = True,
    ) -> None:
        self._dispatcher = ReliableSQLAlchemyOutboxDispatcher(
            session_factory=session_factory,
            queue=queue,
            spec=ReliableOutboxSpec(
                model=PolicyEvaluationOutboxEventModel,
                aggregate_id_attribute="policy_evaluation_run_id",
                queue_payload_key="policy_evaluation_run_id",
                topic=POLICY_EVALUATION_REQUESTED_TASK,
                dispatch_failure_code="POLICY_EVALUATION_OUTBOX_FAILED",
                terminal_run_failure=TerminalRunFailure(
                    model=PolicyEvaluationRunModel,
                    id_attribute="id",
                    failure_code="POLICY_EVALUATION_OUTBOX_FAILED",
                    failure_message="Policy evaluation dispatch failed.",
                ),
            ),
            claimed_by=claimed_by,
            batch_size=batch_size,
            claim_ttl=claim_ttl,
            max_attempts=max_attempts,
            retry_base=retry_base,
            retry_max=retry_max,
            terminalize_run_on_failure=terminalize_run_on_failure,
        )

    def execute(self) -> DispatchOutboxResult:
        return self._dispatcher.execute()


__all__ = ["POLICY_EVALUATION_REQUESTED_TASK", "DispatchPolicyEvaluationOutbox"]
