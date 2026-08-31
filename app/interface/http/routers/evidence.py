"""Tenant-scoped image Evidence upload and metadata endpoints."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Header, Path, Response, UploadFile, status

from app.interface.http.dependencies import (
    provide_current_principal,
    provide_sprint1_services,
    require_case_access,
)
from app.interface.http.schemas import ErrorResponse
from app.interface.http.services import Sprint1ServiceContainer
from app.interface.http.sprint1_schemas import (
    EvidenceAccessUrlResponse,
    EvidenceListResponse,
    EvidenceResponse,
)
from app.platform.errors import StorageUnavailableError
from app.platform.evidence import EvidenceType
from app.platform.tenant import Principal

router = APIRouter(
    prefix="/api/v1/cases",
    tags=["evidence"],
    dependencies=[Depends(require_case_access)],
)

AUTH_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}
EVIDENCE_QUERY_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **AUTH_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
}

CaseId = Annotated[str, Path(min_length=1, max_length=255, description="Opaque Case ID")]
EvidenceId = Annotated[
    str,
    Path(min_length=1, max_length=255, description="Opaque Evidence ID"),
]


@router.post(
    "/{case_id}/evidence",
    response_model=EvidenceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
        **AUTH_ERROR_RESPONSES,
    },
)
def add_image_evidence(
    case_id: CaseId,
    file: Annotated[UploadFile, File(description="JPEG, PNG, or WebP image")],
    evidence_type: Annotated[
        Literal["IMAGE"],
        Form(description="Sprint 1 supports IMAGE evidence only."),
    ],
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint1ServiceContainer, Depends(provide_sprint1_services)],
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=255,
            description="Optional tenant-and-Case-scoped Evidence upload key.",
        ),
    ] = None,
) -> EvidenceResponse:
    evidence = services.add_image_evidence.execute(
        principal=principal,
        case_id=case_id,
        content=file.file,
        filename=file.filename,
        declared_content_type=file.content_type,
        evidence_type=EvidenceType(evidence_type),
        idempotency_key=idempotency_key,
    )
    return EvidenceResponse.from_evidence(evidence)


@router.get(
    "/{case_id}/evidence",
    response_model=EvidenceListResponse,
    responses=EVIDENCE_QUERY_ERROR_RESPONSES,
)
def list_case_evidence(
    case_id: CaseId,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint1ServiceContainer, Depends(provide_sprint1_services)],
) -> EvidenceListResponse:
    evidence = services.list_case_evidence.execute(principal=principal, case_id=case_id)
    return EvidenceListResponse(
        items=tuple(EvidenceResponse.from_evidence(item) for item in evidence)
    )


@router.get(
    "/{case_id}/evidence/{evidence_id}",
    response_model=EvidenceResponse,
    responses=EVIDENCE_QUERY_ERROR_RESPONSES,
)
def get_evidence_metadata(
    case_id: CaseId,
    evidence_id: EvidenceId,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint1ServiceContainer, Depends(provide_sprint1_services)],
) -> EvidenceResponse:
    evidence = services.get_evidence_metadata.execute(
        principal=principal,
        case_id=case_id,
        evidence_id=evidence_id,
    )
    return EvidenceResponse.from_evidence(evidence)


@router.post(
    "/{case_id}/evidence/{evidence_id}/access-url",
    response_model=EvidenceAccessUrlResponse,
    responses={
        **EVIDENCE_QUERY_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
def create_evidence_access_url(
    case_id: CaseId,
    evidence_id: EvidenceId,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint1ServiceContainer, Depends(provide_sprint1_services)],
) -> EvidenceAccessUrlResponse:
    result = services.create_evidence_access_url.execute(
        principal=principal,
        case_id=case_id,
        evidence_id=evidence_id,
    )
    response.headers["Cache-Control"] = "no-store"
    return EvidenceAccessUrlResponse.from_result(result)


@router.get(
    "/{case_id}/evidence/{evidence_id}/content",
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {}, "image/png": {}, "image/webp": {}}},
        **EVIDENCE_QUERY_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
def read_evidence_content(
    case_id: CaseId,
    evidence_id: EvidenceId,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint1ServiceContainer, Depends(provide_sprint1_services)],
) -> Response:
    service = services.read_evidence_content
    if service is None:
        raise StorageUnavailableError()
    result = service.execute(
        principal=principal,
        case_id=case_id,
        evidence_id=evidence_id,
    )
    return Response(
        content=result.content,
        media_type=result.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": "inline",
            "Cross-Origin-Resource-Policy": "same-origin",
            "ETag": f'"{result.sha256}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
