"""Translate framework and application errors into the versioned error envelope."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.bootstrap.logging import get_logger
from app.interface.http.schemas import ErrorDetail, ErrorResponse
from app.platform.analysis import AnalysisProviderError, ProviderTimeoutError

logger = get_logger(__name__)


def _safe_http_message(detail: object) -> str:
    if isinstance(detail, str):
        return detail
    return "The request could not be completed."


def _correlation_id(request: Request) -> str | None:
    value = request.headers.get("X-Correlation-ID")
    if value is None:
        return None
    normalized = value.strip()
    return normalized[:128] or None


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details or {},
            correlation_id=_correlation_id(request),
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


async def _handle_http_exception(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, StarletteHTTPException):
        raise TypeError("HTTP exception handler received an incompatible exception")
    headers = exception.headers or {}
    code = headers.get("X-Error-Code", f"HTTP_{exception.status_code}")
    return _error_response(
        request,
        status_code=exception.status_code,
        code=code,
        message=_safe_http_message(exception.detail),
    )


async def _handle_validation_exception(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, RequestValidationError):
        raise TypeError("validation handler received an incompatible exception")
    sanitized_errors: list[dict[str, object]] = []
    for error in exception.errors():
        sanitized_errors.append(
            {
                "type": str(error.get("type", "validation_error")),
                "location": [str(item) for item in error.get("loc", ())],
                "message": str(error.get("msg", "Invalid input")),
            }
        )
    return _error_response(
        request,
        status_code=422,
        code="REQUEST_VALIDATION_ERROR",
        message="The request is invalid.",
        details={"errors": sanitized_errors},
    )


async def _handle_provider_exception(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, AnalysisProviderError):
        raise TypeError("provider handler received an incompatible exception")
    status_code = 504 if isinstance(exception, ProviderTimeoutError) else 502
    return _error_response(
        request,
        status_code=status_code,
        code=exception.code,
        message="An analysis provider could not complete the request.",
    )


async def _handle_unexpected_exception(request: Request, exception: Exception) -> JSONResponse:
    logger.error(
        "unhandled_http_exception",
        error_type=type(exception).__name__,
        path=request.url.path,
    )
    return _error_response(
        request,
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all HTTP translations in one interface-layer location."""

    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_exception)
    app.add_exception_handler(AnalysisProviderError, _handle_provider_exception)
    app.add_exception_handler(Exception, _handle_unexpected_exception)
