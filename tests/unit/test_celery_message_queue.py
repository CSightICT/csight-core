"""Reference-only Celery publisher tests."""

from contextlib import AbstractContextManager
from typing import cast

import pytest
from celery import Celery

from app.adapters.messaging import CeleryAnalysisMessageQueue

pytestmark = pytest.mark.unit


class _FakeConnection(AbstractContextManager["_FakeConnection"]):
    connected = True

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def ensure_connection(self, *, max_retries: int) -> None:
        assert max_retries == 0


class _FakeCelery:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def send_task(self, name: str, **options: object) -> object:
        self.calls.append({"name": name, **options})
        return object()

    def connection_for_write(self) -> _FakeConnection:
        return _FakeConnection()


def _payload() -> dict[str, object]:
    return {
        "event_id": "event-1",
        "tenant_id": "tenant-1",
        "case_id": "case-1",
        "analysis_run_id": "run-1",
        "stage_run_id": "stage-1",
        "correlation_id": "correlation-1",
    }


def test_publish_sends_exact_reference_payload_with_event_task_id() -> None:
    application = _FakeCelery()
    queue = CeleryAnalysisMessageQueue(cast(Celery, application))

    message_id = queue.publish(
        topic="analysis.requested.v1",
        payload=_payload(),
        correlation_id="correlation-1",
    )

    assert message_id == "event-1"
    assert application.calls == [
        {
            "name": "analysis.requested.v1",
            "args": [_payload()],
            "task_id": "event-1",
            "queue": "analysis",
            "headers": {"correlation_id": "correlation-1"},
        }
    ]
    assert queue.is_ready() is True


@pytest.mark.parametrize(
    "payload",
    [
        {**_payload(), "customer_message": "must-not-cross-the-boundary"},
        {key: value for key, value in _payload().items() if key != "stage_run_id"},
        {**_payload(), "case_id": ""},
    ],
)
def test_publish_rejects_non_allowlisted_or_blank_payloads(
    payload: dict[str, object],
) -> None:
    application = _FakeCelery()
    queue = CeleryAnalysisMessageQueue(cast(Celery, application))

    with pytest.raises(ValueError):
        queue.publish(
            topic="analysis.requested.v1",
            payload=payload,
            correlation_id="correlation-1",
        )

    assert application.calls == []


def test_publish_rejects_mismatched_correlation_id() -> None:
    queue = CeleryAnalysisMessageQueue(cast(Celery, _FakeCelery()))

    with pytest.raises(ValueError, match="correlation_id"):
        queue.publish(
            topic="analysis.requested.v1",
            payload=_payload(),
            correlation_id="different",
        )
