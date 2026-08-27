"""Translate framework and application errors into the versioned error envelope."""

import re
from collections.abc import Awaitable, Callable, Mapping
from tempfile import SpooledTemporaryFile
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.bootstrap.logging import bind_log_context, get_logger
from app.interface.http.schemas import ErrorDetail, ErrorResponse
from app.platform.analysis import (
    AnalysisAlreadyTerminalError,
    AnalysisError,
    AnalysisPipelineNotSupportedError,
    AnalysisProviderError,
    AnalysisRunNotFoundError,
    ImageEvidenceRequiredError,
    ProviderTimeoutError,
)
from app.platform.errors import CSightError, FileTooLargeError

logger = get_logger(__name__)

_CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_:-]{0,127}$")
_EVIDENCE_UPLOAD_PATH = re.compile(r"^/api/v1/cases/[^/]+/evidence/?$")
_MULTIPART_OVERHEAD_ALLOWANCE_BYTES = 1024 * 1024
_CSIGHT_STATUS_CODES = {
    "AUTHENTICATION_REQUIRED": 401,
    "INVALID_CREDENTIALS": 401,
    "FORBIDDEN": 403,
    "CASE_NOT_FOUND": 404,
    "EVIDENCE_NOT_FOUND": 404,
    "INVALID_FILE_TYPE": 422,
    "FILE_TOO_LARGE": 413,
    "EMPTY_FILE": 422,
    "INVALID_IMAGE_CONTENT": 422,
    "IMAGE_DIMENSION_LIMIT_EXCEEDED": 422,
    "EVIDENCE_UPLOAD_FAILED": 500,
    "IDEMPOTENCY_KEY_REUSED": 409,
    "VALIDATION_ERROR": 422,
    "STORAGE_UNAVAILABLE": 503,
    "INCONSISTENT_PERSISTENCE_STATE": 500,
    "EMBEDDING_PROVIDER_UNAVAILABLE": 503,
    "POLICY_INDEX_UNAVAILABLE": 503,
    "POLICY_DOCUMENT_VERSION_CONTENT_MISMATCH": 409,
    "RERANKER_PROVIDER_UNAVAILABLE": 503,
    "RERANKER_PROVIDER_INVALID_RESPONSE": 502,
    "RERANKER_PROFILE_UNAVAILABLE": 503,
    "REVIEW_TASK_NOT_FOUND": 404,
    "REVIEW_TASK_VERSION_CONFLICT": 409,
    "REVIEW_TASK_ALREADY_CLAIMED": 409,
    "INVALID_REVIEW_TRANSITION": 409,
    "INVALID_DECISION_BASIS": 422,
    "DUPLICATE_HUMAN_DECISION": 409,
    "REVIEW_PACKET_INTEGRITY_FAILED": 422,
    "CASE_RESOLUTION_NOT_FOUND": 404,
    "EXTERNAL_ACTION_INTENT_NOT_FOUND": 404,
    "CASE_RESOLUTION_INTEGRITY_FAILED": 422,
    "EXTERNAL_ACTION_SIMULATION_FAILED": 422,
    "REVIEW_REPORT_NOT_FOUND": 404,
}


def _safe_http_message(detail: object) -> str:
    if isinstance(detail, str):
        return detail
    return "The request could not be completed."


def _new_correlation_id() -> str:
    return str(uuid4())


def _normalize_correlation_id(value: str | None) -> str:
    if value is not None:
        normalized = value.strip()[:128]
        if _CORRELATION_ID_PATTERN.fullmatch(normalized):
            return normalized
    return _new_correlation_id()


def _correlation_id(request: Request) -> str:
    configured = getattr(request.state, "correlation_id", None)
    if isinstance(configured, str) and configured:
        return configured
    correlation_id = _normalize_correlation_id(request.headers.get("X-Correlation-ID"))
    request.state.correlation_id = correlation_id
    return correlation_id


class EvidenceUploadBodyLimitMiddleware:
    """Bound multipart request bytes before Starlette can spool an oversized upload.

    ``MAX_UPLOAD_BYTES`` remains the exact decoded file limit enforced by the file
    inspector.  The ASGI boundary allows a small, fixed amount of multipart framing
    overhead and caps the entire evidence-upload request before dependency parsing.
    """

    def __init__(self, app: ASGIApp, *, max_upload_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_upload_bytes + _MULTIPART_OVERHEAD_ALLOWANCE_BYTES

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if not self._applies(scope):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_bytes = int(content_length)
            except ValueError:
                declared_bytes = -1
            if declared_bytes > self.max_body_bytes:
                response = _error_response(
                    request,
                    status_code=413,
                    code=FileTooLargeError.code,
                    message=FileTooLargeError.default_message,
                )
                await response(scope, receive, send)
                return

        received_bytes = 0
        with SpooledTemporaryFile(max_size=_MULTIPART_OVERHEAD_ALLOWANCE_BYTES) as buffered:
            while True:
                message = await receive()
                if message.get("type") == "http.disconnect":
                    return
                body = message.get("body", b"")
                if isinstance(body, bytes):
                    received_bytes += len(body)
                    if received_bytes > self.max_body_bytes:
                        response = _error_response(
                            request,
                            status_code=413,
                            code=FileTooLargeError.code,
                            message=FileTooLargeError.default_message,
                        )
                        await response(scope, receive, send)
                        return
                    buffered.write(body)
                if not message.get("more_body", False):
                    break

            buffered.seek(0)

            async def receive_bounded() -> Message:
                body = buffered.read(64 * 1024)
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": buffered.tell() < received_bytes,
                }

            await self.app(scope, receive_bounded, send)

    @staticmethod
    def _applies(scope: Mapping[str, object]) -> bool:
        path = scope.get("path")
        return (
            scope.get("type") == "http"
            and scope.get("method") == "POST"
            and isinstance(path, str)
            and _EVIDENCE_UPLOAD_PATH.fullmatch(path) is not None
        )


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    correlation_id = _correlation_id(request)
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details or {},
            correlation_id=correlation_id,
        )
    )
    response_headers = dict(headers or {})
    response_headers["X-Correlation-ID"] = correlation_id
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers=response_headers,
    )


async def _correlation_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    correlation_id = _normalize_correlation_id(request.headers.get("X-Correlation-ID"))
    request.state.correlation_id = correlation_id
    with bind_log_context(correlation_id=correlation_id):
        response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


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
        headers=headers,
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
        code="VALIDATION_ERROR",
        message="The request is invalid.",
        details={"errors": sanitized_errors},
    )


async def _handle_csight_exception(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, CSightError):
        raise TypeError("CSight error handler received an incompatible exception")
    status_code = _CSIGHT_STATUS_CODES.get(exception.code, 500)
    headers = None
    if exception.code in {"AUTHENTICATION_REQUIRED", "INVALID_CREDENTIALS"}:
        headers = {"WWW-Authenticate": "Bearer"}
    return _error_response(
        request,
        status_code=status_code,
        code=exception.code,
        message=exception.message,
        details=exception.details,
        headers=headers,
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


async def _handle_analysis_exception(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, AnalysisError):
        raise TypeError("analysis handler received an incompatible exception")
    if isinstance(exception, AnalysisRunNotFoundError):
        return _error_response(
            request,
            status_code=404,
            code=exception.code,
            message="The requested analysis run was not found.",
        )
    if isinstance(exception, AnalysisPipelineNotSupportedError):
        return _error_response(
            request,
            status_code=422,
            code=exception.code,
            message="The requested analysis pipeline or version is not supported.",
        )
    if isinstance(exception, ImageEvidenceRequiredError):
        return _error_response(
            request,
            status_code=422,
            code=exception.code,
            message="At least one available image evidence item is required.",
        )
    if isinstance(exception, AnalysisAlreadyTerminalError):
        return _error_response(
            request,
            status_code=409,
            code=exception.code,
            message="The analysis run is already in a terminal state.",
        )
    return _error_response(
        request,
        status_code=500,
        code="ANALYSIS_ERROR",
        message="The analysis request could not be completed.",
    )


async def _handle_unexpected_exception(request: Request, exception: Exception) -> JSONResponse:
    logger.error(
        "unhandled_http_exception",
        error_type=type(exception).__name__,
        path=request.url.path,
        correlation_id=_correlation_id(request),
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
    app.add_exception_handler(CSightError, _handle_csight_exception)
    app.add_exception_handler(AnalysisProviderError, _handle_provider_exception)
    app.add_exception_handler(AnalysisError, _handle_analysis_exception)
    app.add_exception_handler(Exception, _handle_unexpected_exception)


def register_correlation_id_middleware(app: FastAPI) -> None:
    """Assign one safe correlation ID to every request and response."""

    app.middleware("http")(_correlation_id_middleware)


def register_evidence_upload_body_limit_middleware(
    app: FastAPI,
    *,
    max_upload_bytes: int,
) -> None:
    """Install the evidence multipart request cap at the ASGI boundary."""

    app.add_middleware(
        EvidenceUploadBodyLimitMiddleware,
        max_upload_bytes=max_upload_bytes,
    )
