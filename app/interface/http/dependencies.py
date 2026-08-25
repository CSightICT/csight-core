"""FastAPI dependency providers kept separate from the composition root."""

from typing import Annotated, cast

from fastapi import Depends, Request

from app.bootstrap.dependencies import build_readiness_service
from app.bootstrap.settings import Settings
from app.ports.readiness import ReadinessService


def provide_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def provide_readiness_service(
    request: Request,
    settings: Annotated[Settings, Depends(provide_settings)],
) -> ReadinessService:
    configured_service = getattr(request.app.state, "readiness_service", None)
    if configured_service is None:
        configured_service = build_readiness_service(settings)
        request.app.state.readiness_service = configured_service
    return cast(ReadinessService, configured_service)
