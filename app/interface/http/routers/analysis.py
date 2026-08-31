"""Tenant-scoped append-only analysis-run endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status

from app.application.analysis import ListAnalysisRunsQuery, StartTextAnalysisCommand
from app.interface.http.analysis_schemas import (
    AnalysisRunDetailResponse,
    AnalysisRunListParameters,
    AnalysisRunListResponse,
    AnalysisRunResponse,
    StartTextAnalysisRequest,
)
from app.interface.http.dependencies import (
    provide_current_principal,
    provide_sprint2_services,
    require_case_access,
)
from app.interface.http.schemas import ErrorResponse
from app.interface.http.services import Sprint2ServiceContainer
from app.platform.tenant import Principal

router = APIRouter(
    prefix="/api/v1/cases/{case_id}/analysis-runs",
    tags=["analysis"],
    dependencies=[Depends(require_case_access)],
)

ANALYSIS_RUN_RESPONSE_HEADERS: dict[str, dict[str, object]] = {
    "Location": {
        "description": "Relative URL of the created or replayed analysis run.",
        "schema": {"type": "string"},
    },
    "Cache-Control": {
        "description": "Analysis responses must not be stored.",
        "schema": {"type": "string", "example": "no-store"},
    },
}
ANALYSIS_AUTH_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}
ANALYSIS_QUERY_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **ANALYSIS_AUTH_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
}

CaseId = Annotated[str, Path(min_length=1, max_length=255, description="Opaque Case ID")]
AnalysisRunId = Annotated[
    str,
    Path(min_length=1, max_length=255, description="Opaque Analysis Run ID"),
]


def _disable_storage(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.post(
    "",
    name="start_text_analysis",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_200_OK: {
            "model": AnalysisRunResponse,
            "description": "An idempotent replay of the original analysis run.",
            "headers": ANALYSIS_RUN_RESPONSE_HEADERS,
        },
        status.HTTP_202_ACCEPTED: {
            "model": AnalysisRunResponse,
            "description": "A new append-only analysis run was accepted.",
            "headers": ANALYSIS_RUN_RESPONSE_HEADERS,
        },
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "model": ErrorResponse,
            "description": "The transaction-safe nonterminal run budget is full.",
            "headers": {
                "Retry-After": {
                    "description": "Seconds before retrying a new admission.",
                    "schema": {"type": "integer"},
                }
            },
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        **ANALYSIS_AUTH_ERROR_RESPONSES,
    },
)
def start_text_analysis(
    case_id: CaseId,
    body: StartTextAnalysisRequest,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint2ServiceContainer, Depends(provide_sprint2_services)],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=255,
            pattern=r"\S",
            description="Required tenant-scoped analysis request key.",
        ),
    ],
) -> AnalysisRunResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    if not isinstance(correlation_id, str) or not correlation_id:
        raise RuntimeError("correlation middleware did not establish a request identifier")
    result = services.start_text_analysis.execute(
        principal=principal,
        case_id=case_id,
        command=StartTextAnalysisCommand(
            pipeline=body.pipeline,
            pipeline_version=body.pipeline_version,
            execution_mode=body.execution_mode,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        ),
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    response.headers["Location"] = request.url_for(
        "get_analysis_run",
        case_id=case_id,
        analysis_run_id=result.run.id,
    ).path
    _disable_storage(response)
    return AnalysisRunResponse.from_run(result.run)


@router.get(
    "",
    name="list_analysis_runs",
    response_model=AnalysisRunListResponse,
    responses=ANALYSIS_QUERY_ERROR_RESPONSES,
)
def list_analysis_runs(
    response: Response,
    case_id: CaseId,
    filters: Annotated[AnalysisRunListParameters, Query()],
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint2ServiceContainer, Depends(provide_sprint2_services)],
) -> AnalysisRunListResponse:
    page = services.list_analysis_runs.execute(
        principal=principal,
        case_id=case_id,
        query=ListAnalysisRunsQuery(**filters.model_dump()),
    )
    _disable_storage(response)
    return AnalysisRunListResponse.from_page(page)


@router.get(
    "/{analysis_run_id}",
    name="get_analysis_run",
    response_model=AnalysisRunDetailResponse,
    responses=ANALYSIS_QUERY_ERROR_RESPONSES,
)
def get_analysis_run(
    response: Response,
    case_id: CaseId,
    analysis_run_id: AnalysisRunId,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint2ServiceContainer, Depends(provide_sprint2_services)],
) -> AnalysisRunDetailResponse:
    detail = services.get_analysis_run.execute(
        principal=principal,
        case_id=case_id,
        analysis_run_id=analysis_run_id,
    )
    _disable_storage(response)
    return AnalysisRunDetailResponse.from_detail(detail)
