"""Authenticated asynchronous Case-to-policy retrieval API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.application.policy_query_runs import StartPolicyRetrievalRunCommand
from app.interface.http.dependencies import provide_current_principal, provide_sprint4c2_services
from app.interface.http.policy_query_run_schemas import (
    PolicyRetrievalRunDetailResponse,
    PolicyRetrievalRunListResponse,
    PolicyRetrievalRunResponse,
    StartPolicyRetrievalRunRequest,
)
from app.interface.http.schemas import ErrorResponse
from app.interface.http.services import Sprint4C2ServiceContainer
from app.platform.tenant import Principal

router = APIRouter(
    prefix="/api/v1/cases/{case_id}/policy-retrieval-runs", tags=["policy-retrieval-runs"]
)


@router.post(
    "",
    name="start_policy_retrieval_run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PolicyRetrievalRunResponse,
    responses={
        200: {"model": PolicyRetrievalRunResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def start_policy_retrieval_run(
    case_id: str,
    body: StartPolicyRetrievalRunRequest,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint4C2ServiceContainer, Depends(provide_sprint4c2_services)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> PolicyRetrievalRunResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    if not isinstance(correlation_id, str) or not correlation_id:
        raise RuntimeError("correlation middleware did not establish a request identifier")
    result = services.start_policy_retrieval_run.execute(
        principal=principal,
        case_id=case_id,
        command=StartPolicyRetrievalRunCommand(
            **body.model_dump(),
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        ),
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    response.headers["Location"] = request.url_for(
        "get_policy_retrieval_run", case_id=case_id, run_id=result.run.id
    ).path
    response.headers["Cache-Control"] = "no-store"
    return PolicyRetrievalRunResponse.from_run(result.run)


@router.get("", response_model=PolicyRetrievalRunListResponse)
def list_policy_retrieval_runs(
    case_id: str,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint4C2ServiceContainer, Depends(provide_sprint4c2_services)],
) -> PolicyRetrievalRunListResponse:
    runs = services.list_policy_retrieval_runs.execute(principal=principal, case_id=case_id)
    response.headers["Cache-Control"] = "no-store"
    return PolicyRetrievalRunListResponse(
        items=tuple(PolicyRetrievalRunResponse.from_run(run) for run in runs)
    )


@router.get(
    "/{run_id}", name="get_policy_retrieval_run", response_model=PolicyRetrievalRunDetailResponse
)
def get_policy_retrieval_run(
    case_id: str,
    run_id: str,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint4C2ServiceContainer, Depends(provide_sprint4c2_services)],
) -> PolicyRetrievalRunDetailResponse:
    detail = services.get_policy_retrieval_run.execute(
        principal=principal, case_id=case_id, run_id=run_id
    )
    response.headers["Cache-Control"] = "no-store"
    return PolicyRetrievalRunDetailResponse.from_detail(detail)


__all__ = ["router"]
