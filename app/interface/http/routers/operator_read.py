"""Authenticated, tenant-scoped operator queue and workflow reads."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.interface.http.dependencies import (
    provide_current_principal,
    provide_operator_read_services,
    require_case_access,
)
from app.interface.http.operator_read_schemas import (
    OperatorCasePageResponse,
    OperatorReviewPageResponse,
    WorkflowSnapshotResponse,
)
from app.interface.http.operator_read_services import OperatorReadServiceContainer
from app.platform.operator_read import QueueSort, QueueView
from app.platform.tenant import Principal

router = APIRouter(tags=["operator"])


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.get("/api/v1/operator/cases", response_model=OperatorCasePageResponse)
def list_operator_cases(
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[OperatorReadServiceContainer, Depends(provide_operator_read_services)],
    view: Annotated[QueueView, Query()] = QueueView.ALL,
    sort: Annotated[QueueSort, Query()] = QueueSort.NEWEST,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
) -> OperatorCasePageResponse:
    page = services.list_cases.execute(
        principal=principal,
        view=view,
        sort=sort,
        query=q,
        limit=limit,
        cursor=cursor,
    )
    _no_store(response)
    return OperatorCasePageResponse.from_page(page)


@router.get("/api/v1/operator/reviews", response_model=OperatorReviewPageResponse)
def list_operator_reviews(
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[OperatorReadServiceContainer, Depends(provide_operator_read_services)],
    view: Annotated[QueueView, Query()] = QueueView.ALL,
    sort: Annotated[QueueSort, Query()] = QueueSort.NEWEST,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
) -> OperatorReviewPageResponse:
    page = services.list_reviews.execute(
        principal=principal,
        view=view,
        sort=sort,
        query=q,
        limit=limit,
        cursor=cursor,
    )
    _no_store(response)
    return OperatorReviewPageResponse.from_page(page)


@router.get(
    "/api/v1/cases/{case_id}/workflow-snapshot",
    response_model=WorkflowSnapshotResponse,
    dependencies=[Depends(require_case_access)],
)
def get_workflow_snapshot(
    case_id: UUID,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[OperatorReadServiceContainer, Depends(provide_operator_read_services)],
) -> WorkflowSnapshotResponse:
    snapshot = services.get_workflow_snapshot.execute(
        principal=principal,
        case_id=str(case_id),
    )
    _no_store(response)
    return WorkflowSnapshotResponse.from_snapshot(snapshot)


__all__ = ["router"]
