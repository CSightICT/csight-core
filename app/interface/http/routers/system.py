"""Non-sensitive service metadata endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.bootstrap.settings import Settings
from app.interface.http.dependencies import provide_settings
from app.interface.http.schemas import SystemInfoResponse

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/info", response_model=SystemInfoResponse)
def system_info(
    settings: Annotated[Settings, Depends(provide_settings)],
) -> SystemInfoResponse:
    return SystemInfoResponse(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        api_schema_version=settings.api_schema_version,
    )
