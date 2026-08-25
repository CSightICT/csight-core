"""Tenant-scoped Case creation and query endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, Query, Response, status

from app.application.cases import CreateCaseCommand, ListCasesQuery
from app.interface.http.dependencies import (
    provide_current_principal,
    provide_sprint1_services,
)
from app.interface.http.schemas import ErrorResponse
from app.interface.http.services import Sprint1ServiceContainer
from app.interface.http.sprint1_schemas import (
    CaseDetailResponse,
    CaseListParameters,
    CaseListResponse,
    CreateCaseRequest,
    CreateCaseResponse,
    StatusHistoryListResponse,
    StatusHistoryResponse,
)
from app.platform.tenant import Principal

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])

AUTH_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}
CASE_QUERY_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **AUTH_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
}

CaseId = Annotated[str, Path(min_length=1, max_length=255, description="Opaque Case ID")]


@router.post(
    "",
    response_model=CreateCaseResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {
            "model": CreateCaseResponse,
            "description": "An idempotent replay of the original Case creation result.",
        },
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        **AUTH_ERROR_RESPONSES,
    },
)
def create_case(
    request: CreateCaseRequest,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint1ServiceContainer, Depends(provide_sprint1_services)],
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=255,
            description="Optional tenant-scoped idempotency key.",
        ),
    ] = None,
) -> CreateCaseResponse:
    result = services.create_case.execute(
        principal=principal,
        command=CreateCaseCommand(
            order_ref=request.order_ref,
            product_ref=request.product_ref,
            customer_message=request.customer_message,
            requested_action=request.requested_action,
            attributes=request.attributes,
            idempotency_key=idempotency_key,
        ),
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return CreateCaseResponse.from_result(result)


@router.get(
    "",
    response_model=CaseListResponse,
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        **AUTH_ERROR_RESPONSES,
    },
)
def list_cases(
    filters: Annotated[CaseListParameters, Query()],
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint1ServiceContainer, Depends(provide_sprint1_services)],
) -> CaseListResponse:
    page = services.list_cases.execute(
        principal=principal,
        query=ListCasesQuery(**filters.model_dump()),
    )
    return CaseListResponse.from_page(page)


@router.get(
    "/{case_id}",
    response_model=CaseDetailResponse,
    responses=CASE_QUERY_ERROR_RESPONSES,
)
def get_case_detail(
    case_id: CaseId,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint1ServiceContainer, Depends(provide_sprint1_services)],
) -> CaseDetailResponse:
    case = services.get_case.execute(principal=principal, case_id=case_id)
    evidence = services.list_case_evidence.execute(principal=principal, case_id=case_id)
    history = services.get_case_status_history.execute(principal=principal, case_id=case_id)
    return CaseDetailResponse.from_domain(case=case, evidence=evidence, history=history)


@router.get(
    "/{case_id}/status-history",
    response_model=StatusHistoryListResponse,
    responses=CASE_QUERY_ERROR_RESPONSES,
)
def get_case_status_history(
    case_id: CaseId,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint1ServiceContainer, Depends(provide_sprint1_services)],
) -> StatusHistoryListResponse:
    history = services.get_case_status_history.execute(principal=principal, case_id=case_id)
    return StatusHistoryListResponse(
        items=tuple(StatusHistoryResponse.from_transition(item) for item in history)
    )
