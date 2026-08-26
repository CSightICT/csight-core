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


__all__ = ["ANALYSIS_QUEUE_PAYLOAD_KEYS", "CeleryAnalysisMessageQueue"]
