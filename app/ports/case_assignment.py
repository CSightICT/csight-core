"""Persistence boundary for intake-level Case ownership."""

from typing import Protocol, runtime_checkable

from app.platform.case_assignment import CaseAssignmentSnapshot


@runtime_checkable
class CaseAssignmentRepository(Protocol):
    def get(self, *, tenant_id: str, case_id: str) -> CaseAssignmentSnapshot | None: ...

    def assign(
        self,
        *,
        tenant_id: str,
        case_id: str,
        assignee_id: str,
        assigned_by: str,
        expected_version: int,
        rationale: str,
    ) -> CaseAssignmentSnapshot: ...

    def can_access(
        self,
        *,
        tenant_id: str,
        case_id: str,
        actor_id: str,
    ) -> bool: ...

    def exists(self, *, tenant_id: str, case_id: str) -> bool: ...


__all__ = ["CaseAssignmentRepository"]
