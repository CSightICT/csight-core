"""Thin Celery entrypoint for one reference-only text-extraction event."""

from typing import cast

from celery import Task
from celery.exceptions import Reject

from app.application.analysis import ExecuteTextExtractionCommand
from app.application.grounding import ExecuteGroundedExplanationCommand
from app.application.policy_query_runs import ExecutePolicyRetrievalRunCommand
from app.bootstrap.logging import bind_log_context, get_logger
from app.bootstrap.settings import get_settings
from app.bootstrap.sprint2 import build_execute_analysis_stage
from app.bootstrap.sprint4c2 import build_execute_policy_retrieval_run
from app.bootstrap.sprint4c3a import build_execute_grounded_explanation
from app.interface.workers.celery_app import (
    ANALYSIS_REQUESTED_TASK_NAME,
    GROUNDED_EXPLANATION_REQUESTED_TASK_NAME,
    POLICY_RETRIEVAL_REQUESTED_TASK_NAME,
    celery_app,
)

logger = get_logger(__name__)

# Compatibility seam retained for Sprint 2 worker tests and alternate composition.
build_execute_text_extraction = build_execute_analysis_stage


@celery_app.task(  # pyright: ignore[reportUntypedFunctionDecorator]
    bind=True,
    name=ANALYSIS_REQUESTED_TASK_NAME,
)
def execute_text_extraction_task(
    task: Task,
    payload: dict[str, object],
) -> dict[str, object]:
    """Validate six opaque identifiers and delegate all work to the use case."""

    command = ExecuteTextExtractionCommand.model_validate(payload)
    try:
        task_id = cast(str | None, getattr(task.request, "id", None))
        with bind_log_context(
            event_id=command.event_id,
            tenant_id=command.tenant_id,
            case_id=command.case_id,
            analysis_run_id=command.analysis_run_id,
            stage_run_id=command.stage_run_id,
            task_id=task_id,
            correlation_id=command.correlation_id,
        ):
            logger.info("analysis_task_started")
            result = build_execute_text_extraction(get_settings()).execute(command=command)
            logger.info(
                "analysis_task_completed",
                disposition=result.disposition.value,
                status=result.status.value if result.status is not None else None,
            )
            return {
                "event_id": command.event_id,
                "tenant_id": command.tenant_id,
                "case_id": command.case_id,
                "analysis_run_id": result.analysis_run_id,
                "stage_run_id": result.stage_run_id,
                "correlation_id": command.correlation_id,
                "disposition": result.disposition.value,
                "status": result.status.value if result.status is not None else None,
                "retry_at": result.retry_at.isoformat() if result.retry_at is not None else None,
            }
    except Exception as error:
        # The command itself is already validated.  An unexpected infrastructure
        # failure must leave the broker delivery unacknowledged/requeued so a
        # committed outbox event cannot strand a QUEUED or RUNNING stage.  Normal
        # provider failures are persisted and returned by the application use case.
        logger.warning(
            "analysis_task_requeued",
            exception_type=type(error).__name__,
        )
        raise Reject(
            "analysis task did not reach a durable application outcome",
            requeue=True,
        ) from None


@celery_app.task(  # pyright: ignore[reportUntypedFunctionDecorator]
    bind=True,
    name=POLICY_RETRIEVAL_REQUESTED_TASK_NAME,
)
def execute_policy_retrieval_task(
    task: Task,
    payload: dict[str, object],
) -> dict[str, object]:
    """Validate five opaque identifiers and delegate all rules to the use case."""

    del task
    command = ExecutePolicyRetrievalRunCommand.model_validate(payload)
    try:
        disposition = build_execute_policy_retrieval_run(get_settings()).execute(command)
        return {**command.model_dump(), "disposition": disposition}
    except Exception:
        raise Reject(
            "policy retrieval task did not reach a durable application outcome",
            requeue=True,
        ) from None


@celery_app.task(  # pyright: ignore[reportUntypedFunctionDecorator]
    bind=True,
    name=GROUNDED_EXPLANATION_REQUESTED_TASK_NAME,
)
def execute_grounded_explanation_task(
    task: Task,
    payload: dict[str, object],
) -> dict[str, object]:
    """Validate five opaque identifiers and delegate grounding to the use case."""

    del task
    command = ExecuteGroundedExplanationCommand.model_validate(payload)
    try:
        disposition = build_execute_grounded_explanation(get_settings()).execute(command)
        return {**command.model_dump(), "disposition": disposition}
    except Exception:
        raise Reject(
            "grounded explanation task did not reach a durable application outcome",
            requeue=True,
        ) from None
