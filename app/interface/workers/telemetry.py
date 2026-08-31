"""Celery task base that adds safe process-local telemetry."""

from __future__ import annotations

import re
from time import perf_counter

from celery import Task
from celery.exceptions import Reject, Retry

from app.bootstrap.logging import bind_log_context
from app.bootstrap.telemetry import get_process_telemetry

_CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_:-]{0,127}$")


class TelemetryTask(Task):
    """Instrument every registered thin task without changing application use cases."""

    abstract = True

    def __call__(self, *args: object, **kwargs: object) -> object:
        runtime = get_process_telemetry()
        task_name_value: object = getattr(self, "name", None)
        task_name = task_name_value if isinstance(task_name_value, str) else "unknown"
        correlation_id = _payload_correlation_id(args=args, kwargs=kwargs)
        request = getattr(self, "request", None)
        request_id = getattr(request, "id", None)
        task_id = request_id if isinstance(request_id, str) else None
        started_at = perf_counter()
        outcome = "error"
        with (
            bind_log_context(correlation_id=correlation_id, task_id=task_id),
            runtime.start_task_span(
                task_name=task_name,
                correlation_id=correlation_id,
            ) as span,
        ):
            try:
                result = super().__call__(*args, **kwargs)
            except Retry as error:
                outcome = "retry"
                runtime.finish_task_span(
                    span,
                    outcome=outcome,
                    error_type=type(error).__name__,
                )
                raise
            except Reject as error:
                outcome = "reject"
                runtime.finish_task_span(
                    span,
                    outcome=outcome,
                    error_type=type(error).__name__,
                )
                raise
            except Exception as error:
                runtime.finish_task_span(
                    span,
                    outcome=outcome,
                    error_type=type(error).__name__,
                )
                raise
            else:
                outcome = "success"
                runtime.finish_task_span(span, outcome=outcome)
                return result
            finally:
                runtime.finish_task(
                    task_name=task_name,
                    outcome=outcome,
                    duration_ms=(perf_counter() - started_at) * 1000,
                )


def _payload_correlation_id(
    *,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> str | None:
    payload = args[0] if args else kwargs.get("payload")
    if not isinstance(payload, dict):
        return None
    value = payload.get("correlation_id")
    if not isinstance(value, str) or _CORRELATION_ID_PATTERN.fullmatch(value) is None:
        return None
    return value


__all__ = ["TelemetryTask"]
