"""HTTP contracts for the tenant-scoped human-review queue and human actions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.application.human_review import (
    GetHumanReviewTask,
    HumanReviewActions,
    ListHumanReviewTasks,
    ListReviewAssignees,
)
from app.bootstrap.settings import Settings
from app.interface.http.services import Sprint1ServiceContainer, Sprint5BServiceContainer
from app.main import create_app
from app.platform.errors import AuthenticationRequiredError
from app.platform.human_review import (
    HumanDecision,
    HumanDecisionRequest,
    OutcomeRelation,
    ReviewAction,
    ReviewActionType,
    ReviewAssignee,
    ReviewPacket,
    ReviewPriority,
    ReviewTask,
    ReviewTaskAlreadyClaimedError,
    ReviewTaskStatus,
    ReviewTaskType,
)
from app.platform.policy_engine import EvaluationSummary, PolicyEffect, PolicyEffectType
from app.platform.tenant import Principal, Role
from app.ports.human_review import ReviewQueueQuery, ReviewTaskDetail
from tests.case_assignment_support import AllowCaseAccess

pytestmark = pytest.mark.unit
NOW = datetime(2026, 8, 27, tzinfo=UTC)
ASSIGNEE_ID = "00000000-0000-0000-0000-000000000123"


def _principal(role: Role) -> Principal:
    return Principal(
        user_id=f"user-{role.value.lower()}",
        tenant_id="tenant-a",
        email=f"{role.value.lower()}@example.test",
        display_name=role.value,
        roles=frozenset({role}),
    )


class _ResolvePrincipal:
    def execute(self, token: str) -> Principal:
        roles = {
            "admin-token": Role.ADMIN,
            "reviewer-token": Role.REVIEWER,
            "viewer-token": Role.QUALITY_VIEWER,
        }
        if token not in roles:
            raise AuthenticationRequiredError()
        return _principal(roles[token])


def _task(
    status: ReviewTaskStatus = ReviewTaskStatus.PENDING,
    *,
    version: int = 1,
) -> ReviewTask:
    return ReviewTask(
        id="task-1",
        tenant_id="tenant-a",
        case_id="case-1",
        policy_evaluation_run_id="policy-run-1",
        task_type=ReviewTaskType.STANDARD_REVIEW,
        priority=ReviewPriority.NORMAL,
        status=status,
        current_assignee_id=("user-reviewer" if status is ReviewTaskStatus.CLAIMED else None),
        version=version,
        created_at=NOW,
        updated_at=NOW,
    )


def _detail(task: ReviewTask | None = None) -> ReviewTaskDetail:
    selected = task or _task()
    packet = ReviewPacket(
        id="packet-1",
        tenant_id="tenant-a",
        review_task_id=selected.id,
        case_id=selected.case_id,
        analysis_run_id="analysis-1",
        policy_evaluation_run_id=selected.policy_evaluation_run_id,
        rule_set_id="rule-set-1",
        rule_set_version="1.0.0",
        rule_set_hash="a" * 64,
        llm_extraction_result_v2_id="extraction-1",
        completeness_result_id="extraction-1",
        case_metadata_snapshot={"case.has_order_reference": True},
        qualification_snapshot={"vision": {"scope": "MOCK_QUALIFIED"}},
        policy_effects=(PolicyEffect(type=PolicyEffectType.REQUIRE_HUMAN_REVIEW),),
        policy_summary_status=EvaluationSummary.REQUIRES_HUMAN_REVIEW,
        packet_hash="b" * 64,
        created_at=NOW,
    )
    created = ReviewAction(
        id="action-1",
        tenant_id="tenant-a",
        review_task_id=selected.id,
        action_type=ReviewActionType.CREATED,
        from_status=None,
        to_status=ReviewTaskStatus.PENDING,
        actor_id=None,
        actor_role=None,
        expected_task_version=0,
        resulting_task_version=1,
        created_at=NOW,
    )
    return ReviewTaskDetail(
        task=selected,
        packet=packet,
        actions=(created,),
        decision=None,
        rule_results=({"id": "rule-result-1", "status": "MATCHED"},),
        citation_items=(),
        grounded_explanation={"summary": "Advisory only", "advisory": True},
    )


class _Repository:
    def __init__(self) -> None:
        self.query: ReviewQueueQuery | None = None

    def list(
        self, *, tenant_id: str, actor_id: str, query: ReviewQueueQuery
    ) -> tuple[ReviewTask, ...]:
        assert tenant_id == "tenant-a" and actor_id
        self.query = query
        return (_task(),)

    def get(self, *, tenant_id: str, task_id: str) -> ReviewTaskDetail | None:
        return _detail() if tenant_id == "tenant-a" and task_id == "task-1" else None

    def list_assignees(self, *, tenant_id: str) -> tuple[ReviewAssignee, ...]:
        assert tenant_id == "tenant-a"
        return (
            ReviewAssignee(
                user_id=ASSIGNEE_ID,
                display_name="Reviewer",
                email="reviewer@example.test",
                roles=(Role.REVIEWER,),
            ),
        )

    def assign(self, *, assignee_id: str, expected_version: int, **_: object) -> ReviewTask:
        assert assignee_id == ASSIGNEE_ID and expected_version == 1
        return _task(ReviewTaskStatus.CLAIMED, version=2)

    def claim(self, *, expected_version: int, **_: object) -> ReviewTask:
        if expected_version != 1:
            raise ReviewTaskAlreadyClaimedError()
        return _task(ReviewTaskStatus.CLAIMED, version=2)

    def release(self, **_: object) -> ReviewTask:
        return _task(ReviewTaskStatus.PENDING, version=3)

    def request_additional_evidence(self, **_: object) -> ReviewTask:
        return _task(ReviewTaskStatus.WAITING_FOR_EVIDENCE, version=3)

    def resume(self, **_: object) -> ReviewTask:
        return _task(ReviewTaskStatus.PENDING, version=4)

    def escalate(self, **_: object) -> ReviewTask:
        return _task(ReviewTaskStatus.ESCALATED, version=3)

    def resolve(
        self,
        *,
        actor_id: str,
        request: HumanDecisionRequest,
        **_: object,
    ) -> tuple[ReviewTask, HumanDecision]:
        return _task(ReviewTaskStatus.RESOLVED, version=3), HumanDecision(
            id="decision-1",
            tenant_id="tenant-a",
            review_task_id="task-1",
            decision_type=request.decision,
            reason_codes=request.reason_codes,
            rationale=request.rationale,
            basis=request.basis,
            outcome_relation=OutcomeRelation.CONSISTENT_WITH_RECOMMENDATION,
            decided_by=actor_id,
            decided_at=NOW,
            content_hash="c" * 64,
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
    services = Sprint5BServiceContainer(
        list_tasks=ListHumanReviewTasks(repository),  # pyright: ignore[reportArgumentType]
        get_task=GetHumanReviewTask(repository),  # pyright: ignore[reportArgumentType]
        list_assignees=ListReviewAssignees(repository),  # pyright: ignore[reportArgumentType]
        actions=HumanReviewActions(repository),  # pyright: ignore[reportArgumentType]
    )
    return TestClient(
        create_app(
            Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
            sprint1_services=sprint1,
            sprint5b_services=services,
        )
    )


def _headers(role: Role) -> dict[str, str]:
    token = {
        Role.ADMIN: "admin-token",
        Role.REVIEWER: "reviewer-token",
        Role.QUALITY_VIEWER: "viewer-token",
    }[role]
    return {"Authorization": f"Bearer {token}"}


def test_viewer_can_list_detail_and_case_queue_with_stable_filters() -> None:
    repository = _Repository()
    client = _client(repository)
    listing = client.get(
        "/api/v1/human-review-tasks",
        headers=_headers(Role.QUALITY_VIEWER),
        params={
            "status": "PENDING",
            "task_type": "STANDARD_REVIEW",
            "priority": "NORMAL",
            "assigned_to": "me",
            "page": 2,
            "page_size": 10,
        },
    )
    assert listing.status_code == 200
    assert listing.headers["Cache-Control"] == "no-store"
    assert listing.json()["items"][0]["id"] == "task-1"
    assert repository.query is not None
    assert repository.query.assigned_to_me is True and repository.query.page == 2
    detail = client.get("/api/v1/human-review-tasks/task-1", headers=_headers(Role.QUALITY_VIEWER))
    assert detail.status_code == 200
    assert detail.json()["grounded_explanation"]["advisory"] is True
    assert "raw_prompt" not in detail.text.lower()
    case_list = client.get(
        "/api/v1/cases/case-1/human-review-tasks",
        headers=_headers(Role.QUALITY_VIEWER),
    )
    assert case_list.status_code == 200
    assert repository.query is not None and repository.query.case_id == "case-1"


def test_human_action_endpoints_validate_role_version_reasons_and_basis() -> None:
    client = _client(_Repository())
    base = "/api/v1/human-review-tasks/task-1"
    assert (
        client.post(
            f"{base}/claim", headers=_headers(Role.REVIEWER), json={"expected_version": 1}
        ).status_code
        == 200
    )
    conflict = client.post(
        f"{base}/claim", headers=_headers(Role.REVIEWER), json={"expected_version": 2}
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "REVIEW_TASK_ALREADY_CLAIMED"
    assert (
        client.post(
            f"{base}/claim", headers=_headers(Role.QUALITY_VIEWER), json={"expected_version": 1}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{base}/release",
            headers=_headers(Role.REVIEWER),
            json={"expected_version": 2, "reason_code": "SHIFT_END"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{base}/release", headers=_headers(Role.REVIEWER), json={"expected_version": 2}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{base}/request-additional-evidence",
            headers=_headers(Role.REVIEWER),
            json={
                "expected_version": 2,
                "reason_codes": ["DEFECT_AREA_NOT_VISIBLE"],
                "instructions": "결함 부위가 보이도록 다시 촬영해 주세요.",
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{base}/resume",
            headers=_headers(Role.ADMIN),
            json={"expected_version": 3, "rationale": "관리자 확인 후 재개합니다."},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{base}/escalate",
            headers=_headers(Role.REVIEWER),
            json={
                "expected_version": 2,
                "reason_codes": ["POLICY_EXCEPTION"],
                "rationale": "상충 정책이 있어 관리자 검토가 필요합니다.",
            },
        ).status_code
        == 200
    )
    resolved = client.post(
        f"{base}/resolve",
        headers=_headers(Role.REVIEWER),
        json={
            "expected_version": 2,
            "decision": "APPROVE_EXCHANGE",
            "reason_codes": ["POLICY_CONDITION_MET"],
            "rationale": "정책 결과와 고정된 근거를 확인하여 교환을 승인합니다.",
            "basis": [{"type": "POLICY_RULE_RESULT", "reference_id": "rule-result-1"}],
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["decision"]["decided_by"] == "user-reviewer"
    invalid = client.post(
        f"{base}/resolve",
        headers=_headers(Role.REVIEWER),
        json={
            "expected_version": 2,
            "decision": "AUTOMATED_APPROVAL",
            "reason_codes": ["POLICY_CONDITION_MET"],
            "rationale": "자동 결정은 계약에서 허용되면 안 됩니다.",
            "basis": [{"type": "UNKNOWN", "reference_id": "bad"}],
        },
    )
    assert invalid.status_code == 422


def test_only_admin_can_list_assignees_and_assign_with_audit_rationale() -> None:
    client = _client(_Repository())
    assignees = client.get("/api/v1/human-review-assignees", headers=_headers(Role.ADMIN))
    assert assignees.status_code == 200
    assert assignees.json()["items"][0]["display_name"] == "Reviewer"
    assert (
        client.get("/api/v1/human-review-assignees", headers=_headers(Role.REVIEWER)).status_code
        == 403
    )

    assigned = client.post(
        "/api/v1/human-review-tasks/task-1/assign",
        headers=_headers(Role.ADMIN),
        json={
            "expected_version": 1,
            "assignee_id": ASSIGNEE_ID,
            "rationale": "관리자가 문의 담당자를 배정했습니다.",
        },
    )
    assert assigned.status_code == 200
    assert assigned.json()["task"]["status"] == "CLAIMED"
    assert (
        client.post(
            "/api/v1/human-review-tasks/task-1/assign",
            headers=_headers(Role.REVIEWER),
            json={
                "expected_version": 1,
                "assignee_id": ASSIGNEE_ID,
                "rationale": "담당자가 임의로 배정하려고 했습니다.",
            },
        ).status_code
        == 403
    )
