"""Thin Celery entrypoints; orchestration remains in application use cases."""

from typing import cast

from celery import Task

from app.application.analyze_case import AnalyzeCaseCommand
from app.bootstrap.dependencies import build_analyze_case
from app.bootstrap.logging import bind_log_context, get_logger
from app.bootstrap.settings import get_settings
from app.interface.workers.celery_app import ANALYZE_CASE_TASK_NAME, celery_app
from app.platform.analysis import ProviderFailureError, ProviderTimeoutError

logger = get_logger(__name__)
_task_settings = get_settings()


@celery_app.task(  # pyright: ignore[reportUntypedFunctionDecorator]
    bind=True,
    name=ANALYZE_CASE_TASK_NAME,
    autoretry_for=(ProviderTimeoutError, ProviderFailureError),
    retry_backoff=True,
    retry_jitter=True,
    retry_backoff_max=_task_settings.celery_retry_backoff_max_seconds,
    retry_kwargs={"max_retries": _task_settings.celery_task_max_retries},
)
def analyze_case_task(
    task: Task,
    payload: dict[str, object],
    correlation_id: str | None = None,
) -> dict[str, object]:
    """Validate a reference-only command and delegate it to ``AnalyzeCase``."""

    command = AnalyzeCaseCommand.model_validate(payload)
    task_id = cast(str | None, getattr(task.request, "id", None))
    request_correlation_id = cast(str | None, getattr(task.request, "correlation_id", None))
    resolved_correlation_id = correlation_id or request_correlation_id

    with bind_log_context(
        case_id=command.case_id,
        analysis_run_id=command.analysis_run_id,
        task_id=task_id,
        correlation_id=resolved_correlation_id,
    ):
        logger.info("analysis_task_started")
        result = build_analyze_case(get_settings()).execute(command)
        logger.info("analysis_task_completed")
        # Celery logs return values at INFO. Keep the task acknowledgement free of
        # customer text and image references; persistence of the normalized result
        # belongs to the application/repository workflow introduced after Sprint 0.
        return {
            "status": "completed",
            "case_id": result.case_id,
            "analysis_run_id": result.analysis_run_id,
            "llm_provider": result.versions.llm_model.provider,
            "vision_provider": result.versions.vision_model.provider,
            "vision_result_count": len(result.vision),
        }
