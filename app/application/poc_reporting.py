"""Authorized read use cases for reports and PoC metrics."""

from __future__ import annotations

from app.platform.poc_reporting import PocSummary, ReviewReport, ReviewReportNotFoundError
from app.platform.tenant import Permission, Principal
from app.ports.poc_reporting import PocReportingRepository


class GetCaseReviewReport:
    def __init__(self, repository: PocReportingRepository) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, case_id: str) -> ReviewReport:
        principal.require(Permission.HUMAN_REVIEW_READ)
        report = self._repository.get_review_report(
            tenant_id=principal.tenant_id,
            case_id=case_id,
        )
        if report is None:
            raise ReviewReportNotFoundError()
        return report


class GetPocSummary:
    def __init__(self, repository: PocReportingRepository) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal) -> PocSummary:
        principal.require(Permission.HUMAN_REVIEW_READ)
        return self._repository.get_poc_summary(tenant_id=principal.tenant_id)


__all__ = ["GetCaseReviewReport", "GetPocSummary"]
