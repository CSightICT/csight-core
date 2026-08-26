"""Structured logging configuration and request/task context binding."""

import logging
import sys
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

LOG_CONTEXT_KEYS = (
    "correlation_id",
    "tenant_id",
    "case_id",
    "analysis_run_id",
    "stage_run_id",
    "task_id",
    "event_id",
    "attempt_count",
    "provider",
    "model",
    "prompt_version",
    "status_transition",
    "latency_ms",
)
REDACTED = "[REDACTED]"
_SENSITIVE_LOG_KEY_PARTS = (
    "access_key",
    "api_key",
    "authorization",
    "customer_message",
    "customer_text",
    "database_url",
    "exc_info",
    "exception",
    "image_binary",
    "password",
    "presigned_url",
    "rabbitmq_url",
    "secret",
    "token",
)


def redact_sensitive_fields(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Remove known secret/PII-bearing structured fields before rendering."""

    for key in tuple(event_dict):
        normalized_key = key.casefold()
        if normalized_key.endswith("_url") or any(
            part in normalized_key for part in _SENSITIVE_LOG_KEY_PARTS
        ):
            event_dict[key] = REDACTED
    return event_dict


def configure_logging(log_level: str) -> None:
    """Configure JSON logging for API and worker processes."""

    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level, force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            redact_sensitive_fields,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structured logger without attaching sensitive configuration."""

    return structlog.stdlib.get_logger(name)


@contextmanager
def bind_log_context(**values: str | None) -> Generator[None, None, None]:
    """Bind supported trace identifiers for the duration of a unit of work."""

    clean_values = {
        key: value for key, value in values.items() if key in LOG_CONTEXT_KEYS and value is not None
    }
    tokens: Mapping[str, Any] = structlog.contextvars.bind_contextvars(**clean_values)
    try:
        yield
    finally:
        structlog.contextvars.reset_contextvars(**tokens)
