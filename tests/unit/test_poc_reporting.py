"""Immutable report integrity and denominator-visible KPI contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Table, UniqueConstraint

from app.adapters.persistence.models import (
    PERSISTENCE_MODELS,
    CaseResolutionEventModel,
    ReviewReportModel,
)
from app.platform.poc_reporting import MetricUnit, PocMetric, ReviewReport

pytestmark = pytest.mark.unit


def _report() -> ReviewReport:
    return ReviewReport.create(
        report_id="report-1",
        tenant_id="tenant-1",
        case_id="case-1",
        resolution_id="resolution-1",
        resolution_version=4,
        terminal_event_id="event-4",
        case_snapshot={"order_ref": "ORDER-1"},
        analysis_snapshot={"status": "SUCCEEDED"},
        policy_snapshot={"summary_status": "REQUIRES_HUMAN_REVIEW"},
        review_snapshot={"decision": "APPROVE_REPAIR"},
        resolution_snapshot={"status": "ACTION_DRY_RUN_VALIDATED"},
        dry_run_snapshot={"side_effects_performed": False},
        qualification_snapshot={"vision": "MOCK_QUALIFIED"},
        data_scope={"customer_data": "SYNTHETIC"},
        generated_at=datetime(2026, 8, 27, tzinfo=UTC),
    )


def test_review_report_hash_is_immutable_and_sensitive_to_snapshot() -> None:
    report = _report()
    assert len(report.content_hash) == 64
    payload = report.model_dump(mode="json")
    payload["case_snapshot"] = {"order_ref": "TAMPERED"}
    with pytest.raises(ValidationError, match="content hash mismatch"):
        ReviewReport.model_validate(payload)


def test_review_report_factory_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ReviewReport.create(
            report_id="report-1",
            tenant_id="tenant-1",
            case_id="case-1",
            resolution_id="resolution-1",
            resolution_version=1,
            terminal_event_id="event-1",
            case_snapshot={},
            analysis_snapshot={},
            policy_snapshot={},
            review_snapshot={},
            resolution_snapshot={},
            dry_run_snapshot={},
            qualification_snapshot={},
            data_scope={},
            generated_at=datetime(2026, 8, 27),
        )


def test_zero_denominator_is_null_not_zero_percent() -> None:
    metric = PocMetric.from_fraction(
        numerator=0,
        denominator=0,
        sample_count=0,
        unit=MetricUnit.RATIO,
    )
    assert metric.value is None


def test_review_time_uses_interval_sum_and_resolved_task_denominator() -> None:
    metric = PocMetric.from_fraction(
        numerator=125.5,
        denominator=2,
        sample_count=3,
        unit=MetricUnit.SECONDS,
    )
    assert metric.value == 62.75


def test_ratio_rejects_impossible_counts() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        PocMetric.from_fraction(
            numerator=2,
            denominator=1,
            sample_count=2,
            unit=MetricUnit.RATIO,
        )


def test_review_report_mapping_matches_typed_event_identity_and_immutability_guards() -> None:
    assert ReviewReportModel in PERSISTENCE_MODELS
    report_table = cast(Table, ReviewReportModel.__table__)
    event_table = cast(Table, CaseResolutionEventModel.__table__)
    report_constraints = {str(item.name): item for item in report_table.constraints}
    event_constraints = {str(item.name): item for item in event_table.constraints}

    assert isinstance(report_constraints["fk_review_reports_terminal_event"], ForeignKeyConstraint)
    assert isinstance(report_constraints["uq_review_reports_resolution_version"], UniqueConstraint)
    assert isinstance(
        report_constraints["ck_review_reports_schema_version_supported"], CheckConstraint
    )
    assert "schema_version = 'review_report/1.0.0'" in str(
        report_constraints["ck_review_reports_schema_version_supported"].sqltext  # pyright: ignore[reportAttributeAccessIssue]
    )
    assert isinstance(
        event_constraints["uq_case_resolution_events_tenant_case_resolution_id"],
        UniqueConstraint,
    )
