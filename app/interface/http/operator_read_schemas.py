"""Public response contracts for operator queues and workflow state."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.platform.operator_read import (
    OperatorCasePage,
    OperatorReviewPage,
    WorkflowSnapshot,
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueueCountsResponse(_Schema):
    all: int
    my: int
    unassigned: int
    urgent: int
    waiting_evidence: int
    complete: int


class OperatorCaseItemResponse(_Schema):
    case_id: str
    case_status: str
    order_ref: str
    product_ref: str
    requested_action: str
    inquiry_preview: str | None = Field(default=None, max_length=160)
    created_at: datetime
    updated_at: datetime
    review_task_id: str | None
    review_status: str | None
    review_priority: str | None
    assignee_id: str | None
    assignment_version: int
    resolution_status: str | None
    report_id: str | None
    report_generated_at: datetime | None


class OperatorReviewItemResponse(_Schema):
    review_task_id: str
    case_id: str
    case_status: str
    order_ref: str
    product_ref: str
    requested_action: str
    inquiry_preview: str | None = Field(default=None, max_length=160)
    task_type: str
    priority: str
    status: str
    assignee_id: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    resolution_status: str | None
    report_id: str | None
    report_generated_at: datetime | None


class OperatorCasePageResponse(_Schema):
    items: list[OperatorCaseItemResponse]
    counts: QueueCountsResponse
    next_cursor: str | None

    @classmethod
    def from_page(cls, page: OperatorCasePage) -> OperatorCasePageResponse:
        return cls.model_validate(page.model_dump(mode="python"))


class OperatorReviewPageResponse(_Schema):
    items: list[OperatorReviewItemResponse]
    counts: QueueCountsResponse
    next_cursor: str | None

    @classmethod
    def from_page(cls, page: OperatorReviewPage) -> OperatorReviewPageResponse:
        return cls.model_validate(page.model_dump(mode="python"))


class WorkflowComponentResponse(_Schema):
    run_id: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None
    correlation_id: str | None


class WorkflowStageResponse(_Schema):
    stage_type: str
    status: str
    attempt_count: int
    next_attempt_at: datetime | None
    failure_code: str | None


class WorkflowSnapshotResponse(_Schema):
    case_id: str
    case_status: str
    terminal: bool
    degraded: bool
    retry_at: datetime | None
    last_good: str
    correlation_id: str | None
    analysis: WorkflowComponentResponse | None
    stages: list[WorkflowStageResponse]
    policy_retrieval: WorkflowComponentResponse | None
    grounded_explanation: WorkflowComponentResponse | None
    policy_evaluation: WorkflowComponentResponse | None
    review: WorkflowComponentResponse | None
    resolution: WorkflowComponentResponse | None
    report: WorkflowComponentResponse | None

    @classmethod
    def from_snapshot(cls, snapshot: WorkflowSnapshot) -> WorkflowSnapshotResponse:
        return cls.model_validate(snapshot.model_dump(mode="python"))


__all__ = [
    "OperatorCasePageResponse",
    "OperatorReviewPageResponse",
    "WorkflowSnapshotResponse",
]
