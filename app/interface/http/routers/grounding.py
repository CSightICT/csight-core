"""Authenticated asynchronous grounded policy explanation API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.application.grounding import StartGroundedExplanationCommand
from app.interface.http.dependencies import provide_current_principal, provide_sprint4c3a_services
from app.interface.http.grounding_schemas import (
    GroundedExplanationRunDetailResponse,
    GroundedExplanationRunListResponse,
    GroundedExplanationRunResponse,
    StartGroundedExplanationRequest,
)
from app.interface.http.schemas import ErrorResponse
from app.interface.http.services import Sprint4C3AServiceContainer
from app.platform.tenant import Principal

router = APIRouter(
    prefix="/api/v1/cases/{case_id}/grounded-explanation-runs",
    tags=["grounded-policy-explanations"],
)


@router.post(
    "",
    name="start_grounded_explanation_run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GroundedExplanationRunResponse,
    responses={
        200: {"model": GroundedExplanationRunResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def start_grounded_explanation_run(
    case_id: str,
    body: StartGroundedExplanationRequest,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint4C3AServiceContainer, Depends(provide_sprint4c3a_services)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> GroundedExplanationRunResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    if not isinstance(correlation_id, str) or not correlation_id:
        raise RuntimeError("correlation middleware did not establish a request identifier")
    result = services.start_grounded_explanation.execute(
        principal=principal,
        case_id=case_id,
        command=StartGroundedExplanationCommand(
            retrieval_run_id=body.retrieval_run_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        ),
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    response.headers["Location"] = request.url_for(
        "get_grounded_explanation_run",
        case_id=case_id,
        run_id=result.run.id,
    ).path
    response.headers["Cache-Control"] = "no-store"
    return GroundedExplanationRunResponse.from_run(result.run)


@router.get("", response_model=GroundedExplanationRunListResponse)
def list_grounded_explanation_runs(
    case_id: str,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint4C3AServiceContainer, Depends(provide_sprint4c3a_services)],
) -> GroundedExplanationRunListResponse:
    runs = services.list_grounded_explanations.execute(principal=principal, case_id=case_id)
    response.headers["Cache-Control"] = "no-store"
    return GroundedExplanationRunListResponse(
        items=tuple(GroundedExplanationRunResponse.from_run(run) for run in runs)
    )


@router.get(
    "/{run_id}",
    name="get_grounded_explanation_run",
    response_model=GroundedExplanationRunDetailResponse,
)
def get_grounded_explanation_run(
    case_id: str,
    run_id: str,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint4C3AServiceContainer, Depends(provide_sprint4c3a_services)],
) -> GroundedExplanationRunDetailResponse:
    detail = services.get_grounded_explanation.execute(
        principal=principal,
        case_id=case_id,
        run_id=run_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return GroundedExplanationRunDetailResponse.from_detail(detail)


__all__ = ["router"]
