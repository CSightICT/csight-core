"""Unauthenticated HTTP boundary guarded by deployment-owned Ed25519 keys."""

import hashlib

from fastapi import APIRouter, Request, Response, status
from pydantic import ValidationError

from app.application.cases import CreateCaseCommand, CreateSignedIntakeCaseCommand
from app.interface.http.schemas import ErrorResponse
from app.interface.http.signed_intake_schemas import (
    SignedIntakeCaseRequest,
    SignedIntakeCaseResponse,
)
from app.interface.http.signed_intake_services import SignedIntakeServiceContainer
from app.platform.errors import FileTooLargeError
from app.platform.errors import ValidationError as CSightValidationError
from app.platform.signed_intake import SignedIntakeAuthenticationError, SignedIntakeProof
from app.platform.tenant_context import tenant_context

_KEY_ID_HEADER = "X-CSight-Intake-Key-Id"
_EVENT_ID_HEADER = "X-CSight-Intake-Event-Id"
_TIMESTAMP_HEADER = "X-CSight-Intake-Timestamp"
_SIGNATURE_HEADER = "X-CSight-Intake-Signature"


def create_signed_intake_router(services: SignedIntakeServiceContainer) -> APIRouter:
    router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

    @router.post(
        "/cases",
        response_model=SignedIntakeCaseResponse,
        status_code=status.HTTP_201_CREATED,
        responses={
            status.HTTP_200_OK: {
                "model": SignedIntakeCaseResponse,
                "description": "An authenticated replay of the source event.",
            },
            status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
            status.HTTP_409_CONFLICT: {"model": ErrorResponse},
            status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorResponse},
            status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        },
    )
    async def create_signed_case(request: Request, response: Response) -> SignedIntakeCaseResponse:
        raw_body = await _read_bounded_body(
            request=request,
            max_body_bytes=services.max_body_bytes,
        )

        proof = _proof_from_request(request=request, raw_body=raw_body)
        authenticated = services.authenticate.execute(proof)
        try:
            body = SignedIntakeCaseRequest.model_validate_json(raw_body)
        except ValidationError as error:
            raise CSightValidationError(
                details={"errors": _sanitized_validation_errors(error)}
            ) from None

        command = CreateSignedIntakeCaseCommand(
            source_event_id=proof.event_id,
            case=CreateCaseCommand(
                order_ref=body.order_ref,
                product_ref=body.product_ref,
                customer_message=body.customer_message,
                requested_action=body.requested_action,
                attributes=body.attributes,
            ),
        )
        with tenant_context(authenticated.source.tenant_id):
            result = services.create_case.execute(
                authenticated=authenticated,
                command=command,
            )
        response.headers["Cache-Control"] = "no-store"
        if result.replayed:
            response.status_code = status.HTTP_200_OK
        return SignedIntakeCaseResponse.from_result(
            source_event_id=proof.event_id,
            result=result,
        )

    _ = create_signed_case  # FastAPI decorator registration is the intended use.
    return router


async def _read_bounded_body(*, request: Request, max_body_bytes: int) -> bytes:
    """Read at most the configured bytes for both fixed and chunked requests."""

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_bytes = int(content_length)
        except ValueError:
            declared_bytes = -1
        if declared_bytes > max_body_bytes:
            raise FileTooLargeError()

    body = bytearray()
    async for chunk in request.stream():
        if len(chunk) > max_body_bytes - len(body):
            raise FileTooLargeError()
        body.extend(chunk)
    return bytes(body)


def _sanitized_validation_errors(error: ValidationError) -> list[dict[str, object]]:
    safe_fields = {
        "schema_version",
        "order_ref",
        "product_ref",
        "customer_message",
        "requested_action",
        "attributes",
    }
    sanitized: list[dict[str, object]] = []
    for item in error.errors():
        location = ["body"]
        field = next((part for part in item.get("loc", ()) if part in safe_fields), None)
        if isinstance(field, str):
            location.append(field)
        error_type = str(item.get("type", "validation_error"))
        if not error_type.replace("_", "").replace(".", "").isalnum():
            error_type = "validation_error"
        sanitized.append(
            {
                "type": error_type[:64],
                "location": location,
                "message": "Invalid value.",
            }
        )
    return sanitized


def _proof_from_request(*, request: Request, raw_body: bytes) -> SignedIntakeProof:
    try:
        timestamp = int(request.headers[_TIMESTAMP_HEADER])
        return SignedIntakeProof(
            method=request.method.upper(),
            path=request.url.path,
            key_id=request.headers[_KEY_ID_HEADER],
            event_id=request.headers[_EVENT_ID_HEADER],
            timestamp=timestamp,
            body_sha256=hashlib.sha256(raw_body).hexdigest(),
            signature_base64=request.headers[_SIGNATURE_HEADER],
        )
    except (KeyError, TypeError, ValueError, ValidationError):
        raise SignedIntakeAuthenticationError() from None


__all__ = ["create_signed_intake_router"]
