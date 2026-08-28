"""Read ports for immutable review reports and tenant-scoped PoC metrics."""

from __future__ import annotations

from typing import Protocol

from app.platform.poc_reporting import (
    CustomerCommunicationSimulation,
    DataAssetSummary,
    PocSummary,
    ReviewReport,
)


class PocReportingRepository(Protocol):
    def get_review_report(self, *, tenant_id: str, case_id: str) -> ReviewReport | None: ...

    def get_poc_summary(self, *, tenant_id: str) -> PocSummary: ...

    def create_customer_communication(
        self, *, tenant_id: str, case_id: str, created_by: str
    ) -> CustomerCommunicationSimulation: ...

    def list_customer_communications(
        self, *, tenant_id: str, case_id: str
    ) -> tuple[CustomerCommunicationSimulation, ...]: ...

    def get_data_asset_summary(self, *, tenant_id: str) -> DataAssetSummary: ...


__all__ = ["PocReportingRepository"]
