"""FastAPI dependency providers kept separate from the composition root."""

from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.bootstrap.dependencies import build_readiness_service
from app.bootstrap.settings import Settings
from app.interface.http.services import (
    Sprint1ServiceContainer,
    Sprint2ServiceContainer,
    Sprint4BServiceContainer,
)
from app.platform.errors import AuthenticationRequiredError
from app.platform.tenant import Principal
from app.ports.readiness import ReadinessService

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Short-lived CSight JWT access token",
)


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


def provide_sprint1_services(request: Request) -> Sprint1ServiceContainer:
    configured_services = getattr(request.app.state, "sprint1_services", None)
    if configured_services is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sprint 1 application services are unavailable.",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE"},
        )
    return cast(Sprint1ServiceContainer, configured_services)


def provide_optional_sprint2_services(request: Request) -> Sprint2ServiceContainer | None:
    """Return the optional Sprint 2 composition without making Sprint 1 routes unavailable."""

    configured_services = getattr(request.app.state, "sprint2_services", None)
    if configured_services is None:
        return None
    return cast(Sprint2ServiceContainer, configured_services)


def provide_sprint2_services(request: Request) -> Sprint2ServiceContainer:
    configured_services = provide_optional_sprint2_services(request)
    if configured_services is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sprint 2 analysis services are unavailable.",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE"},
        )
    return configured_services


def provide_sprint4b_services(request: Request) -> Sprint4BServiceContainer:
    configured_services = getattr(request.app.state, "sprint4b_services", None)
    if configured_services is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Policy retrieval services are unavailable.",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE"},
        )
    return cast(Sprint4BServiceContainer, configured_services)


def provide_current_principal(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
) -> Principal:
    """Resolve one current principal without logging or retaining the bearer token."""

    if (
        credentials is None
        or credentials.scheme.casefold() != "bearer"
        or not credentials.credentials.strip()
    ):
        raise AuthenticationRequiredError()
    services = provide_sprint1_services(request)
    return services.resolve_principal.execute(credentials.credentials)
