"""Typed service container for immutable reports and tenant PoC metrics."""

from dataclasses import dataclass

from app.application.poc_reporting import (
    CreateCustomerCommunicationSimulation,
    GetCaseReviewReport,
    GetDataAssetSummary,
    GetPocSummary,
    ListCustomerCommunicationSimulations,
)


@dataclass(frozen=True, slots=True)
class PocReportingServiceContainer:
    get_case_review_report: GetCaseReviewReport
    get_poc_summary: GetPocSummary
    create_customer_communication: CreateCustomerCommunicationSimulation
    list_customer_communications: ListCustomerCommunicationSimulations
    get_data_asset_summary: GetDataAssetSummary


__all__ = ["PocReportingServiceContainer"]
