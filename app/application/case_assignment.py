"""Authenticated intake-level assignment and Case ownership checks."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.case_assignment import CaseAssignmentSnapshot
from app.platform.errors import CaseNotFoundError, ForbiddenError
from app.platform.tenant import Principal, Role
from app.ports.case_assignment import CaseAssignmentRepository


class AssignCaseCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    assignee_id: str = Field(min_length=1)
    expected_version: int = Field(ge=0)
    rationale: str = Field(min_length=5, max_length=500)

    @field_validator("assignee_id")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        from uuid import UUID

        try:
            return str(UUID(value))
        except ValueError as error:
            raise ValueError("assignee_id must be a UUID") from error


class GetCaseAssignment:
    def __init__(self, repository: CaseAssignmentRepository) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, case_id: str) -> CaseAssignmentSnapshot:
        if not self._can_view_all(principal):
            self._require_personal_access(principal=principal, case_id=case_id)
        result = self._repository.get(tenant_id=principal.tenant_id, case_id=case_id)
        if result is None:
            raise CaseNotFoundError()
        return result

    @staticmethod
    def _can_view_all(principal: Principal) -> bool:
        return bool(principal.roles & {Role.ADMIN, Role.QUALITY_VIEWER})

    def _require_personal_access(self, *, principal: Principal, case_id: str) -> None:
        if not self._repository.can_access(
            tenant_id=principal.tenant_id,
            case_id=case_id,
            actor_id=principal.user_id,
        ):
            raise CaseNotFoundError()


class AssignCase:
    def __init__(self, repository: CaseAssignmentRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        principal: Principal,
        case_id: str,
        command: AssignCaseCommand,
    ) -> CaseAssignmentSnapshot:
        if Role.ADMIN not in principal.roles:
            raise ForbiddenError()
        return self._repository.assign(
            tenant_id=principal.tenant_id,
            case_id=case_id,
            assignee_id=command.assignee_id,
            assigned_by=principal.user_id,
            expected_version=command.expected_version,
            rationale=command.rationale,
        )


class AuthorizeCaseAccess:
    """Return 404 for an existing Case outside a reviewer's ownership."""

    def __init__(self, repository: CaseAssignmentRepository) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, case_id: str) -> None:
        if principal.roles & {Role.ADMIN, Role.QUALITY_VIEWER}:
            allowed = self._repository.exists(tenant_id=principal.tenant_id, case_id=case_id)
        else:
            allowed = self._repository.can_access(
                tenant_id=principal.tenant_id,
                case_id=case_id,
                actor_id=principal.user_id,
            )
        if not allowed:
            raise CaseNotFoundError()


__all__ = [
    "AssignCase",
    "AssignCaseCommand",
    "AuthorizeCaseAccess",
    "GetCaseAssignment",
]
