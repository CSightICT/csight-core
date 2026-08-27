"""Authenticated case-scoped deterministic policy evaluation API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.application.policy_engine import StartPolicyEvaluationCommand
from app.interface.http.dependencies import provide_current_principal, provide_sprint5a_services
from app.interface.http.policy_evaluation_schemas import (
    PolicyEvaluationRunDetailResponse,
    PolicyEvaluationRunListResponse,
    PolicyEvaluationRunResponse,
    PolicyEvaluationRunSummary,
    StartPolicyEvaluationRequest,
)
from app.interface.http.schemas import ErrorResponse
from app.interface.http.services import Sprint5AServiceContainer
from app.platform.tenant import Principal

router = APIRouter(
    prefix="/api/v1/cases/{case_id}/policy-evaluation-runs",
    tags=["policy-evaluations"],
)


@router.post(
    "",
    name="start_policy_evaluation_run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PolicyEvaluationRunResponse,
    responses={
        200: {"model": PolicyEvaluationRunResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def start_policy_evaluation_run(
    case_id: str,
    body: StartPolicyEvaluationRequest,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5AServiceContainer, Depends(provide_sprint5a_services)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> PolicyEvaluationRunResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    if not isinstance(correlation_id, str) or not correlation_id:
        raise RuntimeError("correlation middleware did not establish a request identifier")
    result = services.start_policy_evaluation.execute(
        principal=principal,
        case_id=case_id,
        command=StartPolicyEvaluationCommand(
            analysis_run_id=body.analysis_run_id,
            as_of_date=body.as_of_date,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        ),
    )
    payload = PolicyEvaluationRunResponse.from_run(result.run)
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    response.headers["Location"] = payload.location
    response.headers["Cache-Control"] = "no-store"
    return payload


@router.get("", response_model=PolicyEvaluationRunListResponse)
def list_policy_evaluation_runs(
    case_id: str,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5AServiceContainer, Depends(provide_sprint5a_services)],
) -> PolicyEvaluationRunListResponse:
    runs = services.list_policy_evaluations.execute(principal=principal, case_id=case_id)
    response.headers["Cache-Control"] = "no-store"
    return PolicyEvaluationRunListResponse(
        items=tuple(PolicyEvaluationRunSummary.from_run(run) for run in runs)
    )


@router.get(
    "/{run_id}",
    name="get_policy_evaluation_run",
    response_model=PolicyEvaluationRunDetailResponse,
)
def get_policy_evaluation_run(
    case_id: str,
    run_id: str,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5AServiceContainer, Depends(provide_sprint5a_services)],
) -> PolicyEvaluationRunDetailResponse:
    detail = services.get_policy_evaluation.execute(
        principal=principal,
        case_id=case_id,
        run_id=run_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return PolicyEvaluationRunDetailResponse.from_detail(detail)


__all__ = ["router"]
