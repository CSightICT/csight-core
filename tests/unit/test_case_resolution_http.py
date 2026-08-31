"""Read-only tenant-scoped Sprint 5C HTTP contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.application.case_resolution import (
    GetCaseResolution,
    GetExternalActionIntent,
    ListCaseExternalActionIntents,
    ListCaseResolutionEvents,
)
from app.bootstrap.settings import Settings
from app.interface.http.services import Sprint1ServiceContainer, Sprint5CServiceContainer
from app.main import create_app
from app.platform.case_resolution import (
    CaseResolution,
    CaseResolutionEvent,
    ExternalActionIntent,
    ExternalActionIntentDetail,
    ExternalActionType,
    ResolutionEventType,
    ResolutionStatus,
)
from app.platform.errors import AuthenticationRequiredError
from app.platform.tenant import Principal, Role
from tests.case_assignment_support import AllowCaseAccess

pytestmark = pytest.mark.unit
NOW = datetime(2026, 8, 27, tzinfo=UTC)
TENANT_ID = str(uuid4())
CASE_ID = str(uuid4())
RESOLUTION_ID = str(uuid4())
TASK_ID = str(uuid4())
DECISION_ID = str(uuid4())
INTENT_ID = str(uuid4())


class _ResolvePrincipal:
    def execute(self, token: str) -> Principal:
        if token != "viewer-token":
            raise AuthenticationRequiredError()
        return Principal(
            user_id=str(uuid4()),
            tenant_id=TENANT_ID,
            email="viewer@example.test",
            display_name="Viewer",
            roles=frozenset({Role.QUALITY_VIEWER}),
        )


class _Repository:
    def __init__(self) -> None:
        self.resolution = CaseResolution(
            id=RESOLUTION_ID,
            tenant_id=TENANT_ID,
            case_id=CASE_ID,
            source_review_task_id=TASK_ID,
            source_human_decision_id=DECISION_ID,
            status=ResolutionStatus.ACTION_READY,
            version=2,
            correlation_id="corr-1",
            created_at=NOW,
            updated_at=NOW,
        )
        self.intent = ExternalActionIntent(
            id=INTENT_ID,
            tenant_id=TENANT_ID,
            case_id=CASE_ID,
            resolution_id=RESOLUTION_ID,
            human_decision_id=DECISION_ID,
            action_type=ExternalActionType.REPAIR,
            order_ref="order-1",
            product_ref="product-1",
            quantity=1,
            content_hash="a" * 64,
            created_at=NOW,
        )

    def get_resolution(self, *, tenant_id: str, case_id: str) -> CaseResolution | None:
        return self.resolution if tenant_id == TENANT_ID and case_id == CASE_ID else None

    def list_events(self, *, tenant_id: str, case_id: str) -> tuple[CaseResolutionEvent, ...]:
        if tenant_id != TENANT_ID or case_id != CASE_ID:
            return ()
        return (
            CaseResolutionEvent(
                id=str(uuid4()),
                tenant_id=TENANT_ID,
                case_id=CASE_ID,
                resolution_id=RESOLUTION_ID,
                sequence=1,
                event_type=ResolutionEventType.DECISION_RECORDED,
                from_status=None,
                to_status=ResolutionStatus.DECISION_RECORDED,
                human_decision_id=DECISION_ID,
                created_at=NOW,
            ),
        )

    def list_intents(self, *, tenant_id: str, case_id: str) -> tuple[ExternalActionIntent, ...]:
        return (self.intent,) if tenant_id == TENANT_ID and case_id == CASE_ID else ()

    def get_intent(self, *, tenant_id: str, intent_id: str) -> ExternalActionIntentDetail | None:
        if tenant_id != TENANT_ID or intent_id != INTENT_ID:
            return None
        return ExternalActionIntentDetail(intent=self.intent)


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
        get_case_assignment=unused,
        assign_case=unused,
        authorize_case_access=AllowCaseAccess(),  # pyright: ignore[reportArgumentType]
    )
    sprint5c = Sprint5CServiceContainer(
        get_resolution=GetCaseResolution(repository),
        list_resolution_events=ListCaseResolutionEvents(repository),
        list_external_action_intents=ListCaseExternalActionIntents(repository),
        get_external_action_intent=GetExternalActionIntent(repository),
    )
    return TestClient(
        create_app(
            Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
            sprint1_services=sprint1,
            sprint5c_services=sprint5c,
        )
    )


def test_all_four_read_only_routes_are_tenant_scoped_and_no_store() -> None:
    client = _client(_Repository())
    headers = {"Authorization": "Bearer viewer-token"}
    paths = (
        f"/api/v1/cases/{CASE_ID}/resolution",
        f"/api/v1/cases/{CASE_ID}/resolution/events",
        f"/api/v1/cases/{CASE_ID}/external-action-intents",
        f"/api/v1/external-action-intents/{INTENT_ID}",
    )
    responses = tuple(client.get(path, headers=headers) for path in paths)
    assert [item.status_code for item in responses] == [200, 200, 200, 200]
    assert all(item.headers["Cache-Control"] == "no-store" for item in responses)
    assert responses[0].json()["status"] == "ACTION_READY"
    assert responses[2].json()["items"][0]["mode"] == "DRY_RUN"
    assert responses[3].json()["results"] == []
    assert all("tenant_id" not in item.text for item in responses)
    assert all("execution_token" not in item.text for item in responses)

    missing = client.get(
        f"/api/v1/cases/{uuid4()}/resolution",
        headers=headers,
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CASE_RESOLUTION_NOT_FOUND"
    assert client.post(paths[0], headers=headers).status_code == 405


def test_case_resolution_routes_require_authentication_and_uuid_paths() -> None:
    client = _client(_Repository())
    assert client.get(f"/api/v1/cases/{CASE_ID}/resolution").status_code == 401
    malformed = client.get(
        "/api/v1/cases/not-a-uuid/resolution",
        headers={"Authorization": "Bearer viewer-token"},
    )
    assert malformed.status_code == 422
    assert UUID(CASE_ID)
