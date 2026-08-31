"""Application rules for intake-level Case ownership."""

from datetime import UTC, datetime

import pytest

from app.application.case_assignment import (
    AssignCase,
    AssignCaseCommand,
    AuthorizeCaseAccess,
    GetCaseAssignment,
)
from app.platform.case_assignment import CaseAssignmentSnapshot, CaseAssignmentType
from app.platform.errors import CaseNotFoundError, ForbiddenError
from app.platform.tenant import Principal, Role

pytestmark = pytest.mark.unit


class _Repository:
    def __init__(self) -> None:
        self.owner_id = "reviewer-a"
        self.case_exists = True
        self.assign_calls = 0

    def get(self, *, tenant_id: str, case_id: str) -> CaseAssignmentSnapshot | None:
        if not self.case_exists:
            return None
        return CaseAssignmentSnapshot(
            case_id=case_id,
            current_assignee_id=self.owner_id,
            version=1,
            assigned_by="admin-a",
            assignment_type=CaseAssignmentType.ADMIN_ASSIGNMENT,
            rationale="업무 담당자 배정",
            assigned_at=datetime(2026, 8, 30, tzinfo=UTC),
        )

    def assign(self, **values: object) -> CaseAssignmentSnapshot:
        self.assign_calls += 1
        self.owner_id = str(values["assignee_id"])
        return self.get(
            tenant_id=str(values["tenant_id"]),
            case_id=str(values["case_id"]),
        )  # type: ignore[return-value]

    def can_access(self, *, tenant_id: str, case_id: str, actor_id: str) -> bool:
        return self.case_exists and actor_id == self.owner_id

    def exists(self, *, tenant_id: str, case_id: str) -> bool:
        return self.case_exists


def _principal(role: Role, *, user_id: str) -> Principal:
    return Principal(
        user_id=user_id,
        tenant_id="tenant-a",
        email=f"{user_id}@example.test",
        display_name=user_id,
        roles=frozenset({role}),
    )


def test_only_admin_can_assign_case() -> None:
    repository = _Repository()
    command = AssignCaseCommand(
        assignee_id="c0ffee00-0000-4000-8000-000000000001",
        expected_version=1,
        rationale="관리자가 새 담당자로 변경합니다",
    )

    result = AssignCase(repository).execute(
        principal=_principal(Role.ADMIN, user_id="admin-a"),
        case_id="case-a",
        command=command,
    )

    assert result.current_assignee_id == command.assignee_id
    assert repository.assign_calls == 1
    with pytest.raises(ForbiddenError):
        AssignCase(repository).execute(
            principal=_principal(Role.REVIEWER, user_id="reviewer-a"),
            case_id="case-a",
            command=command,
        )
    assert repository.assign_calls == 1


def test_reviewer_sees_only_owned_case_but_admin_and_quality_can_view_existing_case() -> None:
    repository = _Repository()

    own = _principal(Role.REVIEWER, user_id="reviewer-a")
    other = _principal(Role.REVIEWER, user_id="reviewer-b")
    GetCaseAssignment(repository).execute(principal=own, case_id="case-a")
    AuthorizeCaseAccess(repository).execute(principal=own, case_id="case-a")

    with pytest.raises(CaseNotFoundError):
        GetCaseAssignment(repository).execute(principal=other, case_id="case-a")
    with pytest.raises(CaseNotFoundError):
        AuthorizeCaseAccess(repository).execute(principal=other, case_id="case-a")

    for role in (Role.ADMIN, Role.QUALITY_VIEWER):
        principal = _principal(role, user_id=role.value.lower())
        GetCaseAssignment(repository).execute(principal=principal, case_id="case-a")
        AuthorizeCaseAccess(repository).execute(principal=principal, case_id="case-a")


def test_privileged_access_still_returns_not_found_for_unknown_case() -> None:
    repository = _Repository()
    repository.case_exists = False
    admin = _principal(Role.ADMIN, user_id="admin-a")

    with pytest.raises(CaseNotFoundError):
        AuthorizeCaseAccess(repository).execute(principal=admin, case_id="missing")
