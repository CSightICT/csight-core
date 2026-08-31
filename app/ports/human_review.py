"""Ports for human review queue, audit actions, and immutable decisions."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.platform.human_review import (
    AdditionalEvidenceReason,
    DecisionBasisReference,
    EscalationReason,
    HumanDecision,
    HumanDecisionRequest,
    ReviewAction,
    ReviewAssignee,
    ReviewPacket,
    ReviewPriority,
    ReviewTask,
    ReviewTaskStatus,
    ReviewTaskType,
)
from app.platform.tenant import Role


class _DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ReviewQueueQuery(_DTO):
    status: ReviewTaskStatus | None = None
    task_type: ReviewTaskType | None = None
    priority: ReviewPriority | None = None
    assigned_to_me: bool = False
    unassigned_only: bool = False
    created_from: datetime | None = None
    created_to: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)
    case_id: str | None = None


class ReviewTaskDetail(_DTO):
    task: ReviewTask
    packet: ReviewPacket
    actions: tuple[ReviewAction, ...]
    decision: HumanDecision | None
    rule_results: tuple[dict[str, object], ...]
    citation_items: tuple[dict[str, object], ...]
    grounded_explanation: dict[str, object] | None
    inquiry_summary: str | None = None
    policy_similarity: tuple[dict[str, object], ...] = ()


class HumanReviewRepository(Protocol):
    def create_from_policy_evaluation(
        self,
        *,
        event_id: str,
        tenant_id: str,
        case_id: str,
        policy_evaluation_run_id: str,
        correlation_id: str,
    ) -> tuple[ReviewTask, bool]: ...

    def record_consumer_failure(
        self,
        *,
        event_id: str,
        code: str,
        message: str,
    ) -> None: ...

    def list(
        self, *, tenant_id: str, actor_id: str, query: ReviewQueueQuery
    ) -> tuple[ReviewTask, ...]: ...

    def get(self, *, tenant_id: str, task_id: str) -> ReviewTaskDetail | None: ...

    def list_assignees(self, *, tenant_id: str) -> tuple[ReviewAssignee, ...]: ...

    def assign(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
        assignee_id: str,
        rationale: str,
    ) -> ReviewTask: ...

    def claim(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
    ) -> ReviewTask: ...

    def release(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
        reason_code: str | None,
        rationale: str | None,
    ) -> ReviewTask: ...

    def request_additional_evidence(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
        reason_codes: tuple[AdditionalEvidenceReason, ...],
        instructions: str,
        rationale: str | None,
    ) -> ReviewTask: ...

    def resume(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
        rationale: str | None,
    ) -> ReviewTask: ...

    def escalate(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
        reason_codes: tuple[EscalationReason, ...],
        rationale: str,
    ) -> ReviewTask: ...

    def resolve(
        self,
        *,
        tenant_id: str,
        task_id: str,
        actor_id: str,
        roles: frozenset[Role],
        expected_version: int,
        request: HumanDecisionRequest,
        correlation_id: str = "human-review-resolve",
    ) -> tuple[ReviewTask, HumanDecision]: ...


__all__ = [
    "DecisionBasisReference",
    "HumanReviewRepository",
    "ReviewQueueQuery",
    "ReviewTaskDetail",
]
