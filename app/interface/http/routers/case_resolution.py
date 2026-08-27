"""Tenant-scoped read-only Case Resolution and Action Intent API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.interface.http.case_resolution_schemas import (
    CaseResolutionEventResponse,
    CaseResolutionEventsResponse,
    CaseResolutionResponse,
    ExternalActionIntentDetailResponse,
    ExternalActionIntentResponse,
    ExternalActionIntentsResponse,
)
from app.interface.http.dependencies import provide_current_principal, provide_sprint5c_services
from app.interface.http.services import Sprint5CServiceContainer
from app.platform.tenant import Principal

router = APIRouter(tags=["case-resolution"])


@router.get("/api/v1/cases/{case_id}/resolution", response_model=CaseResolutionResponse)
def get_case_resolution(
    case_id: UUID,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5CServiceContainer, Depends(provide_sprint5c_services)],
) -> CaseResolutionResponse:
    result = services.get_resolution.execute(principal=principal, case_id=str(case_id))
    response.headers["Cache-Control"] = "no-store"
    return CaseResolutionResponse.from_domain(result)


@router.get(
    "/api/v1/cases/{case_id}/resolution/events",
    response_model=CaseResolutionEventsResponse,
)
def list_case_resolution_events(
    case_id: UUID,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5CServiceContainer, Depends(provide_sprint5c_services)],
) -> CaseResolutionEventsResponse:
    result = services.list_resolution_events.execute(
        principal=principal,
        case_id=str(case_id),
    )
    response.headers["Cache-Control"] = "no-store"
    return CaseResolutionEventsResponse(
        items=tuple(CaseResolutionEventResponse.from_domain(item) for item in result)
    )


@router.get(
    "/api/v1/cases/{case_id}/external-action-intents",
    response_model=ExternalActionIntentsResponse,
)
def list_case_external_action_intents(
    case_id: UUID,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5CServiceContainer, Depends(provide_sprint5c_services)],
) -> ExternalActionIntentsResponse:
    result = services.list_external_action_intents.execute(
        principal=principal,
        case_id=str(case_id),
    )
    response.headers["Cache-Control"] = "no-store"
    return ExternalActionIntentsResponse(
        items=tuple(ExternalActionIntentResponse.from_domain(item) for item in result)
    )


@router.get(
    "/api/v1/external-action-intents/{intent_id}",
    response_model=ExternalActionIntentDetailResponse,
)
def get_external_action_intent(
    intent_id: UUID,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[Sprint5CServiceContainer, Depends(provide_sprint5c_services)],
) -> ExternalActionIntentDetailResponse:
    result = services.get_external_action_intent.execute(
        principal=principal,
        intent_id=str(intent_id),
    )
    response.headers["Cache-Control"] = "no-store"
    return ExternalActionIntentDetailResponse.from_domain(result)


__all__ = ["router"]
