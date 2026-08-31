"""Technology-neutral Case ownership and assignment contracts."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.errors import CSightError


class CaseAssignmentType(StrEnum):
    ADMIN_ASSIGNMENT = "ADMIN_ASSIGNMENT"
    ADMIN_REASSIGNMENT = "ADMIN_REASSIGNMENT"
    REVIEW_TASK_BACKFILL = "REVIEW_TASK_BACKFILL"


class CaseAssignmentActionType(StrEnum):
    ASSIGNED = "ASSIGNED"
    REASSIGNED = "REASSIGNED"
    BACKFILLED = "BACKFILLED"


class CaseAssignmentVersionConflictError(CSightError):
    code = "CASE_ASSIGNMENT_VERSION_CONFLICT"
    default_message = "The Case assignment version is stale."


class CaseAssignmentTargetNotEligibleError(CSightError):
    code = "CASE_ASSIGNMENT_TARGET_NOT_ELIGIBLE"
    default_message = "The selected user is not eligible to own this Case."


class CaseAssignmentTerminalError(CSightError):
    code = "CASE_ASSIGNMENT_TERMINAL"
    default_message = "A resolved Case cannot be reassigned."


class CaseAssignmentSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    case_id: str = Field(min_length=1)
    current_assignee_id: str | None = None
    version: int = Field(ge=0)
    assigned_by: str | None = None
    assignment_type: CaseAssignmentType | None = None
    rationale: str | None = None
    assigned_at: datetime | None = None

    @field_validator("assigned_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("assigned_at must be timezone-aware")
        return value.astimezone(UTC)


__all__ = [
    "CaseAssignmentActionType",
    "CaseAssignmentSnapshot",
    "CaseAssignmentTargetNotEligibleError",
    "CaseAssignmentTerminalError",
    "CaseAssignmentType",
    "CaseAssignmentVersionConflictError",
]
