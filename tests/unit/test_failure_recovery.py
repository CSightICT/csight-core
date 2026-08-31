"""Admin boundary and public contracts for durable failure recovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.messaging.celery import CeleryOperationalRecoveryMessageQueue
from app.adapters.persistence.models import (
    OperationalFailureModel,
    OperationalFailureRecoveryEventModel,
    OperationalFailureRecoveryRunModel,
    OperationalFailureResolutionModel,
)
from app.application.operations import (
    CancelOperationalFailure,
    GetOperationsFailures,
    GetOperationsOverview,
    ListOperationalFailures,
    ReplayOperationalFailure,
)
from app.interface.http import register_exception_handlers
from app.interface.http.operations_services import OperationsServiceContainer
from app.interface.http.routers.operations import router
from app.interface.http.services import Sprint1ServiceContainer
from app.platform.errors import AuthenticationRequiredError, ForbiddenError
from app.platform.operations import (
    OperationalFailureAction,
    OperationalFailureKind,
    OperationalFailurePage,
    OperationalFailurePipeline,
    OperationalFailureRecord,
    OperationalFailureResolutionResult,
    OperationalFailureStatus,
    OperationsFailures,
    OperationsOverview,
)
from app.platform.tenant import Principal, Role
from tests.case_assignment_support import AllowCaseAccess

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
TENANT_ID = str(uuid4())
OTHER_TENANT_ID = str(uuid4())
USER_ID = str(uuid4())
FAILURE_ID = str(uuid4())
SOURCE_EVENT_ID = str(uuid4())
SOURCE_RUN_ID = str(uuid4())
RECOVERY_RUN_ID = str(uuid4())
RECOVERY_EVENT_ID = str(uuid4())


class _Clock:
    def now(self) -> datetime:
        return NOW


class _AggregateRepository:
    def get_overview(
        self,
        *,
        tenant_id: str,
        now: datetime,
        stalled_before: datetime,
    ) -> OperationsOverview:
        return OperationsOverview(
            generated_at=now,
            stalled_after_seconds=int((now - stalled_before).total_seconds()),
            total_backlog_count=0,
            total_stalled_count=0,
            queues=(),
            processing=(),
            active_versions=(),
        )

    def get_failures(
        self,
        *,
        tenant_id: str,
        now: datetime,
        since: datetime,
        stalled_before: datetime,
    ) -> OperationsFailures:
        return OperationsFailures(
            generated_at=now,
            lookback_seconds=int((now - since).total_seconds()),
            total_failed_count=1,
            total_partial_success_count=0,
            total_retry_count=0,
            total_stalled_count=0,
            components=(),
        )


class _FailureRepository:
    def __init__(self) -> None:
        self.list_calls: list[dict[str, object]] = []
        self.replay_calls: list[dict[str, str]] = []
        self.cancel_calls: list[dict[str, str]] = []

    def list_failures(
        self,
        *,
        tenant_id: str,
        since: datetime,
        limit: int,
        cursor: str | None,
    ) -> OperationalFailurePage:
        self.list_calls.append(
            {"tenant_id": tenant_id, "since": since, "limit": limit, "cursor": cursor}
        )
        return OperationalFailurePage(
            items=(
                OperationalFailureRecord(
                    failure_id=FAILURE_ID,
                    pipeline=OperationalFailurePipeline.POLICY_RETRIEVAL,
                    failure_kind=OperationalFailureKind.DISPATCH,
                    failure_code="POLICY_RETRIEVAL_OUTBOX_FAILED",
                    source_event_id=SOURCE_EVENT_ID,
                    source_run_id=SOURCE_RUN_ID,
                    correlation_id="corr-failure",
                    replayable=True,
                    status=OperationalFailureStatus.OPEN,
                    occurred_at=NOW - timedelta(minutes=5),
                ),
            ),
            next_cursor="opaque-next",
        )

    def replay_failure(
        self,
        *,
        tenant_id: str,
        failure_id: str,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> OperationalFailureResolutionResult:
        self.replay_calls.append(
            {
                "tenant_id": tenant_id,
                "failure_id": failure_id,
                "actor_id": actor_id,
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
            }
        )
        return OperationalFailureResolutionResult(
            failure_id=failure_id,
            action=OperationalFailureAction.REPLAYED,
            recovery_run_id=RECOVERY_RUN_ID,
            recovery_event_id=RECOVERY_EVENT_ID,
            created_at=NOW,
            idempotent_replay=len(self.replay_calls) > 1,
        )

    def cancel_failure(
        self,
        *,
        tenant_id: str,
        failure_id: str,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> OperationalFailureResolutionResult:
        self.cancel_calls.append(
            {
                "tenant_id": tenant_id,
                "failure_id": failure_id,
                "actor_id": actor_id,
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
            }
        )
        return OperationalFailureResolutionResult(
            failure_id=failure_id,
            action=OperationalFailureAction.CANCELLED,
            created_at=NOW,
        )


class _ResolvePrincipal:
    def execute(self, token: str) -> Principal:
        if token not in {"admin-token", "reviewer-token"}:
            raise AuthenticationRequiredError()
        role = Role.ADMIN if token == "admin-token" else Role.REVIEWER
        return _principal(role)


def _principal(role: Role = Role.ADMIN) -> Principal:
    return Principal(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        email="operator@example.test",
        display_name="Operator",
        roles=frozenset({role}),
    )


def _services(failures: _FailureRepository) -> OperationsServiceContainer:
    aggregate = _AggregateRepository()
    return OperationsServiceContainer(
        get_overview=GetOperationsOverview(aggregate, _Clock()),
        get_failures=GetOperationsFailures(aggregate, _Clock()),
        list_failure_records=ListOperationalFailures(failures, _Clock()),
        replay_failure=ReplayOperationalFailure(failures),
        cancel_failure=CancelOperationalFailure(failures),
    )


def _client(failures: _FailureRepository) -> TestClient:
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
    application.state.operations_services = _services(failures)
    return TestClient(application, raise_server_exceptions=False)


def test_failure_use_cases_are_admin_only_and_tenant_scoped() -> None:
    repository = _FailureRepository()
    services = _services(repository)

    page = services.list_failure_records
    replay = services.replay_failure
    cancel = services.cancel_failure
    assert page is not None and replay is not None and cancel is not None
    listed = page.execute(principal=_principal(), lookback_hours=12, limit=25)
    replayed = replay.execute(
        principal=_principal(),
        failure_id=FAILURE_ID,
        idempotency_key="replay-1",
        correlation_id="corr-request",
    )
    cancelled = cancel.execute(
        principal=_principal(),
        failure_id=FAILURE_ID,
        idempotency_key="cancel-1",
        correlation_id="corr-cancel",
    )

    assert listed.items[0].failure_id == FAILURE_ID
    assert repository.list_calls == [
        {
            "tenant_id": TENANT_ID,
            "since": NOW - timedelta(hours=12),
            "limit": 25,
            "cursor": None,
        }
    ]
    assert replayed.recovery_run_id == RECOVERY_RUN_ID
    assert cancelled.action is OperationalFailureAction.CANCELLED
    assert repository.replay_calls[0]["tenant_id"] == TENANT_ID
    assert repository.replay_calls[0]["actor_id"] == USER_ID

    reviewer = _principal(Role.REVIEWER)
    with pytest.raises(ForbiddenError):
        page.execute(principal=reviewer, lookback_hours=24, limit=50, cursor=None)
    with pytest.raises(ForbiddenError):
        replay.execute(
            principal=reviewer,
            failure_id=FAILURE_ID,
            idempotency_key="replay-2",
            correlation_id="corr",
        )
    with pytest.raises(ForbiddenError):
        cancel.execute(
            principal=reviewer,
            failure_id=FAILURE_ID,
            idempotency_key="cancel-2",
            correlation_id="corr",
        )


def test_admin_failure_http_list_replay_idempotency_and_cancel_contracts() -> None:
    repository = _FailureRepository()
    client = _client(repository)
    auth = {"Authorization": "Bearer admin-token"}

    listed = client.get(
        "/api/v1/operations/failures?lookback_hours=12&limit=25",
        headers=auth,
    )
    replay_headers = {
        **auth,
        "Idempotency-Key": "replay-http-1",
        "X-Correlation-ID": "corr-http",
    }
    replayed = client.post(
        f"/api/v1/operations/failures/{FAILURE_ID}/replay",
        headers=replay_headers,
    )
    replayed_again = client.post(
        f"/api/v1/operations/failures/{FAILURE_ID}/replay",
        headers=replay_headers,
    )
    cancelled = client.post(
        f"/api/v1/operations/failures/{FAILURE_ID}/cancel",
        headers={**auth, "Idempotency-Key": "cancel-http-1"},
    )
    reviewer = client.post(
        f"/api/v1/operations/failures/{FAILURE_ID}/replay",
        headers={"Authorization": "Bearer reviewer-token", "Idempotency-Key": "blocked"},
    )

    assert listed.status_code == 200
    assert listed.json()["items"][0]["failure_id"] == FAILURE_ID
    assert listed.json()["next_cursor"] == "opaque-next"
    assert replayed.status_code == 202
    assert replayed.json()["recovery_event_id"] == RECOVERY_EVENT_ID
    assert replayed_again.status_code == 200
    assert replayed_again.json()["idempotent_replay"] is True
    assert cancelled.status_code == 200
    assert cancelled.json()["action"] == "CANCELLED"
    assert reviewer.status_code == 403
    assert all(
        response.headers["Cache-Control"] == "no-store"
        for response in (
            listed,
            replayed,
            replayed_again,
            cancelled,
        )
    )


def test_failure_recovery_openapi_declares_admin_mutations_and_required_key() -> None:
    schema = cast(FastAPI, _client(_FailureRepository()).app).openapi()
    replay = schema["paths"]["/api/v1/operations/failures/{failure_id}/replay"]["post"]
    cancel = schema["paths"]["/api/v1/operations/failures/{failure_id}/cancel"]["post"]

    replay_key = next(item for item in replay["parameters"] if item["name"] == "Idempotency-Key")
    cancel_key = next(item for item in cancel["parameters"] if item["name"] == "Idempotency-Key")
    assert replay["responses"].keys() >= {"200", "202", "403", "404", "409"}
    assert cancel["responses"].keys() >= {"200", "403", "404", "409"}
    assert replay_key["in"] == "header" and replay_key["required"] is True
    assert cancel_key["in"] == "header" and cancel_key["required"] is True


class _CeleryStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def send_task(self, topic: str, **values: object) -> None:
        self.calls.append({"topic": topic, **values})


def test_recovery_queue_reuses_pipeline_queue_and_rejects_non_identifier_payload() -> None:
    celery = _CeleryStub()
    queue = CeleryOperationalRecoveryMessageQueue(cast(Any, celery))
    event_id = str(uuid4())
    payload = {
        "event_id": event_id,
        "tenant_id": TENANT_ID,
        "case_id": str(uuid4()),
        "retrieval_run_id": SOURCE_RUN_ID,
        "correlation_id": "corr-safe",
    }

    assert (
        queue.publish(
            topic="policy_retrieval.requested.v1",
            payload=payload,
            correlation_id="corr-safe",
        )
        == event_id
    )
    assert celery.calls == [
        {
            "topic": "policy_retrieval.requested.v1",
            "args": [payload],
            "task_id": event_id,
            "queue": "policy-retrieval",
            "headers": {"correlation_id": "corr-safe"},
        }
    ]
    with pytest.raises(ValueError, match="exactly five IDs"):
        queue.publish(
            topic="policy_retrieval.requested.v1",
            payload={**payload, "customer_message": "must never enter recovery"},
            correlation_id="corr-safe",
        )


def test_failure_recovery_migration_is_linear_rls_scoped_and_pii_free() -> None:
    config = Config()
    config.set_main_option("script_location", str(Path("alembic")))
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision("20260829_0021_failure_recovery")
    assert revision is not None
    assert revision.down_revision == "20260829_0020_postgres_rls_roles"
    privacy_revision = scripts.get_revision("20260829_0022_privacy_lifecycle")
    assert privacy_revision.down_revision == revision.revision

    source = Path("alembic/versions/20260829_0021_failure_recovery.py").read_text(encoding="utf-8")
    for contract in (
        "operational_failures",
        "operational_failure_recovery_runs",
        "operational_failure_recovery_events",
        "operational_failure_resolutions",
        "SECURITY DEFINER",
        "FORCE ROW LEVEL SECURITY",
        "csight_dispatcher_outbox_scope",
        "csight_failure_capture_insert",
        "csight_reject_operational_history_mutation",
    ):
        assert contract in source
    for raw_field in ("customer_message", "email", "order_ref", "product_ref", "image_url"):
        assert raw_field not in source

    assert {column.name for column in OperationalFailureModel.__table__.columns}.isdisjoint(
        {"payload", "last_error", "failure_message"}
    )
    assert OperationalFailureRecoveryRunModel.__tablename__.endswith("recovery_runs")
    assert OperationalFailureRecoveryEventModel.__tablename__.endswith("recovery_events")
    assert OperationalFailureResolutionModel.__tablename__.endswith("resolutions")
