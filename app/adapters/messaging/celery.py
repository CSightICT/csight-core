"""Celery-backed publisher for reference-only analysis commands."""

from collections.abc import Mapping
from typing import Final

from celery import Celery

ANALYSIS_QUEUE_PAYLOAD_KEYS: Final = frozenset(
    {
        "event_id",
        "tenant_id",
        "case_id",
        "analysis_run_id",
        "stage_run_id",
        "correlation_id",
    }
)
POLICY_RETRIEVAL_QUEUE_PAYLOAD_KEYS: Final = frozenset(
    {"event_id", "tenant_id", "case_id", "retrieval_run_id", "correlation_id"}
)
GROUNDED_EXPLANATION_QUEUE_PAYLOAD_KEYS: Final = frozenset(
    {
        "event_id",
        "tenant_id",
        "case_id",
        "grounded_explanation_run_id",
        "correlation_id",
    }
)
POLICY_EVALUATION_QUEUE_PAYLOAD_KEYS: Final = frozenset(
    {
        "event_id",
        "tenant_id",
        "case_id",
        "policy_evaluation_run_id",
        "correlation_id",
    }
)


class CeleryAnalysisMessageQueue:
    """Publish a validated, identifier-only task through Celery.

    The outbox event is the durable source of truth.  ``event_id`` is also used
    as the Celery task identifier so an operator can correlate a duplicate
    publish without putting customer content in the broker message.
    """

    def __init__(self, application: Celery, *, queue: str = "analysis") -> None:
        if not queue.strip():
            raise ValueError("queue must not be blank")
        self._application = application
        self._queue = queue

    def publish(
        self,
        *,
        topic: str,
        payload: Mapping[str, object],
        correlation_id: str,
    ) -> str:
        normalized = dict(payload)
        if frozenset(normalized) != ANALYSIS_QUEUE_PAYLOAD_KEYS:
            raise ValueError("analysis queue payload must contain exactly the six allowed IDs")
        if any(not isinstance(value, str) or not value.strip() for value in normalized.values()):
            raise ValueError("analysis queue payload values must be non-empty strings")
        if normalized["correlation_id"] != correlation_id:
            raise ValueError("correlation_id must match the queue payload")

        event_id = normalized["event_id"]
        assert isinstance(event_id, str)
        self._application.send_task(
            topic,
            args=[normalized],
            task_id=event_id,
            queue=self._queue,
            headers={"correlation_id": correlation_id},
        )
        return event_id

    def is_ready(self) -> bool:
        try:
            with self._application.connection_for_write() as connection:
                connection.ensure_connection(max_retries=0)
                return bool(connection.connected)
        except Exception:
            return False


class CeleryPolicyRetrievalMessageQueue:
    """Publish only five opaque policy-retrieval identifiers."""

    def __init__(self, application: Celery, *, queue: str = "policy-retrieval") -> None:
        self._application = application
        self._queue = queue

    def publish(self, *, topic: str, payload: Mapping[str, object], correlation_id: str) -> str:
        normalized = dict(payload)
        if frozenset(normalized) != POLICY_RETRIEVAL_QUEUE_PAYLOAD_KEYS:
            raise ValueError("policy retrieval queue payload must contain exactly five IDs")
        if any(not isinstance(value, str) or not value.strip() for value in normalized.values()):
            raise ValueError("policy retrieval queue values must be non-empty strings")
        if normalized["correlation_id"] != correlation_id:
            raise ValueError("correlation_id must match the queue payload")
        event_id = str(normalized["event_id"])
        self._application.send_task(
            topic,
            args=[normalized],
            task_id=event_id,
            queue=self._queue,
            headers={"correlation_id": correlation_id},
        )
        return event_id

    def is_ready(self) -> bool:
        try:
            with self._application.connection_for_write() as connection:
                connection.ensure_connection(max_retries=0)
                return bool(connection.connected)
        except Exception:
            return False


class CeleryGroundedExplanationMessageQueue:
    """Publish only five opaque grounded-explanation identifiers."""

    def __init__(self, application: Celery, *, queue: str = "grounded-explanation") -> None:
        self._application = application
        self._queue = queue

    def publish(self, *, topic: str, payload: Mapping[str, object], correlation_id: str) -> str:
        normalized = dict(payload)
        if frozenset(normalized) != GROUNDED_EXPLANATION_QUEUE_PAYLOAD_KEYS:
            raise ValueError("grounded explanation queue payload must contain exactly five IDs")
        if any(not isinstance(value, str) or not value.strip() for value in normalized.values()):
            raise ValueError("grounded explanation queue values must be non-empty strings")
        if normalized["correlation_id"] != correlation_id:
            raise ValueError("correlation_id must match the queue payload")
        event_id = str(normalized["event_id"])
        self._application.send_task(
            topic,
            args=[normalized],
            task_id=event_id,
            queue=self._queue,
            headers={"correlation_id": correlation_id},
        )
        return event_id

    def is_ready(self) -> bool:
        try:
            with self._application.connection_for_write() as connection:
                connection.ensure_connection(max_retries=0)
                return bool(connection.connected)
        except Exception:
            return False


class CeleryPolicyEvaluationMessageQueue:
    """Publish exactly five opaque deterministic-policy identifiers."""

    def __init__(self, application: Celery, *, queue: str = "policy-evaluation") -> None:
        self._application = application
        self._queue = queue

    def publish(self, *, topic: str, payload: Mapping[str, object], correlation_id: str) -> str:
        normalized = dict(payload)
        if frozenset(normalized) != POLICY_EVALUATION_QUEUE_PAYLOAD_KEYS:
            raise ValueError("policy evaluation queue payload must contain exactly five IDs")
        if any(not isinstance(value, str) or not value.strip() for value in normalized.values()):
            raise ValueError("policy evaluation queue values must be non-empty strings")
        if normalized["correlation_id"] != correlation_id:
            raise ValueError("correlation_id must match the queue payload")
        event_id = str(normalized["event_id"])
        self._application.send_task(
            topic,
            args=[normalized],
            task_id=event_id,
            queue=self._queue,
            headers={"correlation_id": correlation_id},
        )
        return event_id

    def is_ready(self) -> bool:
        try:
            with self._application.connection_for_write() as connection:
                connection.ensure_connection(max_retries=0)
                return bool(connection.connected)
        except Exception:
            return False


__all__ = [
    "ANALYSIS_QUEUE_PAYLOAD_KEYS",
    "GROUNDED_EXPLANATION_QUEUE_PAYLOAD_KEYS",
    "POLICY_EVALUATION_QUEUE_PAYLOAD_KEYS",
    "POLICY_RETRIEVAL_QUEUE_PAYLOAD_KEYS",
    "CeleryAnalysisMessageQueue",
    "CeleryGroundedExplanationMessageQueue",
    "CeleryPolicyEvaluationMessageQueue",
    "CeleryPolicyRetrievalMessageQueue",
]
