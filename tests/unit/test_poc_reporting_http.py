"""HTTP contracts for immutable Review Reports and denominator-visible PoC KPIs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.application.poc_reporting import GetCaseReviewReport, GetPocSummary
from app.bootstrap.settings import Settings
from app.interface.http.poc_reporting_services import PocReportingServiceContainer
from app.interface.http.services import Sprint1ServiceContainer
from app.main import create_app
from app.platform.errors import AuthenticationRequiredError
from app.platform.poc_reporting import MetricUnit, PocMetric, PocSummary, ReviewReport
from app.platform.tenant import Principal, Role

pytestmark = pytest.mark.unit
NOW = datetime(2026, 8, 27, tzinfo=UTC)
TENANT_ID = str(uuid4())
OTHER_TENANT_ID = str(uuid4())
CASE_ID = str(uuid4())


class _ResolvePrincipal:
    def execute(self, token: str) -> Principal:
        if token == "viewer-token":
            tenant_id = TENANT_ID
        elif token == "other-token":
            tenant_id = OTHER_TENANT_ID
        else:
            raise AuthenticationRequiredError()
        return Principal(
            user_id=str(uuid4()),
            tenant_id=tenant_id,
            email="viewer@example.test",
            display_name="Viewer",
            roles=frozenset({Role.QUALITY_VIEWER}),
        )


def _metric(
    numerator: float,
    denominator: int,
    *,
    unit: MetricUnit = MetricUnit.RATIO,
    sample_count: int | None = None,
) -> PocMetric:
    return PocMetric.from_fraction(
        numerator=numerator,
        denominator=denominator,
        sample_count=denominator if sample_count is None else sample_count,
        unit=unit,
    )


class _Repository:
    def __init__(self) -> None:
        self.report_tenants: list[str] = []
        self.metric_tenants: list[str] = []

    def get_review_report(self, *, tenant_id: str, case_id: str) -> ReviewReport | None:
        self.report_tenants.append(tenant_id)
        if tenant_id != TENANT_ID or case_id != CASE_ID:
            return None
        return ReviewReport.create(
            report_id=str(uuid4()),
            tenant_id=tenant_id,
            case_id=case_id,
            resolution_id=str(uuid4()),
            resolution_version=4,
            terminal_event_id=str(uuid4()),
            case_snapshot={"order_ref": "ORDER-1"},
            analysis_snapshot={"status": "SUCCEEDED"},
            policy_snapshot={"summary_status": "REQUIRES_HUMAN_REVIEW"},
            review_snapshot={"decision_type": "APPROVE_REPAIR"},
            resolution_snapshot={"status": "ACTION_DRY_RUN_VALIDATED"},
            dry_run_snapshot={"side_effects_performed": False},
            qualification_snapshot={"vision": "MOCK_QUALIFIED"},
            data_scope={"case_data_scope": "NOT_ATTESTED"},
            generated_at=NOW,
        )

    def get_poc_summary(self, *, tenant_id: str) -> PocSummary:
        self.metric_tenants.append(tenant_id)
        return PocSummary(
            generated_at=NOW,
            review_time=_metric(
                125.5,
                2,
                unit=MetricUnit.SECONDS,
                sample_count=3,
            ),
            recommendation_difference_rate=_metric(1, 4),
            additional_evidence_request_rate=_metric(2, 5),
            action_input_missing_rate=_metric(1, 3),
            dry_run_success_rate=_metric(2, 2),
            analysis_failure_rate=_metric(1, 10),
            analysis_partial_success_rate=_metric(2, 10),
        )


def _client(repository: _Repository) -> TestClient:
    unused: Any = object()
    sprint1 = Sprint1ServiceContainer(
        authenticate_user=unused,
        resolve_principal=_ResolvePrincipal(),  # pyright: ignore[reportArgumentType]
        create_case=unused,
        list_cases=unused,
        get_case=unused,
        get_case_status_history=unused,
        add_image_evidence=unused,
        list_case_evidence=unused,
        get_evidence_metadata=unused,
        create_evidence_access_url=unused,
    )
    reporting = PocReportingServiceContainer(
        get_case_review_report=GetCaseReviewReport(repository),  # pyright: ignore[reportArgumentType]
        get_poc_summary=GetPocSummary(repository),  # pyright: ignore[reportArgumentType]
    )
    return TestClient(
        create_app(
            Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
            sprint1_services=sprint1,
            poc_reporting_services=reporting,
        )
    )


def test_report_and_metric_routes_are_tenant_scoped_and_no_store() -> None:
    repository = _Repository()
    client = _client(repository)
    headers = {"Authorization": "Bearer viewer-token"}

    report = client.get(f"/api/v1/cases/{CASE_ID}/review-report", headers=headers)
    summary = client.get("/api/v1/metrics/poc-summary", headers=headers)

    assert report.status_code == 200
    assert report.headers["Cache-Control"] == "no-store"
    assert report.headers["Pragma"] == "no-cache"
    assert "tenant_id" not in report.json()
    assert report.json()["resolution_snapshot"]["status"] == "ACTION_DRY_RUN_VALIDATED"
    assert summary.status_code == 200
    assert summary.headers["Cache-Control"] == "no-store"
    assert summary.headers["Pragma"] == "no-cache"
    assert summary.json()["review_time"] == {
        "numerator": 125.5,
        "denominator": 2,
        "sample_count": 3,
        "value": 62.75,
        "unit": "seconds",
    }
    assert repository.report_tenants == [TENANT_ID]
    assert repository.metric_tenants == [TENANT_ID]


def test_report_route_hides_other_tenant_and_rejects_malformed_case_id() -> None:
    repository = _Repository()
    client = _client(repository)
    other = client.get(
        f"/api/v1/cases/{CASE_ID}/review-report",
        headers={"Authorization": "Bearer other-token"},
    )
    malformed = client.get(
        "/api/v1/cases/not-a-uuid/review-report",
        headers={"Authorization": "Bearer viewer-token"},
    )

    assert other.status_code == 404
    assert other.json()["error"]["code"] == "REVIEW_REPORT_NOT_FOUND"
    assert malformed.status_code == 422
    assert repository.report_tenants == [OTHER_TENANT_ID]


def test_reporting_routes_require_authentication() -> None:
    client = _client(_Repository())
    assert client.get(f"/api/v1/cases/{CASE_ID}/review-report").status_code == 401
    assert client.get("/api/v1/metrics/poc-summary").status_code == 401
