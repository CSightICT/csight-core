"""FastAPI dependency providers kept separate from the composition root."""

from collections.abc import AsyncGenerator
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.oidc import OidcSessionService
from app.bootstrap.dependencies import build_readiness_service
from app.bootstrap.settings import Settings
from app.interface.http.oidc_router import OidcCookieConfiguration
from app.interface.http.operator_read_services import OperatorReadServiceContainer
from app.interface.http.poc_reporting_services import PocReportingServiceContainer
from app.interface.http.services import (
    Sprint1ServiceContainer,
    Sprint2ServiceContainer,
    Sprint4BServiceContainer,
    Sprint4C2ServiceContainer,
    Sprint4C3AServiceContainer,
    Sprint5AServiceContainer,
    Sprint5BServiceContainer,
    Sprint5CServiceContainer,
)
from app.platform.errors import AuthenticationRequiredError
from app.platform.oidc import InvalidOidcCsrfTokenError
from app.platform.tenant import Principal, Role
from app.platform.tenant_context import case_access_context, tenant_context
from app.ports.readiness import ReadinessService

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Short-lived CSight JWT access token",
)
_SAFE_SESSION_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


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


def provide_sprint4c2_services(request: Request) -> Sprint4C2ServiceContainer:
    configured_services = getattr(request.app.state, "sprint4c2_services", None)
    if configured_services is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Policy retrieval run services are unavailable.",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE"},
        )
    return cast(Sprint4C2ServiceContainer, configured_services)


def provide_sprint4c3a_services(request: Request) -> Sprint4C3AServiceContainer:
    configured_services = getattr(request.app.state, "sprint4c3a_services", None)
    if configured_services is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Grounded policy explanation services are unavailable.",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE"},
        )
    return cast(Sprint4C3AServiceContainer, configured_services)


def provide_sprint5a_services(request: Request) -> Sprint5AServiceContainer:
    configured_services = getattr(request.app.state, "sprint5a_services", None)
    if configured_services is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Policy evaluation services are unavailable.",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE"},
        )
    return cast(Sprint5AServiceContainer, configured_services)


def provide_sprint5b_services(request: Request) -> Sprint5BServiceContainer:
    configured_services = getattr(request.app.state, "sprint5b_services", None)
    if configured_services is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Human review services are unavailable.",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE"},
        )
    return cast(Sprint5BServiceContainer, configured_services)


def provide_sprint5c_services(request: Request) -> Sprint5CServiceContainer:
    configured_services = getattr(request.app.state, "sprint5c_services", None)
    if configured_services is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Case Resolution services are unavailable.",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE"},
        )
    return cast(Sprint5CServiceContainer, configured_services)


def provide_poc_reporting_services(request: Request) -> PocReportingServiceContainer:
    configured_services = getattr(request.app.state, "poc_reporting_services", None)
    if configured_services is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Review Report and PoC metric services are unavailable.",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE"},
        )
    return cast(PocReportingServiceContainer, configured_services)


def provide_operator_read_services(request: Request) -> OperatorReadServiceContainer:
    configured_services = getattr(request.app.state, "operator_read_services", None)
    if configured_services is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Operator read services are unavailable.",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE"},
        )
    return cast(OperatorReadServiceContainer, configured_services)


async def provide_current_principal(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
) -> AsyncGenerator[Principal, None]:
    """Use Bearer JWT only in the explicit local compatibility profile."""

    authorization_header = request.headers.get("Authorization")
    if authorization_header is not None or credentials is not None:
        if not bool(getattr(request.app.state, "legacy_password_auth_enabled", True)):
            raise AuthenticationRequiredError()
        if (
            credentials is None
            or credentials.scheme.casefold() != "bearer"
            or not credentials.credentials.strip()
        ):
            raise AuthenticationRequiredError()
        services = provide_sprint1_services(request)
        principal = services.resolve_principal.execute(credentials.credentials)
    else:
        oidc_service_value = getattr(request.app.state, "oidc_service", None)
        if not isinstance(oidc_service_value, OidcSessionService):
            raise AuthenticationRequiredError()
        cookie_value = getattr(request.app.state, "oidc_cookie_configuration", None)
        cookie = (
            cookie_value
            if isinstance(cookie_value, OidcCookieConfiguration)
            else OidcCookieConfiguration()
        )
        raw_session_id = request.cookies.get(cookie.name)
        if raw_session_id is None:
            raise AuthenticationRequiredError()
        if request.method.upper() in _SAFE_SESSION_METHODS:
            principal = oidc_service_value.authenticate_without_rotation(
                session_id=raw_session_id
            ).principal
        else:
            csrf_token = request.headers.get("X-CSRF-Token")
            if csrf_token is None:
                raise InvalidOidcCsrfTokenError()
            principal = oidc_service_value.validate_csrf(
                session_id=raw_session_id,
                csrf_token=csrf_token,
            ).principal
    try:
        UUID(principal.tenant_id)
    except ValueError:
        # Legacy unit/local adapters may use readable fake tenant identifiers.
        # The qualified RLS profile never accepts them.
        if provide_settings(request).database_rls_required:
            raise AuthenticationRequiredError() from None
        yield principal
    else:
        with (
            tenant_context(principal.tenant_id),
            case_access_context(
                principal.user_id,
                can_view_all=bool(principal.roles & {Role.ADMIN, Role.QUALITY_VIEWER}),
            ),
        ):
            yield principal


def require_case_access(
    case_id: str,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint1ServiceContainer, Depends(provide_sprint1_services)],
) -> None:
    """Fail as 404 when a direct Case-scoped route is outside personal ownership."""

    services.authorize_case_access.execute(principal=principal, case_id=case_id)
