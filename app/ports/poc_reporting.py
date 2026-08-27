"""Read ports for immutable review reports and tenant-scoped PoC metrics."""

from __future__ import annotations

from typing import Protocol

from app.platform.poc_reporting import PocSummary, ReviewReport


class PocReportingRepository(Protocol):
    def get_review_report(self, *, tenant_id: str, case_id: str) -> ReviewReport | None: ...

    def get_poc_summary(self, *, tenant_id: str) -> PocSummary: ...


__all__ = ["PocReportingRepository"]
