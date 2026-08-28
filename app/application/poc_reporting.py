"""Authorized read use cases for reports and PoC metrics."""

from __future__ import annotations

from app.platform.poc_reporting import (
    CustomerCommunicationSimulation,
    DataAssetSummary,
    PocSummary,
    ReviewReport,
    ReviewReportNotFoundError,
)
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


class CreateCustomerCommunicationSimulation:
    def __init__(self, repository: PocReportingRepository) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal, case_id: str) -> CustomerCommunicationSimulation:
        principal.require(Permission.HUMAN_REVIEW_ACTION)
        return self._repository.create_customer_communication(
            tenant_id=principal.tenant_id,
            case_id=case_id,
            created_by=principal.user_id,
        )


class ListCustomerCommunicationSimulations:
    def __init__(self, repository: PocReportingRepository) -> None:
        self._repository = repository

    def execute(
        self, *, principal: Principal, case_id: str
    ) -> tuple[CustomerCommunicationSimulation, ...]:
        principal.require(Permission.HUMAN_REVIEW_READ)
        return self._repository.list_customer_communications(
            tenant_id=principal.tenant_id,
            case_id=case_id,
        )


class GetDataAssetSummary:
    def __init__(self, repository: PocReportingRepository) -> None:
        self._repository = repository

    def execute(self, *, principal: Principal) -> DataAssetSummary:
        principal.require(Permission.HUMAN_REVIEW_READ)
        return self._repository.get_data_asset_summary(tenant_id=principal.tenant_id)


__all__ = [
    "CreateCustomerCommunicationSimulation",
    "GetCaseReviewReport",
    "GetDataAssetSummary",
    "GetPocSummary",
    "ListCustomerCommunicationSimulations",
]
