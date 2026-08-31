"""Admin authorization and HTTP contracts for aggregate operations reads."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application.operations import GetOperationsFailures, GetOperationsOverview
from app.interface.http import register_exception_handlers
from app.interface.http.operations_services import OperationsServiceContainer
from app.interface.http.routers.operations import router
from app.interface.http.services import Sprint1ServiceContainer
from app.platform.errors import AuthenticationRequiredError, ForbiddenError
from app.platform.operations import (
    ActiveVersionSnapshot,
    ComponentFailureSummary,
    FailureCodeCount,
    OperationsComponent,
    OperationsFailures,
    OperationsOverview,
    OperationsQueue,
    OperationsVersionKind,
    OperationsVersionSource,
    ProcessingOperationsSnapshot,
    QueueOperationsSnapshot,
)
from app.platform.tenant import Principal, Role
from tests.case_assignment_support import AllowCaseAccess

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
TENANT_ID = str(uuid4())
OTHER_TENANT_ID = str(uuid4())
USER_ID = str(uuid4())


class _FixedClock:
    def now(self) -> datetime:
        return NOW


class _Repository:
    def __init__(self) -> None:
        self.overview_calls: list[dict[str, object]] = []
        self.failure_calls: list[dict[str, object]] = []

    def get_overview(
        self,
        *,
        tenant_id: str,
        now: datetime,
        stalled_before: datetime,
    ) -> OperationsOverview:
        self.overview_calls.append(
            {
                "tenant_id": tenant_id,
                "now": now,
                "stalled_before": stalled_before,
            }
        )
        return OperationsOverview(
            generated_at=now,
            stalled_after_seconds=int((now - stalled_before).total_seconds()),
            total_backlog_count=4,
            total_stalled_count=1,
            queues=(
                QueueOperationsSnapshot(
                    queue=OperationsQueue.ANALYSIS_DISPATCH,
                    backlog_count=3,
                    pending_count=2,
                    processing_count=1,
                    published_unconsumed_count=0,
                    failed_count=1,
                    retry_count=1,
                    stalled_count=1,
                    oldest_backlog_age_seconds=601,
                    last_healthy_at=now - timedelta(minutes=2),
                ),
            ),
            processing=(
                ProcessingOperationsSnapshot(
                    component=OperationsComponent.ANALYSIS,
                    backlog_count=1,
                    running_count=1,
                    retry_count=0,
                    partial_success_count=1,
                    failed_count=1,
                    stalled_count=0,
                    oldest_backlog_age_seconds=30,
                    last_healthy_at=now - timedelta(minutes=1),
                ),
            ),
            active_versions=(
                ActiveVersionSnapshot(
                    kind=OperationsVersionKind.POLICY,
                    component="policy_evaluation",
                    name="refund_policy",
                    version="2026-08-29",
                    source=OperationsVersionSource.ACTIVE_RECORD,
                    observed_at=now - timedelta(hours=1),
                ),
            ),
        )

    def get_failures(
        self,
        *,
        tenant_id: str,
        now: datetime,
        since: datetime,
        stalled_before: datetime,
    ) -> OperationsFailures:
        self.failure_calls.append(
            {
                "tenant_id": tenant_id,
                "now": now,
                "since": since,
                "stalled_before": stalled_before,
            }
        )
        return OperationsFailures(
            generated_at=now,
            lookback_seconds=int((now - since).total_seconds()),
            total_failed_count=2,
            total_partial_success_count=1,
            total_retry_count=1,
            total_stalled_count=1,
            components=(
                ComponentFailureSummary(
                    component=OperationsComponent.ANALYSIS,
                    failed_count=2,
                    partial_success_count=1,
                    retry_count=1,
                    stalled_count=1,
                    oldest_signal_at=now - timedelta(hours=2),
                    latest_signal_at=now - timedelta(minutes=10),
                    last_healthy_at=now - timedelta(minutes=5),
                    top_failure_codes=(FailureCodeCount(code="PROVIDER_TIMEOUT", count=2),),
                ),
            ),
        )


class _ResolvePrincipal:
    def execute(self, token: str) -> Principal:
        if token not in {"admin-token", "other-admin-token", "reviewer-token"}:
            raise AuthenticationRequiredError()
        role = Role.REVIEWER if token == "reviewer-token" else Role.ADMIN
        return Principal(
            user_id=USER_ID,
            tenant_id=OTHER_TENANT_ID if token == "other-admin-token" else TENANT_ID,
            email=f"{role.value.lower()}@example.test",
            display_name=role.value.title(),
            roles=frozenset({role}),
        )


def _principal(role: Role = Role.ADMIN) -> Principal:
    return Principal(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        email=f"{role.value.lower()}@example.test",
        display_name=role.value.title(),
        roles=frozenset({role}),
    )


def _services(repository: _Repository) -> OperationsServiceContainer:
    return OperationsServiceContainer(
        get_overview=GetOperationsOverview(repository, _FixedClock()),
        get_failures=GetOperationsFailures(repository, _FixedClock()),
    )


def _client(repository: _Repository, *, configure_operations: bool = True) -> TestClient:
    application = FastAPI()
    register_exception_handlers(application)
    application.include_router(router)
    unused: Any = object()
    application.state.sprint1_services = Sprint1ServiceContainer(
        authenticate_user=unused,
        resolve_principal=_ResolvePrincipal(),
        create_case=unused,
        list_cases=unused,
        get_case=unused,
        get_case_status_history=unused,
        add_image_evidence=unused,
        list_case_evidence=unused,
        get_evidence_metadata=unused,
        create_evidence_access_url=unused,
        get_case_assignment=unused,
        assign_case=unused,
        authorize_case_access=AllowCaseAccess(),  # pyright: ignore[reportArgumentType]
    )
    if configure_operations:
        application.state.operations_services = _services(repository)
    return TestClient(application, raise_server_exceptions=False)


def _assert_no_high_cardinality_identifiers(value: object) -> None:
    if isinstance(value, dict):
        assert "tenant_id" not in value
        assert "case_id" not in value
        for item in value.values():
            _assert_no_high_cardinality_identifiers(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_high_cardinality_identifiers(item)
    elif isinstance(value, str):
        assert value not in {TENANT_ID, OTHER_TENANT_ID, USER_ID}


def test_application_services_require_admin_and_apply_time_windows() -> None:
    repository = _Repository()
    services = _services(repository)

    overview = services.get_overview.execute(principal=_principal())
    failures = services.get_failures.execute(principal=_principal(), lookback_hours=72)

    assert overview.total_backlog_count == 4
    assert failures.lookback_seconds == 72 * 60 * 60
    assert repository.overview_calls == [
        {
            "tenant_id": TENANT_ID,
            "now": NOW,
            "stalled_before": NOW - timedelta(minutes=5),
        }
    ]
    assert repository.failure_calls[0]["tenant_id"] == TENANT_ID
    assert repository.failure_calls[0]["since"] == NOW - timedelta(hours=72)
    assert repository.failure_calls[0]["stalled_before"] == NOW - timedelta(minutes=5)

    with pytest.raises(ForbiddenError):
        services.get_overview.execute(principal=_principal(Role.REVIEWER))
    with pytest.raises(ForbiddenError):
        services.get_failures.execute(principal=_principal(Role.QUALITY_VIEWER))


def test_operations_routes_are_admin_only_tenant_scoped_and_low_cardinality() -> None:
    repository = _Repository()
    client = _client(repository)
    headers = {"Authorization": "Bearer admin-token"}

    overview = client.get("/api/v1/operations/overview", headers=headers)
    failures = client.get(
        "/api/v1/operations/failures?lookback_hours=48",
        headers=headers,
    )

    assert overview.status_code == 200
    assert overview.headers["Cache-Control"] == "no-store"
    assert overview.headers["Pragma"] == "no-cache"
    assert overview.json()["queues"][0]["queue"] == "analysis_dispatch"
    assert failures.status_code == 200
    assert failures.headers["Cache-Control"] == "no-store"
    assert failures.json()["components"][0]["top_failure_codes"] == [
        {"code": "PROVIDER_TIMEOUT", "count": 2}
    ]
    assert repository.overview_calls[0]["tenant_id"] == TENANT_ID
    assert repository.failure_calls[0]["tenant_id"] == TENANT_ID
    assert repository.failure_calls[0]["since"] == NOW - timedelta(hours=48)
    _assert_no_high_cardinality_identifiers(overview.json())
    _assert_no_high_cardinality_identifiers(failures.json())


def test_operations_routes_reject_non_admin_invalid_window_and_missing_service() -> None:
    repository = _Repository()
    client = _client(repository)

    reviewer = client.get(
        "/api/v1/operations/overview",
        headers={"Authorization": "Bearer reviewer-token"},
    )
    missing_auth = client.get("/api/v1/operations/overview")
    invalid_window = client.get(
        "/api/v1/operations/failures?lookback_hours=169",
        headers={"Authorization": "Bearer admin-token"},
    )
    unavailable = _client(repository, configure_operations=False).get(
        "/api/v1/operations/overview",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert reviewer.status_code == 403
    assert missing_auth.status_code == 401
    assert invalid_window.status_code == 422
    assert unavailable.status_code == 503
    assert repository.overview_calls == []


def test_failure_lookback_openapi_contract_is_bounded_integer() -> None:
    schema = cast(FastAPI, _client(_Repository()).app).openapi()
    parameters = schema["paths"]["/api/v1/operations/failures"]["get"]["parameters"]
    lookback = next(item for item in parameters if item["name"] == "lookback_hours")

    assert lookback["schema"]["type"] == "integer"
    assert lookback["schema"]["minimum"] == 1
    assert lookback["schema"]["maximum"] == 168
    assert lookback["schema"]["default"] == 24
