"""Authorization and tenant scoping for report/KPI reads."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.poc_reporting import GetCaseReviewReport, GetPocSummary
from app.platform.poc_reporting import (
    CustomerCommunicationSimulation,
    DataAssetSummary,
    MetricUnit,
    PocMetric,
    PocSummary,
    ReviewReport,
)
from app.platform.tenant import Principal, Role

pytestmark = pytest.mark.unit


class _Repository:
    def __init__(self) -> None:
        self.tenant_ids: list[str] = []

    def get_review_report(self, *, tenant_id: str, case_id: str) -> ReviewReport | None:
        self.tenant_ids.append(tenant_id)
        return ReviewReport.create(
            report_id="report-1",
            tenant_id=tenant_id,
            case_id=case_id,
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
            generated_at=datetime(2026, 8, 27, tzinfo=UTC),
        )

    def get_poc_summary(self, *, tenant_id: str) -> PocSummary:
        self.tenant_ids.append(tenant_id)
        empty = PocMetric.from_fraction(
            numerator=0,
            denominator=0,
            sample_count=0,
            unit=MetricUnit.RATIO,
        )
        seconds = empty.model_copy(update={"unit": MetricUnit.SECONDS})
        return PocSummary(
            generated_at=datetime(2026, 8, 27, tzinfo=UTC),
            review_time=seconds,
            recommendation_difference_rate=empty,
            additional_evidence_request_rate=empty,
            action_input_missing_rate=empty,
            dry_run_success_rate=empty,
            analysis_failure_rate=empty,
            analysis_partial_success_rate=empty,
        )

    def create_customer_communication(
        self, *, tenant_id: str, case_id: str, created_by: str
    ) -> CustomerCommunicationSimulation:
        raise NotImplementedError

    def list_customer_communications(
        self, *, tenant_id: str, case_id: str
    ) -> tuple[CustomerCommunicationSimulation, ...]:
        return ()

    def get_data_asset_summary(self, *, tenant_id: str) -> DataAssetSummary:
        raise NotImplementedError


def _principal(role: Role) -> Principal:
    return Principal(
        user_id="user-1",
        tenant_id="tenant-1",
        email="user@example.test",
        display_name="User",
        roles=frozenset({role}),
    )


def test_report_and_metrics_always_use_authenticated_tenant() -> None:
    repository = _Repository()
    report = GetCaseReviewReport(repository).execute(
        principal=_principal(Role.QUALITY_VIEWER),
        case_id="case-1",
    )
    summary = GetPocSummary(repository).execute(principal=_principal(Role.REVIEWER))
    assert report.tenant_id == "tenant-1"
    assert summary.review_time.value is None
    assert repository.tenant_ids == ["tenant-1", "tenant-1"]
