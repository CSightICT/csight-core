"""Tenant-scoped immutable Review Report and PoC KPI reads."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.interface.http.dependencies import (
    provide_current_principal,
    provide_poc_reporting_services,
)
from app.interface.http.poc_reporting_schemas import (
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


__all__ = ["router"]
