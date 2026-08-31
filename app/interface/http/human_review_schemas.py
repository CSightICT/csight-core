"""Strict HTTP schemas for human review tasks and final decisions."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.platform.human_review import (
    AdditionalEvidenceReason,
    DecisionBasisReference,
    DecisionReason,
    EscalationReason,
    HumanDecision,
    HumanDecisionRequest,
    HumanDecisionType,
    ReviewAction,
    ReviewAssignee,
    ReviewPacket,
    ReviewPriority,
    ReviewTask,
    ReviewTaskStatus,
    ReviewTaskType,
)
from app.ports.human_review import ReviewTaskDetail


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VersionRequest(_Schema):
    expected_version: int = Field(ge=1)


class AssignRequest(VersionRequest):
    assignee_id: str = Field(min_length=1)
    rationale: str = Field(min_length=5, max_length=500)


class ReleaseRequest(VersionRequest):
    reason_code: str | None = Field(default=None, min_length=1, max_length=128)
    rationale: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_reason(self) -> ReleaseRequest:
        if not (self.reason_code or (self.rationale or "").strip()):
            raise ValueError("release requires a reason code or rationale")
        return self


class EvidenceRequest(VersionRequest):
    reason_codes: tuple[AdditionalEvidenceReason, ...] = Field(min_length=1, max_length=10)
    instructions: str = Field(min_length=1, max_length=2000)
    rationale: str | None = Field(default=None, max_length=2000)


class ResumeRequest(VersionRequest):
    rationale: str | None = Field(default=None, max_length=2000)


class EscalateRequest(VersionRequest):
    reason_codes: tuple[EscalationReason, ...] = Field(min_length=1, max_length=10)
    rationale: str = Field(min_length=1, max_length=2000)


class ResolveRequest(VersionRequest):
    decision: HumanDecisionType
    reason_codes: tuple[DecisionReason, ...] = Field(min_length=1, max_length=10)
    rationale: str = Field(min_length=10, max_length=2000)
    basis: tuple[DecisionBasisReference, ...] = Field(min_length=1, max_length=30)

    def to_domain(self) -> HumanDecisionRequest:
        return HumanDecisionRequest(
            decision=self.decision,
            reason_codes=self.reason_codes,
            rationale=self.rationale,
            basis=self.basis,
        )


class ReviewTaskResponse(_Schema):
    id: str
    case_id: str
    policy_evaluation_run_id: str
    task_type: ReviewTaskType
    priority: ReviewPriority
    status: ReviewTaskStatus
    current_assignee_id: str | None
    version: int
    mapping_rule_name: str
    mapping_rule_version: str
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None

    @classmethod
    def from_task(cls, task: ReviewTask) -> ReviewTaskResponse:
        return cls(**task.model_dump(exclude={"tenant_id"}))


class ReviewTaskListResponse(_Schema):
    items: tuple[ReviewTaskResponse, ...]


class ReviewAssigneeResponse(_Schema):
    user_id: str
    display_name: str
    email: str
    roles: tuple[str, ...]

    @classmethod
    def from_assignee(cls, assignee: ReviewAssignee) -> ReviewAssigneeResponse:
        return cls.model_validate(assignee.model_dump(mode="python"))


class ReviewAssigneeListResponse(_Schema):
    items: tuple[ReviewAssigneeResponse, ...]


class ReviewTaskDetailResponse(_Schema):
    task: ReviewTaskResponse
    packet: ReviewPacket
    actions: tuple[ReviewAction, ...]
    decision: HumanDecision | None
    rule_results: tuple[dict[str, object], ...]
    citation_items: tuple[dict[str, object], ...]
    grounded_explanation: dict[str, object] | None
    inquiry_summary: str | None
    policy_similarity: tuple[dict[str, object], ...]

    @classmethod
    def from_detail(cls, detail: ReviewTaskDetail) -> ReviewTaskDetailResponse:
        return cls(
            task=ReviewTaskResponse.from_task(detail.task),
            packet=detail.packet,
            actions=detail.actions,
            decision=detail.decision,
            rule_results=detail.rule_results,
            citation_items=detail.citation_items,
            grounded_explanation=detail.grounded_explanation,
            inquiry_summary=detail.inquiry_summary,
            policy_similarity=detail.policy_similarity,
        )


class ReviewActionResponse(_Schema):
    task: ReviewTaskResponse
    decision: HumanDecision | None = None
