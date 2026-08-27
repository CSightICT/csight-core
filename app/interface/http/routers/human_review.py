"""Tenant-scoped human review queue and explicit human action API."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.application.human_review import (
    EscalateTaskCommand,
    ReleaseTaskCommand,
    RequestEvidenceCommand,
    ResolveTaskCommand,
    ResumeTaskCommand,
    VersionedTaskCommand,
)
from app.interface.http.dependencies import provide_current_principal, provide_sprint5b_services
from app.interface.http.human_review_schemas import (
    EscalateRequest,
    EvidenceRequest,
    ReleaseRequest,
    ResolveRequest,
    ResumeRequest,
    ReviewActionResponse,
    ReviewTaskDetailResponse,
    ReviewTaskListResponse,
    ReviewTaskResponse,
    VersionRequest,
)
from app.interface.http.services import Sprint5BServiceContainer
from app.platform.human_review import ReviewPriority, ReviewTaskStatus, ReviewTaskType
from app.platform.tenant import Principal
from app.ports.human_review import ReviewQueueQuery

router = APIRouter(prefix="/api/v1/human-review-tasks", tags=["human-review"])
case_router = APIRouter(prefix="/api/v1/cases/{case_id}/human-review-tasks", tags=["human-review"])


def _query(
    *,
    status: ReviewTaskStatus | None,
    task_type: ReviewTaskType | None,
    priority: ReviewPriority | None,
    assigned_to: Literal["me"] | None,
    unassigned_only: bool,
    created_from: datetime | None,
    created_to: datetime | None,
    page: int,
    page_size: int,
    case_id: str | None = None,
) -> ReviewQueueQuery:
    return ReviewQueueQuery(
        status=status,
        task_type=task_type,
        priority=priority,
        assigned_to_me=assigned_to == "me",
        unassigned_only=unassigned_only,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
        case_id=case_id,
    )


@router.get("", response_model=ReviewTaskListResponse)
def list_tasks(
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5BServiceContainer, Depends(provide_sprint5b_services)],
    status: ReviewTaskStatus | None = None,
    task_type: ReviewTaskType | None = None,
    priority: ReviewPriority | None = None,
    assigned_to: Literal["me"] | None = None,
    unassigned_only: bool = False,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ReviewTaskListResponse:
    items = services.list_tasks.execute(
        principal=principal,
        query=_query(
            status=status,
            task_type=task_type,
            priority=priority,
            assigned_to=assigned_to,
            unassigned_only=unassigned_only,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        ),
    )
    response.headers["Cache-Control"] = "no-store"
    return ReviewTaskListResponse(items=tuple(ReviewTaskResponse.from_task(item) for item in items))


@case_router.get("", response_model=ReviewTaskListResponse)
def list_case_tasks(
    case_id: str,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5BServiceContainer, Depends(provide_sprint5b_services)],
) -> ReviewTaskListResponse:
    items = services.list_tasks.execute(
        principal=principal,
        query=_query(
            status=None,
            task_type=None,
            priority=None,
            assigned_to=None,
            unassigned_only=False,
            created_from=None,
            created_to=None,
            page=1,
            page_size=100,
            case_id=case_id,
        ),
    )
    response.headers["Cache-Control"] = "no-store"
    return ReviewTaskListResponse(items=tuple(ReviewTaskResponse.from_task(item) for item in items))


@router.get("/{task_id}", response_model=ReviewTaskDetailResponse)
def get_task(
    task_id: str,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5BServiceContainer, Depends(provide_sprint5b_services)],
) -> ReviewTaskDetailResponse:
    detail = services.get_task.execute(principal=principal, task_id=task_id)
    response.headers["Cache-Control"] = "no-store"
    return ReviewTaskDetailResponse.from_detail(detail)


@router.post("/{task_id}/claim", response_model=ReviewActionResponse)
def claim_task(
    task_id: str,
    body: VersionRequest,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5BServiceContainer, Depends(provide_sprint5b_services)],
) -> ReviewActionResponse:
    task = services.actions.claim(
        principal=principal,
        task_id=task_id,
        command=VersionedTaskCommand(expected_version=body.expected_version),
    )
    return ReviewActionResponse(task=ReviewTaskResponse.from_task(task))


@router.post("/{task_id}/release", response_model=ReviewActionResponse)
def release_task(
    task_id: str,
    body: ReleaseRequest,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5BServiceContainer, Depends(provide_sprint5b_services)],
) -> ReviewActionResponse:
    task = services.actions.release(
        principal=principal, task_id=task_id, command=ReleaseTaskCommand(**body.model_dump())
    )
    return ReviewActionResponse(task=ReviewTaskResponse.from_task(task))


@router.post("/{task_id}/request-additional-evidence", response_model=ReviewActionResponse)
def request_evidence(
    task_id: str,
    body: EvidenceRequest,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5BServiceContainer, Depends(provide_sprint5b_services)],
) -> ReviewActionResponse:
    task = services.actions.request_evidence(
        principal=principal, task_id=task_id, command=RequestEvidenceCommand(**body.model_dump())
    )
    return ReviewActionResponse(task=ReviewTaskResponse.from_task(task))


@router.post("/{task_id}/resume", response_model=ReviewActionResponse)
def resume_task(
    task_id: str,
    body: ResumeRequest,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5BServiceContainer, Depends(provide_sprint5b_services)],
) -> ReviewActionResponse:
    task = services.actions.resume(
        principal=principal, task_id=task_id, command=ResumeTaskCommand(**body.model_dump())
    )
    return ReviewActionResponse(task=ReviewTaskResponse.from_task(task))


@router.post("/{task_id}/escalate", response_model=ReviewActionResponse)
def escalate_task(
    task_id: str,
    body: EscalateRequest,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5BServiceContainer, Depends(provide_sprint5b_services)],
) -> ReviewActionResponse:
    task = services.actions.escalate(
        principal=principal, task_id=task_id, command=EscalateTaskCommand(**body.model_dump())
    )
    return ReviewActionResponse(task=ReviewTaskResponse.from_task(task))


@router.post("/{task_id}/resolve", response_model=ReviewActionResponse)
def resolve_task(
    task_id: str,
    body: ResolveRequest,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5BServiceContainer, Depends(provide_sprint5b_services)],
) -> ReviewActionResponse:
    task, decision = services.actions.resolve(
        principal=principal,
        task_id=task_id,
        command=ResolveTaskCommand(
            expected_version=body.expected_version,
            decision=body.to_domain(),
        ),
    )
    return ReviewActionResponse(task=ReviewTaskResponse.from_task(task), decision=decision)


__all__ = ["case_router", "router"]
