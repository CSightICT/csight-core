"""Network-free verification of the thin Sprint 2 Celery entrypoint."""

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from billiard.exceptions import SoftTimeLimitExceeded
from celery import Task
from celery.exceptions import Reject

from app.application.analysis import (
    ExecuteTextExtractionCommand,
    ExecuteTextExtractionResult,
    ExecutionDisposition,
)
from app.bootstrap.settings import Settings
from app.interface.workers import tasks as tasks_module
from app.platform.analysis import AnalysisStageStatus

pytestmark = pytest.mark.e2e


class _FakeExecuteTextExtraction:
    def __init__(self) -> None:
        self.command: ExecuteTextExtractionCommand | None = None
        self.poison_event_ids: list[str] = []

    def execute(
        self,
        *,
        command: ExecuteTextExtractionCommand,
    ) -> ExecuteTextExtractionResult:
        self.command = command
        return ExecuteTextExtractionResult(
            disposition=ExecutionDisposition.RETRY_WAITING,
            analysis_run_id=command.analysis_run_id,
            stage_run_id=command.stage_run_id,
            status=AnalysisStageStatus.RETRY_WAITING,
            retry_at=datetime(2026, 8, 26, 4, 5, 6, tzinfo=UTC),
        )

    def record_poison_event(self, *, event_id: str) -> None:
        self.poison_event_ids.append(event_id)


class _FailingExecuteTextExtraction:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def execute(
        self,
        *,
        command: ExecuteTextExtractionCommand,
    ) -> ExecuteTextExtractionResult:
        del command
        raise self._error


def _payload() -> dict[str, object]:
    return {
        "event_id": "event-worker-1",
        "tenant_id": "tenant-worker-1",
        "case_id": "case-worker-1",
        "analysis_run_id": "run-worker-1",
        "stage_run_id": "stage-worker-1",
        "correlation_id": "correlation-worker-1",
    }


def test_worker_task_delegates_exact_six_key_command_without_celery_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    use_case = _FakeExecuteTextExtraction()

    def build(_settings: Settings) -> _FakeExecuteTextExtraction:
        return use_case

    monkeypatch.setattr(tasks_module, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks_module, "build_execute_text_extraction", build)
    task = cast(Task, tasks_module.execute_text_extraction_task)

    result = cast(
        dict[str, object],
        task.run(_payload()),
    )

    assert task.name == "analysis.requested.v1"
    assert use_case.command == ExecuteTextExtractionCommand.model_validate(_payload())
    assert result == {
        **_payload(),
        "disposition": "RETRY_WAITING",
        "status": "RETRY_WAITING",
        "retry_at": "2026-08-26T04:05:06+00:00",
    }
    assert not hasattr(task, "autoretry_for")


def test_worker_task_rejects_raw_or_incomplete_payload_before_delegation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    use_case = _FakeExecuteTextExtraction()

    def build(_settings: Settings) -> _FakeExecuteTextExtraction:
        return use_case

    monkeypatch.setattr(tasks_module, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks_module, "build_execute_text_extraction", build)
    task = cast(Task, tasks_module.execute_text_extraction_task)
    event_id = str(uuid4())

    with pytest.raises(Reject) as extra_rejected:
        task.run(
            {
                **_payload(),
                "event_id": event_id,
                "customer_message": "must never enter the broker",
            }
        )
    with pytest.raises(Reject) as incomplete_rejected:
        task.run(
            {
                key: value
                for key, value in {**_payload(), "event_id": event_id}.items()
                if key != "stage_run_id"
            }
        )

    assert use_case.command is None
    assert use_case.poison_event_ids == [event_id, event_id]
    assert extra_rejected.value.requeue is False
    assert incomplete_rejected.value.requeue is False


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("raw infrastructure detail must not become the reject reason"),
        SoftTimeLimitExceeded(),
    ],
)
def test_worker_task_requeues_unexpected_or_soft_timeout_with_safe_reason(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    def build(_settings: Settings) -> _FailingExecuteTextExtraction:
        return _FailingExecuteTextExtraction(error)

    monkeypatch.setattr(tasks_module, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks_module, "build_execute_text_extraction", build)
    task = cast(Task, tasks_module.execute_text_extraction_task)

    with pytest.raises(Reject) as rejected:
        task.run(_payload())

    assert rejected.value.requeue is True
    assert "raw infrastructure detail" not in str(rejected.value)
