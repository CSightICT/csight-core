"""Structured, non-sensitive observability adapters."""

import structlog

from app.ports.observability import CompensationStep


class StructuredCompensationFailureObserver:
    """Emit one safe event for a failed Evidence upload compensation step.

    Object keys, exception messages, payloads, credentials, and URLs are
    deliberately excluded. The process-wide structlog configuration adds the
    request correlation ID when this observer runs inside an HTTP request.
    """

    def __init__(self) -> None:
        self._logger = structlog.stdlib.get_logger(__name__)

    def record_failure(
        self,
        *,
        step: CompensationStep,
        tenant_id: str,
        case_id: str,
        evidence_id: str,
        error_type: str,
    ) -> None:
        self._logger.error(
            "evidence_upload_compensation_failed",
            operation="evidence_upload",
            compensation_step=step,
            result="failed",
            tenant_id=tenant_id,
            case_id=case_id,
            evidence_id=evidence_id,
            error_type=error_type,
        )
