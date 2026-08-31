"""Admin-only, tenant-scoped, aggregate operations reads."""

from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.interface.http.dependencies import provide_current_principal
from app.interface.http.operations_schemas import (
    ActivateModelReleaseRequest,
    ActivateModelRouteRequest,
    ActiveModelReleaseResponse,
    ActiveModelRouteResponse,
    ModelActivationResponse,
    ModelRouteActivationResponse,
    OnboardingReadinessResponse,
    OperationalFailureResolutionResponse,
    OperationsFailuresResponse,
    OperationsOverviewResponse,
    RegisteredModelReleaseResponse,
    RegisterModelReleaseRequest,
)
from app.interface.http.operations_services import (
    OperationsServiceContainer,
    provide_operations_services,
)
from app.interface.http.schemas import ErrorDetail, ErrorResponse
from app.platform.analysis.enums import AnalysisExecutionMode
from app.platform.model_activation import ModelReleaseTask
from app.platform.model_routing import (
    ActiveModelRoutePlanRequiredError,
    ModelRouteActivationConflictError,
    ModelRoutePlanConflictError,
)
from app.platform.tenant import Principal, Role

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _boundary_error(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    configured_correlation_id = getattr(request.state, "correlation_id", None)
    correlation_id = (
        configured_correlation_id
        if isinstance(configured_correlation_id, str) and configured_correlation_id
        else str(uuid4())
    )
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            correlation_id=correlation_id,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "X-Correlation-ID": correlation_id,
        },
    )


@router.get(
    "/onboarding-readiness",
    response_model=OnboardingReadinessResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
def get_onboarding_readiness(
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        OperationsServiceContainer | None,
        Depends(provide_operations_services),
    ],
) -> OnboardingReadinessResponse | Response:
    if Role.ADMIN not in principal.roles:
        return _boundary_error(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="The authenticated user is not allowed to perform this operation.",
        )
    if services is None or services.get_onboarding_readiness is None:
        return _boundary_error(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            message="Onboarding readiness is unavailable.",
        )
    readiness = services.get_onboarding_readiness.execute(principal=principal)
    _no_store(response)
    return OnboardingReadinessResponse.from_readiness(readiness)


@router.get("/overview", response_model=OperationsOverviewResponse)
def get_operations_overview(
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        OperationsServiceContainer | None,
        Depends(provide_operations_services),
    ],
) -> OperationsOverviewResponse | Response:
    if Role.ADMIN not in principal.roles:
        return _boundary_error(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="The authenticated user is not allowed to perform this operation.",
        )
    if services is None:
        return _boundary_error(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            message="Operations read services are unavailable.",
        )
    overview = services.get_overview.execute(principal=principal)
    _no_store(response)
    return OperationsOverviewResponse.from_overview(overview)


@router.get("/failures", response_model=OperationsFailuresResponse)
def get_operations_failures(
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        OperationsServiceContainer | None,
        Depends(provide_operations_services),
    ],
    lookback_hours: Annotated[
        Any,
        Query(
            description="Failure signal lookback in whole hours (1-168).",
            json_schema_extra={
                "type": "integer",
                "minimum": 1,
                "maximum": 168,
                "default": 24,
            },
        ),
    ] = 24,
    limit: Annotated[
        Any,
        Query(
            description="Maximum durable failure records returned (1-100).",
            json_schema_extra={
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "default": 50,
            },
        ),
    ] = 50,
    cursor: Annotated[
        str | None,
        Query(min_length=1, max_length=512, description="Opaque failure-page cursor."),
    ] = None,
) -> OperationsFailuresResponse | Response:
    if Role.ADMIN not in principal.roles:
        return _boundary_error(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="The authenticated user is not allowed to perform this operation.",
        )
    try:
        parsed_lookback_hours = int(lookback_hours)
    except ValueError:
        parsed_lookback_hours = 0
    if not 1 <= parsed_lookback_hours <= 168:
        return _boundary_error(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="VALIDATION_ERROR",
            message="Operations failure lookback must be between 1 and 168 hours.",
        )
    try:
        parsed_limit = int(limit)
    except ValueError:
        parsed_limit = 0
    if not 1 <= parsed_limit <= 100:
        return _boundary_error(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="VALIDATION_ERROR",
            message="Operations failure page size must be between 1 and 100.",
        )
    if services is None:
        return _boundary_error(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            message="Operations read services are unavailable.",
        )
    failures = services.get_failures.execute(
        principal=principal,
        lookback_hours=parsed_lookback_hours,
    )
    if services.list_failure_records is not None:
        page = services.list_failure_records.execute(
            principal=principal,
            lookback_hours=parsed_lookback_hours,
            limit=parsed_limit,
            cursor=cursor,
        )
        failures = failures.model_copy(
            update={"items": page.items, "next_cursor": page.next_cursor}
        )
    _no_store(response)
    return OperationsFailuresResponse.from_failures(failures)


FailureId = Annotated[
    str,
    Path(min_length=1, max_length=64, description="Opaque operational failure ID."),
]
FailureIdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
        pattern=r"\S",
        description="Required tenant-scoped recovery mutation key.",
    ),
]


@router.post(
    "/failures/{failure_id}/replay",
    response_model=OperationalFailureResolutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_200_OK: {
            "model": OperationalFailureResolutionResponse,
            "description": "Idempotent replay of the same recovery request.",
        },
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
def replay_operational_failure(
    failure_id: FailureId,
    idempotency_key: FailureIdempotencyKey,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        OperationsServiceContainer | None,
        Depends(provide_operations_services),
    ],
) -> OperationalFailureResolutionResponse | Response:
    if Role.ADMIN not in principal.roles:
        return _boundary_error(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="The authenticated user is not allowed to perform this operation.",
        )
    if services is None or services.replay_failure is None:
        return _boundary_error(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            message="Operational failure recovery is unavailable.",
        )
    correlation_id = getattr(request.state, "correlation_id", None)
    if not isinstance(correlation_id, str) or not correlation_id:
        correlation_id = str(uuid4())
    result = services.replay_failure.execute(
        principal=principal,
        failure_id=failure_id,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    _no_store(response)
    return OperationalFailureResolutionResponse.from_result(result)


@router.post(
    "/failures/{failure_id}/cancel",
    response_model=OperationalFailureResolutionResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
def cancel_operational_failure(
    failure_id: FailureId,
    idempotency_key: FailureIdempotencyKey,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        OperationsServiceContainer | None,
        Depends(provide_operations_services),
    ],
) -> OperationalFailureResolutionResponse | Response:
    if Role.ADMIN not in principal.roles:
        return _boundary_error(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="The authenticated user is not allowed to perform this operation.",
        )
    if services is None or services.cancel_failure is None:
        return _boundary_error(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            message="Operational failure recovery is unavailable.",
        )
    correlation_id = getattr(request.state, "correlation_id", None)
    if not isinstance(correlation_id, str) or not correlation_id:
        correlation_id = str(uuid4())
    result = services.cancel_failure.execute(
        principal=principal,
        failure_id=failure_id,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    _no_store(response)
    return OperationalFailureResolutionResponse.from_result(result)


@router.post(
    "/model-releases",
    response_model=RegisteredModelReleaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_model_release(
    body: RegisterModelReleaseRequest,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        OperationsServiceContainer | None,
        Depends(provide_operations_services),
    ],
) -> RegisteredModelReleaseResponse | Response:
    unavailable = _model_release_boundary(request, principal=principal, services=services)
    if unavailable is not None:
        return unavailable
    assert services is not None and services.register_model_release is not None
    result = services.register_model_release.execute(
        principal=principal,
        value=body.signed_manifest(),
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    _no_store(response)
    return RegisteredModelReleaseResponse(
        release=result.release,
        idempotent_replay=result.idempotent_replay,
    )


@router.post(
    "/model-releases/{release_id}/activate",
    response_model=ModelActivationResponse,
    status_code=status.HTTP_201_CREATED,
)
def activate_model_release(
    release_id: Annotated[str, Path(min_length=1, max_length=64)],
    body: ActivateModelReleaseRequest,
    idempotency_key: FailureIdempotencyKey,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        OperationsServiceContainer | None,
        Depends(provide_operations_services),
    ],
) -> ModelActivationResponse | Response:
    unavailable = _model_release_boundary(request, principal=principal, services=services)
    if unavailable is not None:
        return unavailable
    assert services is not None and services.activate_model_release is not None
    result = services.activate_model_release.execute(
        principal=principal,
        release_id=release_id,
        execution_mode=body.execution_mode,
        expected_current_activation_id=body.expected_current_activation_id,
        reason=body.reason,
        idempotency_key=idempotency_key,
    )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    _no_store(response)
    return ModelActivationResponse(
        activation=result.activation,
        idempotent_replay=result.idempotent_replay,
    )


@router.get(
    "/model-activations/active",
    response_model=ActiveModelReleaseResponse,
)
def get_active_model_release(
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        OperationsServiceContainer | None,
        Depends(provide_operations_services),
    ],
    task: Annotated[ModelReleaseTask, Query()],
    execution_mode: Annotated[AnalysisExecutionMode, Query()],
) -> ActiveModelReleaseResponse | Response:
    unavailable = _model_release_boundary(request, principal=principal, services=services)
    if unavailable is not None:
        return unavailable
    assert services is not None and services.get_active_model_release is not None
    active = services.get_active_model_release.execute(
        principal=principal,
        task=task,
        execution_mode=execution_mode,
    )
    if active is None:
        return _boundary_error(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="ACTIVE_MODEL_RELEASE_REQUIRED",
            message="No active signed model release exists for this execution profile.",
        )
    _no_store(response)
    return ActiveModelReleaseResponse(
        task=task,
        execution_mode=execution_mode,
        active=active,
    )


ModelRouteIdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
        pattern=r"\S",
        description="Required tenant/task/mode-scoped model route activation key.",
    ),
]


@router.post(
    "/model-route-plans/activate",
    response_model=ModelRouteActivationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_200_OK: {
            "model": ModelRouteActivationResponse,
            "description": "Idempotent replay of the same model route activation.",
        },
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
def activate_model_route(
    body: ActivateModelRouteRequest,
    idempotency_key: ModelRouteIdempotencyKey,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        OperationsServiceContainer | None,
        Depends(provide_operations_services),
    ],
) -> ModelRouteActivationResponse | Response:
    unavailable = _model_route_boundary(request, principal=principal, services=services)
    if unavailable is not None:
        return unavailable
    assert services is not None and services.activate_model_route is not None
    try:
        result = services.activate_model_route.execute(
            principal=principal,
            task=body.task,
            execution_mode=body.execution_mode,
            model_activation_id=body.model_activation_id,
            deployment_id=body.deployment_id,
            expected_current_route_plan_id=body.expected_current_route_plan_id,
            reason=body.reason,
            idempotency_key=idempotency_key,
        )
    except (ModelRoutePlanConflictError, ModelRouteActivationConflictError) as error:
        return _boundary_error(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code=error.code,
            message=error.message,
        )
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    _no_store(response)
    return ModelRouteActivationResponse.from_result(result)


@router.get(
    "/model-route-plans/active",
    response_model=ActiveModelRouteResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
def get_active_model_route(
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        OperationsServiceContainer | None,
        Depends(provide_operations_services),
    ],
    task: Annotated[ModelReleaseTask, Query()],
    execution_mode: Annotated[AnalysisExecutionMode, Query()],
) -> ActiveModelRouteResponse | Response:
    unavailable = _model_route_boundary(request, principal=principal, services=services)
    if unavailable is not None:
        return unavailable
    assert services is not None and services.get_active_model_route is not None
    try:
        result = services.get_active_model_route.execute(
            principal=principal,
            task=task,
            execution_mode=execution_mode,
        )
    except ActiveModelRoutePlanRequiredError as error:
        return _boundary_error(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code=error.code,
            message=error.message,
        )
    except ModelRouteActivationConflictError as error:
        return _boundary_error(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code=error.code,
            message=error.message,
        )
    _no_store(response)
    return ActiveModelRouteResponse.from_result(result)


def _model_release_boundary(
    request: Request,
    *,
    principal: Principal,
    services: OperationsServiceContainer | None,
) -> Response | None:
    if Role.ADMIN not in principal.roles:
        return _boundary_error(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="The authenticated user is not allowed to perform this operation.",
        )
    if (
        services is None
        or services.register_model_release is None
        or services.activate_model_release is None
        or services.get_active_model_release is None
    ):
        return _boundary_error(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            message="Signed model release management is unavailable.",
        )
    return None


def _model_route_boundary(
    request: Request,
    *,
    principal: Principal,
    services: OperationsServiceContainer | None,
) -> Response | None:
    if Role.ADMIN not in principal.roles:
        return _boundary_error(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="The authenticated user is not allowed to perform this operation.",
        )
    if (
        services is None
        or services.activate_model_route is None
        or services.get_active_model_route is None
    ):
        return _boundary_error(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            message="Model route management is unavailable.",
        )
    return None


__all__ = ["router"]
