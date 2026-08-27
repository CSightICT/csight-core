"""Thin Celery entrypoints for reference-only durable request events."""

import math
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from celery import Task
from celery.exceptions import Reject
from pydantic import ValidationError as PydanticValidationError

from app.application.analysis import ExecuteTextExtractionCommand
from app.application.case_resolution import (
    CaseResolutionRequestedCommand,
    ExternalActionSimulationRequestedCommand,
)
from app.application.grounding import ExecuteGroundedExplanationCommand
from app.application.human_review import HumanReviewRequestedCommand
from app.application.policy_engine import ExecutePolicyEvaluationCommand
from app.application.policy_query_runs import ExecutePolicyRetrievalRunCommand
from app.bootstrap.logging import bind_log_context, get_logger
from app.bootstrap.settings import get_settings
from app.bootstrap.sprint2 import build_execute_analysis_stage
from app.bootstrap.sprint4c2 import build_execute_policy_retrieval_run
from app.bootstrap.sprint4c3a import build_execute_grounded_explanation
from app.bootstrap.sprint5a import build_execute_policy_evaluation
from app.bootstrap.sprint5b import build_create_review_task
from app.bootstrap.sprint5c import (
    build_execute_external_action_simulation,
    build_process_case_resolution,
)
from app.interface.workers.celery_app import (
    ANALYSIS_REQUESTED_TASK_NAME,
    CASE_RESOLUTION_REQUESTED_TASK_NAME,
    EXTERNAL_ACTION_SIMULATION_REQUESTED_TASK_NAME,
    GROUNDED_EXPLANATION_REQUESTED_TASK_NAME,
    HUMAN_REVIEW_REQUESTED_TASK_NAME,
    POLICY_EVALUATION_REQUESTED_TASK_NAME,
    POLICY_RETRIEVAL_REQUESTED_TASK_NAME,
    celery_app,
)
from app.platform.async_reliability import (
    AsyncEventIntegrityError,
    ExecutionAttemptsExhaustedError,
    ExecutionLeaseActiveError,
)
from app.platform.case_resolution import CaseResolutionIntegrityError
from app.platform.human_review import ReviewPacketIntegrityError, ReviewTaskNotFoundError

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

    try:
        command = ExecutePolicyRetrievalRunCommand.model_validate(payload)
    except PydanticValidationError:
        event_id = _valid_event_id(payload)
        if event_id is not None:
            try:
                build_execute_policy_retrieval_run(get_settings()).record_poison_event(
                    event_id=event_id
                )
            except Exception:
                raise Reject(
                    "invalid policy retrieval payload could not be durably failed",
                    requeue=True,
                ) from None
        raise Reject("policy retrieval queue payload is invalid", requeue=False) from None
    service = build_execute_policy_retrieval_run(get_settings())
    try:
        disposition = service.execute(command)
        return {**command.model_dump(), "disposition": disposition}
    except ExecutionLeaseActiveError as error:
        settings = get_settings()
        raise task.retry(
            exc=error,
            countdown=_lease_retry_countdown(error),
            max_retries=settings.celery_task_max_retries + 2,
        ) from None
    except (AsyncEventIntegrityError, ExecutionAttemptsExhaustedError) as error:
        return {**command.model_dump(), "disposition": "FAILED", "failure_code": error.code}
    except Exception as error:
        settings = get_settings()
        retries = int(getattr(task.request, "retries", 0))
        if retries >= settings.celery_task_max_retries:
            service.record_failure(
                command,
                code="POLICY_RETRIEVAL_WORKER_RETRIES_EXHAUSTED",
                message="Policy retrieval worker exhausted bounded infrastructure retries.",
            )
            return {
                **command.model_dump(),
                "disposition": "FAILED",
                "failure_code": "POLICY_RETRIEVAL_WORKER_RETRIES_EXHAUSTED",
            }
        raise task.retry(
            exc=error,
            countdown=min(2**retries, settings.celery_retry_backoff_max_seconds),
            max_retries=settings.celery_task_max_retries,
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

    try:
        command = ExecuteGroundedExplanationCommand.model_validate(payload)
    except PydanticValidationError:
        event_id = _valid_event_id(payload)
        if event_id is not None:
            try:
                build_execute_grounded_explanation(get_settings()).record_poison_event(
                    event_id=event_id
                )
            except Exception:
                raise Reject(
                    "invalid grounded explanation payload could not be durably failed",
                    requeue=True,
                ) from None
        raise Reject("grounded explanation queue payload is invalid", requeue=False) from None
    service = build_execute_grounded_explanation(get_settings())
    try:
        disposition = service.execute(command)
        return {**command.model_dump(), "disposition": disposition}
    except ExecutionLeaseActiveError as error:
        settings = get_settings()
        raise task.retry(
            exc=error,
            countdown=_lease_retry_countdown(error),
            max_retries=settings.celery_task_max_retries + 2,
        ) from None
    except (AsyncEventIntegrityError, ExecutionAttemptsExhaustedError) as error:
        return {**command.model_dump(), "disposition": "FAILED", "failure_code": error.code}
    except Exception as error:
        settings = get_settings()
        retries = int(getattr(task.request, "retries", 0))
        if retries >= settings.celery_task_max_retries:
            service.record_failure(
                command,
                code="GROUNDED_EXPLANATION_WORKER_RETRIES_EXHAUSTED",
                message="Grounded explanation worker exhausted bounded infrastructure retries.",
            )
            return {
                **command.model_dump(),
                "disposition": "FAILED",
                "failure_code": "GROUNDED_EXPLANATION_WORKER_RETRIES_EXHAUSTED",
            }
        raise task.retry(
            exc=error,
            countdown=min(2**retries, settings.celery_retry_backoff_max_seconds),
            max_retries=settings.celery_task_max_retries,
        ) from None


@celery_app.task(  # pyright: ignore[reportUntypedFunctionDecorator]
    bind=True,
    name=POLICY_EVALUATION_REQUESTED_TASK_NAME,
)
def execute_policy_evaluation_task(
    task: Task,
    payload: dict[str, object],
) -> dict[str, object]:
    """Validate opaque identifiers and invoke the deterministic use case."""

    try:
        command = ExecutePolicyEvaluationCommand.model_validate(payload)
    except PydanticValidationError:
        event_id = _valid_event_id(payload)
        if event_id is not None:
            try:
                build_execute_policy_evaluation(get_settings()).record_poison_event(
                    event_id=event_id
                )
            except Exception:
                raise Reject(
                    "invalid policy evaluation payload could not be durably failed",
                    requeue=True,
                ) from None
        raise Reject("policy evaluation queue payload is invalid", requeue=False) from None
    service = build_execute_policy_evaluation(get_settings())
    try:
        disposition = service.execute(command)
        return {**command.model_dump(), "disposition": disposition}
    except ExecutionLeaseActiveError as error:
        settings = get_settings()
        raise task.retry(
            exc=error,
            countdown=_lease_retry_countdown(error),
            max_retries=settings.celery_task_max_retries + 2,
        ) from None
    except (AsyncEventIntegrityError, ExecutionAttemptsExhaustedError) as error:
        return {**command.model_dump(), "disposition": "FAILED", "failure_code": error.code}
    except Exception as error:
        settings = get_settings()
        retries = int(getattr(task.request, "retries", 0))
        if retries >= settings.celery_task_max_retries:
            service.record_failure(
                command,
                code="POLICY_EVALUATION_WORKER_RETRIES_EXHAUSTED",
                message="Policy evaluation worker exhausted bounded infrastructure retries.",
            )
            return {
                **command.model_dump(),
                "disposition": "FAILED",
                "failure_code": "POLICY_EVALUATION_WORKER_RETRIES_EXHAUSTED",
            }
        raise task.retry(
            exc=error,
            countdown=min(2**retries, settings.celery_retry_backoff_max_seconds),
            max_retries=settings.celery_task_max_retries,
        ) from None


@celery_app.task(  # pyright: ignore[reportUntypedFunctionDecorator]
    bind=True,
    name=HUMAN_REVIEW_REQUESTED_TASK_NAME,
)
def create_human_review_task(
    task: Task,
    payload: dict[str, object],
) -> dict[str, object]:
    """Create only Task/Packet/CREATED audit rows; never a final decision."""

    try:
        command = HumanReviewRequestedCommand.model_validate(payload)
    except PydanticValidationError:
        event_id = _valid_event_id(payload)
        if event_id is not None:
            try:
                build_create_review_task(get_settings()).record_poison_event(event_id=event_id)
            except Exception:
                raise Reject(
                    "invalid human review payload could not be durably failed",
                    requeue=True,
                ) from None
        raise Reject("human review queue payload is invalid", requeue=False) from None
    service = build_create_review_task(get_settings())
    try:
        disposition = service.execute(command)
        return {**command.model_dump(), "disposition": disposition}
    except (AsyncEventIntegrityError, ReviewPacketIntegrityError, ReviewTaskNotFoundError) as error:
        service.record_failure(
            command,
            code=str(getattr(error, "code", "HUMAN_REVIEW_INTEGRITY_FAILED")),
            message="Human review request failed permanent integrity validation.",
        )
        raise Reject(
            "human review request failed permanent integrity validation",
            requeue=False,
        ) from None
    except Exception:
        settings = get_settings()
        retries = int(getattr(task.request, "retries", 0))
        if retries >= settings.celery_task_max_retries:
            service.record_failure(
                command,
                code="HUMAN_REVIEW_WORKER_RETRIES_EXHAUSTED",
                message="Human review worker exhausted bounded infrastructure retries.",
            )
            raise Reject(
                "human review task exhausted bounded infrastructure retries",
                requeue=False,
            ) from None
        raise task.retry(
            exc=RuntimeError("human review task hit a transient infrastructure failure"),
            countdown=min(2**retries, settings.celery_retry_backoff_max_seconds),
            max_retries=settings.celery_task_max_retries,
        ) from None


@celery_app.task(  # pyright: ignore[reportUntypedFunctionDecorator]
    bind=True,
    name=CASE_RESOLUTION_REQUESTED_TASK_NAME,
)
def process_case_resolution_task(
    task: Task,
    payload: dict[str, object],
) -> dict[str, object]:
    """Map a committed Human Decision into a durable resolution outcome."""

    try:
        command = CaseResolutionRequestedCommand.model_validate(payload)
    except PydanticValidationError:
        event_id = _valid_event_id(payload)
        if event_id is not None:
            try:
                build_process_case_resolution(get_settings()).record_poison_event(event_id=event_id)
            except Exception:
                raise Reject(
                    "invalid Case Resolution payload could not be durably failed",
                    requeue=True,
                ) from None
        raise Reject("Case Resolution queue payload is invalid", requeue=False) from None
    service = build_process_case_resolution(get_settings())
    try:
        disposition = service.execute(command)
        return {**command.model_dump(), "disposition": disposition}
    except (AsyncEventIntegrityError, CaseResolutionIntegrityError) as error:
        return {
            **command.model_dump(),
            "disposition": "FAILED",
            "failure_code": str(getattr(error, "code", "CASE_RESOLUTION_INTEGRITY_FAILED")),
        }
    except Exception as error:
        settings = get_settings()
        retries = int(getattr(task.request, "retries", 0))
        if retries >= settings.celery_task_max_retries:
            service.record_failure(
                command,
                code="CASE_RESOLUTION_WORKER_RETRIES_EXHAUSTED",
                message="Case Resolution worker exhausted bounded infrastructure retries.",
            )
            return {
                **command.model_dump(),
                "disposition": "FAILED",
                "failure_code": "CASE_RESOLUTION_WORKER_RETRIES_EXHAUSTED",
            }
        raise task.retry(
            exc=error,
            countdown=min(2**retries, settings.celery_retry_backoff_max_seconds),
            max_retries=settings.celery_task_max_retries,
        ) from None


@celery_app.task(  # pyright: ignore[reportUntypedFunctionDecorator]
    bind=True,
    name=EXTERNAL_ACTION_SIMULATION_REQUESTED_TASK_NAME,
)
def execute_external_action_simulation_task(
    task: Task,
    payload: dict[str, object],
) -> dict[str, object]:
    """Run only the deterministic, network-free external Action simulation."""

    try:
        command = ExternalActionSimulationRequestedCommand.model_validate(payload)
    except PydanticValidationError:
        event_id = _valid_event_id(payload)
        if event_id is not None:
            try:
                build_execute_external_action_simulation(get_settings()).record_poison_event(
                    event_id=event_id
                )
            except Exception:
                raise Reject(
                    "invalid Action simulation payload could not be durably failed",
                    requeue=True,
                ) from None
        raise Reject("Action simulation queue payload is invalid", requeue=False) from None
    service = build_execute_external_action_simulation(get_settings())
    try:
        disposition = service.execute(command)
        return {**command.model_dump(), "disposition": disposition}
    except ExecutionLeaseActiveError as error:
        settings = get_settings()
        retries = int(getattr(task.request, "retries", 0))
        lease_retry_limit = settings.celery_task_max_retries + 2
        if retries >= lease_retry_limit:
            # This delivery is a duplicate fenced behind another committed lease.
            # The active delivery owns completion.  If it is lost, each expired
            # lease reclaim increments the DB execution counter until the
            # repository durably fails the Resolution at its configured bound.
            return {
                **command.model_dump(),
                "disposition": "FENCED_ACTIVE_LEASE",
                "retry_at": error.retry_at.isoformat(),
            }
        raise task.retry(
            exc=error,
            countdown=_lease_retry_countdown(error),
            max_retries=lease_retry_limit,
        ) from None
    except (
        AsyncEventIntegrityError,
        ExecutionAttemptsExhaustedError,
        CaseResolutionIntegrityError,
    ) as error:
        return {
            **command.model_dump(),
            "disposition": "FAILED",
            "failure_code": str(getattr(error, "code", "EXTERNAL_ACTION_SIMULATION_FAILED")),
        }
    except Exception as error:
        settings = get_settings()
        retries = int(getattr(task.request, "retries", 0))
        if retries >= settings.celery_task_max_retries:
            service.record_failure(
                command,
                code="EXTERNAL_ACTION_SIMULATION_WORKER_RETRIES_EXHAUSTED",
                message="Action simulation worker exhausted bounded infrastructure retries.",
                expected_execution_token=service.active_execution_token,
            )
            return {
                **command.model_dump(),
                "disposition": "FAILED",
                "failure_code": "EXTERNAL_ACTION_SIMULATION_WORKER_RETRIES_EXHAUSTED",
            }
        raise task.retry(
            exc=error,
            countdown=min(2**retries, settings.celery_retry_backoff_max_seconds),
            max_retries=settings.celery_task_max_retries,
        ) from None


def _lease_retry_countdown(error: ExecutionLeaseActiveError) -> int:
    return max(1, math.ceil((error.retry_at - datetime.now(UTC)).total_seconds()))


def _valid_event_id(payload: dict[str, object]) -> str | None:
    value = payload.get("event_id")
    if not isinstance(value, str):
        return None
    try:
        UUID(value)
    except ValueError:
        return None
    return value
