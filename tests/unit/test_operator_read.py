"""Application and HTTP contracts for server-side operator reads."""

from __future__ import annotations

from datetime import UTC, datetime
from inspect import getsource
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.adapters.persistence.operator_read import SQLAlchemyOperatorReadRepository
from app.application.operator_read import (
    GetWorkflowSnapshot,
    ListOperatorCases,
    ListOperatorReviews,
)
from app.bootstrap.settings import Settings
from app.interface.http.operator_read_services import OperatorReadServiceContainer
from app.interface.http.services import Sprint1ServiceContainer
from app.main import create_app
from app.platform.errors import AuthenticationRequiredError, ValidationError
from app.platform.operator_read import (
    OperatorCaseItem,
    OperatorReviewItem,
    QueueCounts,
    QueueSort,
    QueueView,
    WorkflowComponent,
    WorkflowSnapshot,
    WorkflowStage,
)
from app.platform.tenant import Principal, Role
from app.ports.operator_read import CaseQueueSlice, ReviewQueueSlice
from tests.case_assignment_support import AllowCaseAccess

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)
TENANT_ID = str(uuid4())
OTHER_TENANT_ID = str(uuid4())
USER_ID = str(uuid4())
CASE_ID = str(uuid4())
TASK_ID = str(uuid4())
COUNTS = QueueCounts(all=4, my=1, unassigned=2, urgent=1, waiting_evidence=0, complete=1)


class _ResolvePrincipal:
    def execute(self, token: str) -> Principal:
        if token not in {"reviewer-token", "other-token"}:
            raise AuthenticationRequiredError()
        return Principal(
            user_id=USER_ID,
            tenant_id=OTHER_TENANT_ID if token == "other-token" else TENANT_ID,
            email="reviewer@example.test",
            display_name="Reviewer",
            roles=frozenset({Role.REVIEWER}),
        )


class _Repository:
    def __init__(self) -> None:
        self.case_calls: list[dict[str, object]] = []
        self.review_calls: list[dict[str, object]] = []
        self.snapshot_tenants: list[str] = []

    def list_cases(self, **values: object) -> CaseQueueSlice:
        self.case_calls.append(values)
        item = OperatorCaseItem(
            case_id=CASE_ID,
            case_status="UNDER_REVIEW",
            order_ref="ORDER-1",
            product_ref="PRODUCT-1",
            requested_action="REFUND",
            inquiry_preview="포장 파손으로 교환을 요청합니다.",
            created_at=NOW,
            updated_at=NOW,
            review_task_id=TASK_ID,
            review_status="CLAIMED",
            review_priority="HIGH",
            assignee_id=USER_ID,
            assignment_version=1,
        )
        return CaseQueueSlice(items=(item,), counts=COUNTS, has_more=True)

    def list_reviews(self, **values: object) -> ReviewQueueSlice:
        self.review_calls.append(values)
        item = OperatorReviewItem(
            review_task_id=TASK_ID,
            case_id=CASE_ID,
            case_status="UNDER_REVIEW",
            order_ref="ORDER-1",
            product_ref="PRODUCT-1",
            requested_action="REFUND",
            inquiry_preview="포장 파손으로 교환을 요청합니다.",
            task_type="STANDARD_REVIEW",
            priority="HIGH",
            status="CLAIMED",
            assignee_id=USER_ID,
            version=2,
            created_at=NOW,
            updated_at=NOW,
        )
        return ReviewQueueSlice(items=(item,), counts=COUNTS, has_more=False)

    def get_workflow_snapshot(self, *, tenant_id: str, case_id: str) -> WorkflowSnapshot | None:
        self.snapshot_tenants.append(tenant_id)
        if tenant_id != TENANT_ID or case_id != CASE_ID:
            return None
        return WorkflowSnapshot(
            case_id=case_id,
            case_status="UNDER_REVIEW",
            terminal=False,
            degraded=True,
            retry_at=NOW,
            last_good="ANALYSIS",
            correlation_id="corr-1",
            analysis=WorkflowComponent(
                run_id=str(uuid4()),
                status="PARTIAL_SUCCESS",
                started_at=NOW,
                completed_at=NOW,
                correlation_id="corr-1",
            ),
            stages=(
                WorkflowStage(
                    stage_type="TEXT_EXTRACTION",
                    status="RETRY_WAITING",
                    attempt_count=2,
                    next_attempt_at=NOW,
                ),
            ),
            policy_retrieval=None,
            grounded_explanation=None,
            policy_evaluation=None,
            review=None,
            resolution=None,
            report=None,
        )


def _services(repository: _Repository) -> OperatorReadServiceContainer:
    return OperatorReadServiceContainer(
        list_cases=ListOperatorCases(repository),  # pyright: ignore[reportArgumentType]
        list_reviews=ListOperatorReviews(repository),  # pyright: ignore[reportArgumentType]
        get_workflow_snapshot=GetWorkflowSnapshot(repository),  # pyright: ignore[reportArgumentType]
    )


def _principal() -> Principal:
    return Principal(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        email="reviewer@example.test",
        display_name="Reviewer",
        roles=frozenset({Role.REVIEWER}),
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
        get_case_assignment=unused,
        assign_case=unused,
        authorize_case_access=AllowCaseAccess(),  # pyright: ignore[reportArgumentType]
    )
    return TestClient(
        create_app(
            Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
            sprint1_services=sprint1,
            operator_read_services=_services(repository),
        )
    )


def test_case_cursor_is_opaque_keyset_and_bound_to_view_and_sort() -> None:
    repository = _Repository()
    use_case = ListOperatorCases(repository)  # pyright: ignore[reportArgumentType]
    first = use_case.execute(
        principal=_principal(),
        view=QueueView.MY,
        sort=QueueSort.NEWEST,
        query=None,
        limit=1,
        cursor=None,
    )
    assert first.next_cursor is not None
    assert CASE_ID not in first.next_cursor

    use_case.execute(
        principal=_principal(),
        view=QueueView.MY,
        sort=QueueSort.NEWEST,
        query=None,
        limit=1,
        cursor=first.next_cursor,
    )
    assert repository.case_calls[-1]["after_created_at"] == NOW
    assert repository.case_calls[-1]["after_id"] == CASE_ID

    with pytest.raises(ValidationError):
        use_case.execute(
            principal=_principal(),
            view=QueueView.URGENT,
            sort=QueueSort.NEWEST,
            query=None,
            limit=1,
            cursor=first.next_cursor,
        )


def test_case_queue_moves_to_complete_on_human_decision_before_report_generation() -> None:
    source = getsource(SQLAlchemyOperatorReadRepository.list_cases)

    assert "(hd.id IS NULL" in source
    assert "AND c.current_assignee_id = CAST(:actor_id AS uuid)) AS is_my" in source
    assert "(hd.id IS NOT NULL AND (" in source
    assert "rr.id IS NULL\n                           AND c.current_assignee_id" not in source


def test_queue_search_is_normalized_and_cursor_is_bound_to_search() -> None:
    repository = _Repository()
    use_case = ListOperatorCases(repository)  # pyright: ignore[reportArgumentType]

    first = use_case.execute(
        principal=_principal(),
        view=QueueView.MY,
        sort=QueueSort.NEWEST,
        query="  ORDER-1   ",
        limit=1,
        cursor=None,
    )

    assert repository.case_calls[-1]["query"] == "ORDER-1"
    assert first.next_cursor is not None
    with pytest.raises(ValidationError):
        use_case.execute(
            principal=_principal(),
            view=QueueView.MY,
            sort=QueueSort.NEWEST,
            query="PRODUCT-1",
            limit=1,
            cursor=first.next_cursor,
        )


def test_operator_routes_are_tenant_scoped_no_store_and_return_counts() -> None:
    repository = _Repository()
    client = _client(repository)
    headers = {"Authorization": "Bearer reviewer-token"}

    cases = client.get(
        "/api/v1/operator/cases?view=my&sort=newest&limit=1&q=ORDER-1", headers=headers
    )
    reviews = client.get("/api/v1/operator/reviews?view=urgent&q=PRODUCT-1", headers=headers)
    snapshot = client.get(f"/api/v1/cases/{CASE_ID}/workflow-snapshot", headers=headers)

    assert cases.status_code == 200
    assert cases.headers["Cache-Control"] == "no-store"
    assert cases.json()["counts"] == COUNTS.model_dump()
    assert cases.json()["items"][0]["review_status"] == "CLAIMED"
    assert cases.json()["items"][0]["inquiry_preview"] == "포장 파손으로 교환을 요청합니다."
    assert reviews.status_code == 200
    assert reviews.json()["items"][0]["inquiry_preview"] == "포장 파손으로 교환을 요청합니다."
    assert reviews.json()["items"][0]["priority"] == "HIGH"
    assert snapshot.status_code == 200
    assert snapshot.headers["Pragma"] == "no-cache"
    assert snapshot.json()["degraded"] is True
    assert snapshot.json()["last_good"] == "ANALYSIS"
    assert repository.case_calls[0]["tenant_id"] == TENANT_ID
    assert repository.review_calls[0]["actor_id"] == USER_ID
    assert repository.case_calls[0]["can_view_all"] is False
    assert repository.review_calls[0]["can_view_all"] is False
    assert repository.case_calls[0]["query"] == "ORDER-1"
    assert repository.review_calls[0]["query"] == "PRODUCT-1"
    assert repository.snapshot_tenants == [TENANT_ID]


def test_operator_routes_reject_bad_cursor_hide_other_tenant_and_require_auth() -> None:
    repository = _Repository()
    client = _client(repository)
    headers = {"Authorization": "Bearer reviewer-token"}

    bad_cursor = client.get("/api/v1/operator/cases?cursor=not-base64", headers=headers)
    hidden = client.get(
        f"/api/v1/cases/{CASE_ID}/workflow-snapshot",
        headers={"Authorization": "Bearer other-token"},
    )
    malformed = client.get("/api/v1/cases/not-a-uuid/workflow-snapshot", headers=headers)

    assert bad_cursor.status_code == 422
    assert bad_cursor.json()["error"]["code"] == "VALIDATION_ERROR"
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "CASE_NOT_FOUND"
    assert malformed.status_code == 422
    assert client.get("/api/v1/operator/reviews").status_code == 401
