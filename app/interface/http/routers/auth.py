"""Local/PoC authentication endpoints for the Sprint 1 tenant boundary."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.application.auth import LoginCommand
from app.interface.http.dependencies import (
    provide_current_principal,
    provide_sprint1_services,
)
from app.interface.http.schemas import ErrorResponse
from app.interface.http.services import Sprint1ServiceContainer
from app.interface.http.sprint1_schemas import (
    CurrentUserResponse,
    LoginRequest,
    TokenResponse,
)
from app.platform.tenant import Principal

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
legacy_password_router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@legacy_password_router.post(
    "/token",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
def issue_access_token(
    request: LoginRequest,
    response: Response,
    services: Annotated[Sprint1ServiceContainer, Depends(provide_sprint1_services)],
) -> TokenResponse:
    result = services.authenticate_user.execute(
        LoginCommand(
            tenant_slug=request.tenant_slug,
            email=request.email,
            password=request.password,
        )
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return TokenResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        expires_in=result.expires_in,
    )


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
def get_current_user(
    principal: Annotated[Principal, Depends(provide_current_principal)],
) -> CurrentUserResponse:
    return CurrentUserResponse.from_principal(principal)
