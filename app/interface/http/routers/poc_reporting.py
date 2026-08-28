"""Tenant-scoped immutable Review Report and PoC KPI reads."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.interface.http.dependencies import (
    provide_current_principal,
    provide_poc_reporting_services,
)
from app.interface.http.poc_reporting_schemas import (
    CustomerCommunicationResponse,
    DataAssetSummaryResponse,
    PocSummaryResponse,
    ReviewReportResponse,
)
from app.interface.http.poc_reporting_services import PocReportingServiceContainer
from app.platform.tenant import Principal

router = APIRouter(tags=["poc-reporting"])


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.get(
    "/api/v1/cases/{case_id}/review-report",
    response_model=ReviewReportResponse,
)
def get_case_review_report(
    case_id: UUID,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        PocReportingServiceContainer,
        Depends(provide_poc_reporting_services),
    ],
) -> ReviewReportResponse:
    report = services.get_case_review_report.execute(
        principal=principal,
        case_id=str(case_id),
    )
    _no_store(response)
    return ReviewReportResponse.from_report(report)


@router.get("/api/v1/metrics/poc-summary", response_model=PocSummaryResponse)
def get_poc_summary(
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        PocReportingServiceContainer,
        Depends(provide_poc_reporting_services),
    ],
) -> PocSummaryResponse:
    summary = services.get_poc_summary.execute(principal=principal)
    _no_store(response)
    return PocSummaryResponse.from_summary(summary)


@router.post(
    "/api/v1/cases/{case_id}/communication-simulations",
    response_model=CustomerCommunicationResponse,
)
def create_customer_communication_simulation(
    case_id: UUID,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        PocReportingServiceContainer,
        Depends(provide_poc_reporting_services),
    ],
) -> CustomerCommunicationResponse:
    simulation = services.create_customer_communication.execute(
        principal=principal,
        case_id=str(case_id),
    )
    _no_store(response)
    return CustomerCommunicationResponse.from_simulation(simulation)


@router.get(
    "/api/v1/cases/{case_id}/communication-simulations",
    response_model=list[CustomerCommunicationResponse],
)
def list_customer_communication_simulations(
    case_id: UUID,
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        PocReportingServiceContainer,
        Depends(provide_poc_reporting_services),
    ],
) -> list[CustomerCommunicationResponse]:
    simulations = services.list_customer_communications.execute(
        principal=principal,
        case_id=str(case_id),
    )
    _no_store(response)
    return [CustomerCommunicationResponse.from_simulation(item) for item in simulations]


@router.get("/api/v1/data-assets/summary", response_model=DataAssetSummaryResponse)
def get_data_asset_summary(
    response: Response,
    principal: Annotated[Principal, Depends(provide_current_principal)],
    services: Annotated[
        PocReportingServiceContainer,
        Depends(provide_poc_reporting_services),
    ],
) -> DataAssetSummaryResponse:
    summary = services.get_data_asset_summary.execute(principal=principal)
    _no_store(response)
    return DataAssetSummaryResponse.from_summary(summary)


__all__ = ["router"]
