"""FastAPI router factory for an explicitly injected OIDC session service."""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Form, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import RedirectResponse

from app.application.oidc import (
    CompleteOidcLoginCommand,
    OidcSessionExpiryInfo,
    OidcSessionService,
    StartOidcLoginCommand,
)
from app.platform.oidc import (
    InvalidOidcCallbackError,
    InvalidOidcCsrfTokenError,
    InvalidOidcSessionError,
    OidcPersistenceConflictError,
    OidcProviderUnavailableError,
)
from app.platform.tenant import Principal, Role

_COOKIE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True, slots=True)
class OidcCookieConfiguration:
    """Host-only HttpOnly cookie containing only the raw opaque session ID."""

    name: str = "csight_session"
    login_state_name: str = "csight_oidc_state"
    secure: bool = True
    same_site: Literal["lax", "strict"] = "lax"
    path: str = "/"

    def __post_init__(self) -> None:
        if (
            _COOKIE_NAME_PATTERN.fullmatch(self.name) is None
            or _COOKIE_NAME_PATTERN.fullmatch(self.login_state_name) is None
            or self.name == self.login_state_name
        ):
            raise ValueError("OIDC cookie name is invalid")
        if not self.path.startswith("/") or "\\" in self.path:
            raise ValueError("OIDC cookie path must be an absolute local path")


class OidcPrincipalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str
    tenant_id: str
    email: str
    display_name: str
    roles: tuple[Role, ...]

    @classmethod
    def from_principal(cls, principal: Principal) -> OidcPrincipalResponse:
        return cls(
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
            email=principal.email,
            display_name=principal.display_name,
            roles=tuple(sorted(principal.roles, key=lambda role: role.value)),
        )


class OidcSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    authenticated: Literal[True] = True
    csrf_token: str = Field(repr=False)
    principal: OidcPrincipalResponse
    expiry: OidcSessionExpiryInfo


class AuthCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    oidc_enabled: bool
    legacy_password_enabled: bool


def create_auth_capabilities_router(
    *,
    oidc_enabled: bool,
    legacy_password_enabled: bool,
) -> APIRouter:
    """Expose only the login methods that this process can actually serve."""

    router = APIRouter(prefix="/auth", tags=["authentication"])

    @router.get("/capabilities", response_model=AuthCapabilitiesResponse)
    def _get_auth_capabilities(response: Response) -> AuthCapabilitiesResponse:
        _no_store(response)
        return AuthCapabilitiesResponse(
            oidc_enabled=oidc_enabled,
            legacy_password_enabled=legacy_password_enabled,
        )

    _registered_routes = (_get_auth_capabilities,)
    return router


def create_oidc_router(
    *,
    service: OidcSessionService,
    cookie: OidcCookieConfiguration | None = None,
) -> APIRouter:
    """Build a router without importing global settings, sessions, or dependencies."""

    cookie_configuration = cookie or OidcCookieConfiguration()
    router = APIRouter(prefix="/auth", tags=["authentication"])

    @router.get(
        "/oidc/login",
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    def _start_oidc_login(
        return_path: Annotated[str, Query(min_length=1, max_length=2048)],
    ) -> Response:
        try:
            result = service.start_login(StartOidcLoginCommand(return_path=return_path))
        except (OidcProviderUnavailableError, OidcPersistenceConflictError) as error:
            _raise_temporarily_unavailable(error)
        redirect = RedirectResponse(
            url=result.authorization_url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )
        # `state` protects the provider response only when it is also bound to
        # the browser that initiated login.  This short-lived, callback-scoped
        # cookie prevents a valid attacker-started callback from replacing the
        # victim's authenticated CSight session.
        redirect.set_cookie(
            key=cookie_configuration.login_state_name,
            value=result.browser_state,
            max_age=10 * 60,
            path="/auth/oidc/callback",
            secure=cookie_configuration.secure,
            httponly=True,
            samesite="lax",
        )
        _no_store(redirect)
        return redirect

    @router.get(
        "/oidc/callback",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    def _complete_oidc_login(
        request: Request,
        code: Annotated[str, Query(min_length=1, max_length=4096)],
        state_value: Annotated[
            str,
            Query(alias="state", min_length=32, max_length=512),
        ],
    ) -> Response:
        browser_state = request.cookies.get(cookie_configuration.login_state_name)
        if browser_state is None or not hmac.compare_digest(browser_state, state_value):
            raise InvalidOidcCallbackError()
        try:
            result = service.complete_login(CompleteOidcLoginCommand(code=code, state=state_value))
        except (OidcProviderUnavailableError, OidcPersistenceConflictError) as error:
            _raise_temporarily_unavailable(error)
        response = RedirectResponse(
            url=result.return_path,
            status_code=status.HTTP_303_SEE_OTHER,
        )
        response.set_cookie(
            key=cookie_configuration.name,
            value=result.session_id,
            expires=result.expiry.absolute_expires_at,
            path=cookie_configuration.path,
            secure=cookie_configuration.secure,
            httponly=True,
            samesite=cookie_configuration.same_site,
        )
        response.delete_cookie(
            key=cookie_configuration.login_state_name,
            path="/auth/oidc/callback",
            secure=cookie_configuration.secure,
            httponly=True,
            samesite="lax",
        )
        _no_store(response)
        return response

    @router.get(
        "/session",
        response_model=OidcSessionResponse,
        status_code=status.HTTP_200_OK,
    )
    def _get_oidc_session(request: Request, response: Response) -> OidcSessionResponse:
        raw_session_id = request.cookies.get(cookie_configuration.name)
        if raw_session_id is None:
            raise InvalidOidcSessionError()
        result = service.resolve_session(session_id=raw_session_id)
        _no_store(response)
        return OidcSessionResponse(
            csrf_token=result.csrf_token,
            principal=OidcPrincipalResponse.from_principal(result.principal),
            expiry=result.expiry,
        )

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    def _logout_oidc_session(
        request: Request,
        response: Response,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> Response:
        raw_session_id = request.cookies.get(cookie_configuration.name)
        if raw_session_id is None:
            raise InvalidOidcSessionError()
        if csrf_token is None:
            raise InvalidOidcCsrfTokenError()
        service.logout(session_id=raw_session_id, csrf_token=csrf_token)
        response.delete_cookie(
            key=cookie_configuration.name,
            path=cookie_configuration.path,
            secure=cookie_configuration.secure,
            httponly=True,
            samesite=cookie_configuration.same_site,
        )
        _no_store(response)
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @router.post(
        "/oidc/backchannel-logout",
        status_code=status.HTTP_200_OK,
        response_class=Response,
    )
    def _backchannel_logout(
        logout_token: Annotated[
            str,
            Form(min_length=1, max_length=65536),
        ],
    ) -> Response:
        try:
            service.backchannel_logout(logout_token=logout_token)
        except (OidcProviderUnavailableError, OidcPersistenceConflictError) as error:
            _raise_temporarily_unavailable(error)
        response = Response(status_code=status.HTTP_200_OK)
        _no_store(response)
        return response

    _registered_routes = (
        _start_oidc_login,
        _complete_oidc_login,
        _get_oidc_session,
        _logout_oidc_session,
        _backchannel_logout,
    )
    return router


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _raise_temporarily_unavailable(
    error: OidcProviderUnavailableError | OidcPersistenceConflictError,
) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=error.message,
        headers={"X-Error-Code": error.code},
    ) from error
