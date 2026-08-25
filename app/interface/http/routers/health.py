"""Process liveness and dependency readiness endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.bootstrap.settings import Settings
from app.interface.http.dependencies import provide_readiness_service, provide_settings
from app.interface.http.schemas import LiveResponse, ReadyResponse
from app.ports.readiness import ReadinessService

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LiveResponse, status_code=status.HTTP_200_OK)
def live(settings: Annotated[Settings, Depends(provide_settings)]) -> LiveResponse:
    """Report process liveness without touching external infrastructure."""

    return LiveResponse(service=settings.app_name)


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
)
def ready(
    response: Response,
    settings: Annotated[Settings, Depends(provide_settings)],
    readiness: Annotated[ReadinessService, Depends(provide_readiness_service)],
) -> ReadyResponse:
    """Probe PostgreSQL, RabbitMQ, and MinIO and fail closed on any outage."""

    report = readiness.check()
    if not report.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(
        status="ok" if report.ready else "unavailable",
        service=settings.app_name,
        dependencies=report.as_status_map(),
    )
