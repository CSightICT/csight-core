"""Bounded scheduling, alert-state, and health contracts for retention automation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import pytest

from app.interface.maintenance.privacy_lifecycle import (
    retention_healthcheck,
    run_automation_loop,
    run_retention_sweep,
)
from app.platform.privacy_lifecycle import (
    LifecycleFinding,
    LifecycleFindingKind,
    LifecycleFindingOutcome,
    LifecycleRunMode,
    LifecycleRunReport,
)
from app.platform.tenant_context import (
    current_actor_id,
    current_case_access_all,
    current_tenant_id,
)

pytestmark = pytest.mark.unit
TENANT_ID = "00000000-0000-4000-8000-000000000001"
NOW = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)


def _report(
    *,
    scanned: int,
    applied: int,
    blocked: int = 0,
    truncated: bool = False,
) -> LifecycleRunReport:
    findings = tuple(
        LifecycleFinding(
            kind=LifecycleFindingKind.SENSITIVE_PAYLOAD_EXPIRED,
            outcome=LifecycleFindingOutcome.BLOCKED,
            case_id="00000000-0000-4000-8000-000000000002",
            resource_id="00000000-0000-4000-8000-000000000003",
            reason="payload_digest_mismatch",
        )
        for _ in range(blocked)
    )
    return LifecycleRunReport(
        mode=LifecycleRunMode.EXECUTE,
        tenant_id=TENANT_ID,
        generated_at=NOW,
        scanned_count=scanned,
        planned_count=0,
        applied_count=applied,
        already_applied_count=0,
        blocked_count=blocked,
        truncated=truncated,
        findings=findings,
    )


class Reports:
    def __init__(self, *reports: LifecycleRunReport) -> None:
        self.reports = list(reports)
        self.calls: list[tuple[str, int]] = []

    def execute_automated(self, *, tenant_id: str, limit: int) -> LifecycleRunReport:
        assert current_tenant_id() == tenant_id
        assert current_case_access_all() is True
        assert current_actor_id() is None
        self.calls.append((tenant_id, limit))
        return self.reports.pop(0)


def test_sweep_drains_multiple_bounded_batches() -> None:
    service = Reports(
        _report(scanned=2, applied=2, truncated=True),
        _report(scanned=1, applied=1),
    )

    result = run_retention_sweep(
        service,
        tenant_id=TENANT_ID,
        batch_size=2,
        max_batches=3,
    )

    assert result.passed is True
    assert result.scanned_count == 3
    assert result.applied_count == 3
    assert result.batch_count == 2
    assert service.calls == [(TENANT_ID, 2), (TENANT_ID, 2)]
    assert current_tenant_id() is None
    assert current_case_access_all() is False


def test_sweep_stops_on_blocked_item_instead_of_looping() -> None:
    service = Reports(
        _report(scanned=2, applied=1, blocked=1, truncated=True),
        _report(scanned=1, applied=1),
    )

    result = run_retention_sweep(
        service,
        tenant_id=TENANT_ID,
        batch_size=2,
        max_batches=3,
    )

    assert result.passed is False
    assert result.blocked_count == 1
    assert result.truncated is True
    assert service.calls == [(TENANT_ID, 2)]


def test_sweep_reports_truncation_after_configured_batch_cap() -> None:
    service = Reports(
        _report(scanned=1, applied=1, truncated=True),
        _report(scanned=1, applied=1, truncated=True),
    )

    result = run_retention_sweep(
        service,
        tenant_id=TENANT_ID,
        batch_size=1,
        max_batches=2,
    )

    assert result.passed is False
    assert result.applied_count == 2
    assert result.truncated is True


def test_healthcheck_rejects_missing_failed_and_stale_state(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    assert retention_healthcheck(path=path, interval_seconds=60, now_epoch=1000) is False

    path.write_text(
        '{"status":"attention_required","recorded_at_epoch":990}',
        encoding="utf-8",
    )
    assert retention_healthcheck(path=path, interval_seconds=60, now_epoch=1000) is False

    path.write_text('{"status":"ok","recorded_at_epoch":700}', encoding="utf-8")
    assert retention_healthcheck(path=path, interval_seconds=60, now_epoch=1000) is False

    path.write_text('{"status":"ok","recorded_at_epoch":900}', encoding="utf-8")
    assert retention_healthcheck(path=path, interval_seconds=60, now_epoch=1000) is True


def test_sweep_exception_overwrites_previous_health_with_failure(tmp_path: Path) -> None:
    path = tmp_path / "health.json"
    path.write_text(
        '{"status":"ok","recorded_at_epoch":9999999999}',
        encoding="utf-8",
    )
    service = Reports()

    assert (
        run_automation_loop(
            service,
            tenant_id=TENANT_ID,
            batch_size=1,
            max_batches=1,
            interval_seconds=60,
            health_file=path,
            once=True,
            stop_event=Event(),
        )
        == 1
    )
    assert retention_healthcheck(path=path, interval_seconds=60) is False
