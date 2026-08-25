"""Safe structured logging tests for Evidence compensation failures."""

import pytest
from structlog.testing import capture_logs

from app.adapters.observability import StructuredCompensationFailureObserver

pytestmark = pytest.mark.unit


def test_compensation_observer_emits_safe_structured_fields_only() -> None:
    observer = StructuredCompensationFailureObserver()

    with capture_logs() as events:
        observer.record_failure(
            step="object_delete",
            tenant_id="tenant-safe-id",
            case_id="case-safe-id",
            evidence_id="evidence-safe-id",
            error_type="RuntimeError",
        )

    assert events == [
        {
            "operation": "evidence_upload",
            "compensation_step": "object_delete",
            "result": "failed",
            "tenant_id": "tenant-safe-id",
            "case_id": "case-safe-id",
            "evidence_id": "evidence-safe-id",
            "error_type": "RuntimeError",
            "event": "evidence_upload_compensation_failed",
            "log_level": "error",
        }
    ]
    assert (
        not {
            "object_key",
            "url",
            "content",
            "exception",
            "secret",
        }
        & events[0].keys()
    )
