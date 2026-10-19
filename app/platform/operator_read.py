"""Technology-neutral operator queue and workflow read projections."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueueView(StrEnum):
    ALL = "all"
    MY = "my"
    UNASSIGNED = "unassigned"
    URGENT = "urgent"
    WAITING_EVIDENCE = "waiting_evidence"
    COMPLETE = "complete"


class QueueSort(StrEnum):
    NEWEST = "newest"
    OLDEST = "oldest"


class _Projection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class QueueCounts(_Projection):
    all: int = Field(ge=0)
    my: int = Field(ge=0)
    unassigned: int = Field(ge=0)
    urgent: int = Field(ge=0)
    waiting_evidence: int = Field(ge=0)
    complete: int = Field(ge=0)


class OperatorCaseItem(_Projection):
    case_id: str
    case_status: str
    order_ref: str
    product_ref: str
    requested_action: str
    inquiry_preview: str | None = Field(default=None, max_length=160)
    created_at: datetime
    updated_at: datetime
    review_task_id: str | None = None
    review_status: str | None = None
    review_priority: str | None = None
    assignee_id: str | None = None
    assignment_version: int = Field(ge=0)
    resolution_status: str | None = None
    report_id: str | None = None
    report_generated_at: datetime | None = None


class OperatorReviewItem(_Projection):
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
    assignee_id: str | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    resolution_status: str | None = None
    report_id: str | None = None
    report_generated_at: datetime | None = None


class OperatorCasePage(_Projection):
    items: tuple[OperatorCaseItem, ...]
    counts: QueueCounts
    next_cursor: str | None = None


class OperatorReviewPage(_Projection):
    items: tuple[OperatorReviewItem, ...]
    counts: QueueCounts
    next_cursor: str | None = None


class WorkflowComponent(_Projection):
    run_id: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_code: str | None = None
    correlation_id: str | None = None


class WorkflowStage(_Projection):
    stage_type: str
    status: str
    attempt_count: int = Field(ge=0)
    next_attempt_at: datetime | None = None
    failure_code: str | None = None


class WorkflowSnapshot(_Projection):
    case_id: str
    case_status: str
    terminal: bool
    degraded: bool
    retry_at: datetime | None
    last_good: str
    correlation_id: str | None
    analysis: WorkflowComponent | None
    stages: tuple[WorkflowStage, ...]
    policy_retrieval: WorkflowComponent | None
    grounded_explanation: WorkflowComponent | None
    policy_evaluation: WorkflowComponent | None
    review: WorkflowComponent | None
    resolution: WorkflowComponent | None
    report: WorkflowComponent | None

    @field_validator("retry_at")
    @classmethod
    def normalize_retry_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retry_at must be timezone-aware")
        return value.astimezone(UTC)


__all__ = [
    "OperatorCaseItem",
    "OperatorCasePage",
    "OperatorReviewItem",
    "OperatorReviewPage",
    "QueueCounts",
    "QueueSort",
    "QueueView",
    "WorkflowComponent",
    "WorkflowSnapshot",
    "WorkflowStage",
]
