"""HTTP contracts for administrator-managed intake assignment."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.platform.case_assignment import CaseAssignmentSnapshot, CaseAssignmentType


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AssignCaseRequest(_Schema):
    assignee_id: str = Field(min_length=1)
    expected_version: int = Field(ge=0)
    rationale: str = Field(min_length=5, max_length=500)


class CaseAssignmentResponse(_Schema):
    case_id: str
    current_assignee_id: str | None
    version: int
    assigned_by: str | None
    assignment_type: CaseAssignmentType | None
    rationale: str | None
    assigned_at: datetime | None

    @classmethod
    def from_snapshot(cls, snapshot: CaseAssignmentSnapshot) -> "CaseAssignmentResponse":
        return cls.model_validate(snapshot.model_dump(mode="python"))


__all__ = ["AssignCaseRequest", "CaseAssignmentResponse"]
