"""Reliable identifier-only dispatchers for Sprint 5C request events."""

from datetime import timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.case_resolution import (
    CASE_RESOLUTION_DISPATCH_FAILURE,
    SIMULATION_DISPATCH_FAILURE,
)
from app.adapters.persistence.models import (
    CaseResolutionRequestEventModel,
    ExternalActionSimulationRequestEventModel,
)
from app.adapters.persistence.reliable_outbox import (
    DEFAULT_CLAIM_TTL,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_RETRY_BASE,
    DEFAULT_RETRY_MAX,
    ReliableOutboxSpec,
    ReliableSQLAlchemyOutboxDispatcher,
)
from app.application.outbox import DispatchOutboxResult
from app.platform.case_resolution import (
    CASE_RESOLUTION_REQUESTED_EVENT,
    EXTERNAL_ACTION_SIMULATION_REQUESTED_EVENT,
)
from app.ports.message_queue import MessageQueue


class DispatchCaseResolutionOutbox:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        queue: MessageQueue,
        claimed_by: str = "csight-case-resolution-dispatcher",
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
                model=CaseResolutionRequestEventModel,
                aggregate_id_attribute="resolution_id",
                queue_payload_key="resolution_id",
                topic=CASE_RESOLUTION_REQUESTED_EVENT,
                dispatch_failure_code=CASE_RESOLUTION_DISPATCH_FAILURE,
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


class DispatchExternalActionSimulationOutbox:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        queue: MessageQueue,
        claimed_by: str = "csight-action-simulation-dispatcher",
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
                model=ExternalActionSimulationRequestEventModel,
                aggregate_id_attribute="external_action_intent_id",
                queue_payload_key="external_action_intent_id",
                topic=EXTERNAL_ACTION_SIMULATION_REQUESTED_EVENT,
                dispatch_failure_code=SIMULATION_DISPATCH_FAILURE,
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


__all__ = ["DispatchCaseResolutionOutbox", "DispatchExternalActionSimulationOutbox"]
