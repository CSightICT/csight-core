"""Authenticated human-in-the-loop review use cases."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.platform.errors import ForbiddenError
from app.platform.human_review import (
    AdditionalEvidenceReason,
    EscalationReason,
    HumanDecision,
    HumanDecisionRequest,
    ReviewAssignee,
    ReviewTask,
)
from app.platform.tenant import Permission, Principal, Role
from app.ports.human_review import HumanReviewRepository, ReviewQueueQuery, ReviewTaskDetail


class _Command(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class HumanReviewRequestedCommand(_Command):
    event_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    policy_evaluation_run_id: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)

    @field_validator("event_id", "tenant_id", "case_id", "policy_evaluation_run_id")
    @classmethod
    def validate_uuid_identifiers(cls, value: str) -> str:
        try:
            UUID(value)
        except ValueError as error:
            raise ValueError("worker identifiers must be UUIDs") from error
        return value


class VersionedTaskCommand(_Command):
    expected_version: int = Field(ge=1)


class ReleaseTaskCommand(VersionedTaskCommand):
    reason_code: str | None = Field(default=None, min_length=1, max_length=128)
    rationale: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_reason(self) -> ReleaseTaskCommand:
        if not (self.reason_code or (self.rationale or "").strip()):
            raise ValueError("release requires a reason code or rationale")
        return self


class RequestEvidenceCommand(VersionedTaskCommand):
    reason_codes: tuple[AdditionalEvidenceReason, ...] = Field(min_length=1, max_length=10)
    instructions: str = Field(min_length=1, max_length=2000)
    rationale: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_other(self) -> RequestEvidenceCommand:
        if (
            AdditionalEvidenceReason.OTHER in self.reason_codes
            and not (self.rationale or "").strip()
        ):
            raise ValueError("OTHER requires rationale")
        return self


class ResumeTaskCommand(VersionedTaskCommand):
    rationale: str | None = Field(default=None, max_length=2000)


class EscalateTaskCommand(VersionedTaskCommand):
    reason_codes: tuple[EscalationReason, ...] = Field(min_length=1, max_length=10)
    rationale: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_other(self) -> EscalateTaskCommand:
        if EscalationReason.OTHER in self.reason_codes and not self.rationale.strip():
            raise ValueError("OTHER requires rationale")
        return self


class ResolveTaskCommand(VersionedTaskCommand):
    decision: HumanDecisionRequest
    correlation_id: str = Field(default="human-review-resolve", min_length=1, max_length=128)


class AssignTaskCommand(VersionedTaskCommand):
    assignee_id: str = Field(min_length=1)
    rationale: str = Field(min_length=5, max_length=500)

    @field_validator("assignee_id")
    @classmethod
    def validate_assignee_id(cls, value: str) -> str:
        try:
            UUID(value)
        except ValueError as error:
            raise ValueError("assignee_id must be a UUID") from error
        return value


class CreateReviewTaskFromPolicy:
    """Worker-safe task creation; this use case cannot create a human decision."""

    def __init__(self, repository: HumanReviewRepository) -> None:
        self._repository = repository

    def execute(self, command: HumanReviewRequestedCommand) -> str:
        _, replayed = self._repository.create_from_policy_evaluation(**command.model_dump())
        return "NOOP" if replayed else "CREATED"

    def record_failure(
        self,
        command: HumanReviewRequestedCommand,
        *,
        code: str,
        message: str,
    ) -> None:
        self._repository.record_consumer_failure(
            event_id=command.event_id,
            code=code,
            message=message,
        )

    def record_poison_event(self, *, event_id: str) -> None:
        self._repository.record_consumer_failure(
            event_id=event_id,
            code="HUMAN_REVIEW_QUEUE_PAYLOAD_INVALID",
            message="Human review queue payload failed UUID validation.",
        )


class ListHumanReviewTasks:
    def __init__(self, repository: HumanReviewRepository) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, query: ReviewQueueQuery) -> tuple[ReviewTask, ...]:
        principal.require(Permission.HUMAN_REVIEW_READ)
        return self._repository.list(
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            query=query,
        )


class ListReviewAssignees:
    def __init__(self, repository: HumanReviewRepository) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal) -> tuple[ReviewAssignee, ...]:
        if Role.ADMIN not in principal.roles:
            raise ForbiddenError()
        return self._repository.list_assignees(tenant_id=principal.tenant_id)


class GetHumanReviewTask:
    def __init__(self, repository: HumanReviewRepository) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, task_id: str) -> ReviewTaskDetail:
        principal.require(Permission.HUMAN_REVIEW_READ)
        detail = self._repository.get(tenant_id=principal.tenant_id, task_id=task_id)
        if detail is None:
            from app.platform.human_review import ReviewTaskNotFoundError

            raise ReviewTaskNotFoundError()
        if Role.REVIEWER in principal.roles and Role.ADMIN not in principal.roles:
            assigned_to_actor = detail.task.current_assignee_id == principal.user_id
            completed_by_actor = bool(
                detail.decision is not None and detail.decision.decided_by == principal.user_id
            )
            if not assigned_to_actor and not completed_by_actor:
                from app.platform.human_review import ReviewTaskNotFoundError

                raise ReviewTaskNotFoundError()
        return detail


class HumanReviewActions:
    def __init__(self, repository: HumanReviewRepository) -> None:
        self._repository = repository

    @staticmethod
    def _authorize(principal: Principal) -> None:
        principal.require(Permission.HUMAN_REVIEW_ACTION)

    def claim(
        self, *, principal: Principal, task_id: str, command: VersionedTaskCommand
    ) -> ReviewTask:
        self._authorize(principal)
        return self._repository.claim(
            tenant_id=principal.tenant_id,
            task_id=task_id,
            actor_id=principal.user_id,
            roles=principal.roles,
            expected_version=command.expected_version,
        )

    def assign(
        self, *, principal: Principal, task_id: str, command: AssignTaskCommand
    ) -> ReviewTask:
        if Role.ADMIN not in principal.roles:
            raise ForbiddenError()
        return self._repository.assign(
            tenant_id=principal.tenant_id,
            task_id=task_id,
            actor_id=principal.user_id,
            roles=principal.roles,
            **command.model_dump(),
        )

    def release(
        self, *, principal: Principal, task_id: str, command: ReleaseTaskCommand
    ) -> ReviewTask:
        self._authorize(principal)
        return self._repository.release(
            tenant_id=principal.tenant_id,
            task_id=task_id,
            actor_id=principal.user_id,
            roles=principal.roles,
            **command.model_dump(),
        )

    def request_evidence(
        self, *, principal: Principal, task_id: str, command: RequestEvidenceCommand
    ) -> ReviewTask:
        self._authorize(principal)
        return self._repository.request_additional_evidence(
            tenant_id=principal.tenant_id,
            task_id=task_id,
            actor_id=principal.user_id,
            roles=principal.roles,
            **command.model_dump(),
        )

    def resume(
        self, *, principal: Principal, task_id: str, command: ResumeTaskCommand
    ) -> ReviewTask:
        self._authorize(principal)
        return self._repository.resume(
            tenant_id=principal.tenant_id,
            task_id=task_id,
            actor_id=principal.user_id,
            roles=principal.roles,
            **command.model_dump(),
        )

    def escalate(
        self, *, principal: Principal, task_id: str, command: EscalateTaskCommand
    ) -> ReviewTask:
        self._authorize(principal)
        return self._repository.escalate(
            tenant_id=principal.tenant_id,
            task_id=task_id,
            actor_id=principal.user_id,
            roles=principal.roles,
            **command.model_dump(),
        )

    def resolve(
        self, *, principal: Principal, task_id: str, command: ResolveTaskCommand
    ) -> tuple[ReviewTask, HumanDecision]:
        self._authorize(principal)
        return self._repository.resolve(
            tenant_id=principal.tenant_id,
            task_id=task_id,
            actor_id=principal.user_id,
            roles=principal.roles,
            expected_version=command.expected_version,
            request=command.decision,
            correlation_id=command.correlation_id,
        )
