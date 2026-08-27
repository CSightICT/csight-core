"""Typed service container for immutable reports and tenant PoC metrics."""

from dataclasses import dataclass

from app.application.poc_reporting import GetCaseReviewReport, GetPocSummary


@dataclass(frozen=True, slots=True)
class PocReportingServiceContainer:
    get_case_review_report: GetCaseReviewReport
    get_poc_summary: GetPocSummary


__all__ = ["PocReportingServiceContainer"]
