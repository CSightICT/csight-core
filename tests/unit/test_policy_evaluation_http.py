"""HTTP contracts for append-only deterministic policy evaluation runs."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.application.policy_engine import (
    StartPolicyEvaluationCommand,
    StartPolicyEvaluationResult,
)
from app.bootstrap.settings import Settings
from app.interface.http.services import Sprint1ServiceContainer, Sprint5AServiceContainer
from app.main import create_app
from app.platform.errors import AuthenticationRequiredError, IdempotencyKeyReusedError
from app.platform.policy_engine import (
    EvaluationSummary,
    PolicyEvaluationRun,
    PolicyEvaluationRunStatus,
)
from app.platform.tenant import Permission, Principal, Role
from app.ports.policy_engine import PolicyEvaluationRunDetail

pytestmark = pytest.mark.unit
NOW = datetime(2026, 8, 27, tzinfo=UTC)


def _principal(role: Role, *, tenant_id: str = "tenant-a") -> Principal:
    return Principal(
        user_id=f"user-{role.value.lower()}",
        tenant_id=tenant_id,
        email=f"{role.value.lower()}@example.test",
        display_name=role.value,
        roles=frozenset({role}),
    )


def _run(
    *, status: PolicyEvaluationRunStatus = PolicyEvaluationRunStatus.QUEUED
) -> PolicyEvaluationRun:
    succeeded = status is PolicyEvaluationRunStatus.SUCCEEDED
    return PolicyEvaluationRun(
        id="policy-run-1",
        tenant_id="tenant-a",
        case_id="case-1",
        analysis_run_id="analysis-1",
        rule_set_id="rule-set-1",
        rule_set_name="product_defect_policy",
        rule_set_version="1.0.0",
        rule_set_hash="a" * 64,
        as_of_date=date(2026, 2, 1),
        status=status,
        summary_status=EvaluationSummary.REQUIRES_HUMAN_REVIEW if succeeded else None,
        correlation_id="corr-policy",
        created_at=NOW,
        started_at=NOW if succeeded else None,
        completed_at=NOW if succeeded else None,
    )


class _ResolvePrincipal:
    def execute(self, token: str) -> Principal:
        values = {
            "admin-token": _principal(Role.ADMIN),
            "reviewer-token": _principal(Role.REVIEWER),
            "viewer-token": _principal(Role.QUALITY_VIEWER),
        }
        if token not in values:
            raise AuthenticationRequiredError()
        return values[token]


@dataclass(slots=True)
class _Start:
    command: StartPolicyEvaluationCommand | None = None

    def execute(
        self, *, principal: Principal, case_id: str, command: StartPolicyEvaluationCommand
    ) -> StartPolicyEvaluationResult:
        principal.require(Permission.ANALYSIS_CREATE)
        self.command = command
        if command.idempotency_key == "conflict":
            raise IdempotencyKeyReusedError()
        return StartPolicyEvaluationResult(run=_run(), replayed=command.idempotency_key == "replay")


class _List:
    def execute(self, *, principal: Principal, case_id: str) -> tuple[PolicyEvaluationRun, ...]:
        principal.require(Permission.POLICY_READ)
        return (_run(status=PolicyEvaluationRunStatus.SUCCEEDED),)


class _Get:
    def execute(
        self, *, principal: Principal, case_id: str, run_id: str
    ) -> PolicyEvaluationRunDetail:
        principal.require(Permission.POLICY_READ)
        return PolicyEvaluationRunDetail(
            run=_run(status=PolicyEvaluationRunStatus.SUCCEEDED),
            input_qualification={
                "llm": "LOCAL_POC",
                "vision": "MOCK_QUALIFIED",
                "alignment": "NOT_AVAILABLE",
            },
        )


def _client(start: _Start) -> TestClient:
    unused: Any = object()
    sprint1 = Sprint1ServiceContainer(
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
    )
    sprint5a = Sprint5AServiceContainer(
        start_policy_evaluation=start,  # pyright: ignore[reportArgumentType]
        list_policy_evaluations=_List(),  # pyright: ignore[reportArgumentType]
        get_policy_evaluation=_Get(),  # pyright: ignore[reportArgumentType]
    )
    return TestClient(
        create_app(
            Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
            sprint1_services=sprint1,
            sprint5a_services=sprint5a,
        )
    )


def _headers(role: Role, key: str = "new") -> dict[str, str]:
    token = {
        Role.ADMIN: "admin-token",
        Role.REVIEWER: "reviewer-token",
        Role.QUALITY_VIEWER: "viewer-token",
    }[role]
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


@pytest.mark.parametrize("role", [Role.ADMIN, Role.REVIEWER])
def test_create_is_202_and_core_owned_fields_are_not_accepted(role: Role) -> None:
    start = _Start()
    client = _client(start)
    response = client.post(
        "/api/v1/cases/case-1/policy-evaluation-runs",
        headers=_headers(role),
        json={"analysis_run_id": "analysis-1", "as_of_date": "2026-02-01"},
    )
    assert response.status_code == 202
    assert response.json() == {
        "policy_evaluation_run_id": "policy-run-1",
        "status": "QUEUED",
        "location": "/api/v1/cases/case-1/policy-evaluation-runs/policy-run-1",
    }
    assert response.headers["Location"] == response.json()["location"]
    assert start.command is not None and start.command.analysis_run_id == "analysis-1"

    invalid = client.post(
        "/api/v1/cases/case-1/policy-evaluation-runs",
        headers=_headers(role, "invalid"),
        json={
            "analysis_run_id": "analysis-1",
            "as_of_date": "2026-02-01",
            "tenant_id": "other",
            "rule_set_version": "9.9.9",
        },
    )
    assert invalid.status_code == 422


def test_replay_conflict_roles_list_and_detail_contracts() -> None:
    client = _client(_Start())
    path = "/api/v1/cases/case-1/policy-evaluation-runs"
    body = {"analysis_run_id": "analysis-1", "as_of_date": "2026-02-01"}
    assert (
        client.post(path, headers=_headers(Role.REVIEWER, "replay"), json=body).status_code == 200
    )
    conflict = client.post(path, headers=_headers(Role.REVIEWER, "conflict"), json=body)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert client.post(path, headers=_headers(Role.QUALITY_VIEWER), json=body).status_code == 403

    listing = client.get(path, headers=_headers(Role.QUALITY_VIEWER))
    assert listing.status_code == 200
    assert listing.json()["items"][0]["rule_set"]["version"] == "1.0.0"
    detail = client.get(f"{path}/policy-run-1", headers=_headers(Role.QUALITY_VIEWER))
    assert detail.status_code == 200
    assert detail.json()["input_qualification"] == {
        "llm": "LOCAL_POC",
        "vision": "MOCK_QUALIFIED",
        "alignment": "NOT_AVAILABLE",
    }
    assert "tenant_id" not in detail.text
    assert "APPROVED" not in detail.text
