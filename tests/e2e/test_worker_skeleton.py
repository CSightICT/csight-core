"""Network-free verification of the thin Celery analysis entrypoint."""

from typing import cast

import pytest
from celery import Task

from app.bootstrap.settings import Settings
from app.interface.workers import tasks as tasks_module

pytestmark = pytest.mark.e2e


def test_worker_task_delegates_to_mock_analysis_use_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    monkeypatch.setattr(tasks_module, "get_settings", lambda: settings)
    task = cast(Task, tasks_module.analyze_case_task)

    result = cast(
        dict[str, object],
        task.run(
            {
                "case_id": "CASE-WORKER-1",
                "analysis_run_id": "AR-WORKER-1",
                "customer_message": "용기 하단 누액으로 교환을 요청합니다.",
                "image_references": ["minio://csight-evidence/example.jpg"],
            }
        ),
    )

    assert result["case_id"] == "CASE-WORKER-1"
    assert result["analysis_run_id"] == "AR-WORKER-1"
    assert result["status"] == "completed"
    assert result["llm_provider"] == "mock"
    assert result["vision_provider"] == "mock"
    assert result["vision_result_count"] == 1
    assert "llm" not in result
    assert "vision" not in result
    assert "image_references" not in result
    assert "customer_message" not in result
