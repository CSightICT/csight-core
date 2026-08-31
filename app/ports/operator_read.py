"""Ports for tenant-scoped operator read projections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.platform.operator_read import (
    OperatorCaseItem,
    OperatorReviewItem,
    QueueCounts,
    QueueSort,
    QueueView,
    WorkflowSnapshot,
)


@dataclass(frozen=True, slots=True)
class CaseQueueSlice:
    items: tuple[OperatorCaseItem, ...]
    counts: QueueCounts
    has_more: bool


@dataclass(frozen=True, slots=True)
class ReviewQueueSlice:
    items: tuple[OperatorReviewItem, ...]
    counts: QueueCounts
    has_more: bool


class OperatorReadRepository(Protocol):
    def list_cases(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        can_view_all: bool,
        view: QueueView,
        sort: QueueSort,
        query: str | None,
        limit: int,
        after_created_at: datetime | None,
        after_id: str | None,
    ) -> CaseQueueSlice: ...

    def list_reviews(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        can_view_all: bool,
        view: QueueView,
        sort: QueueSort,
        query: str | None,
        limit: int,
        after_created_at: datetime | None,
        after_id: str | None,
    ) -> ReviewQueueSlice: ...

    def get_workflow_snapshot(self, *, tenant_id: str, case_id: str) -> WorkflowSnapshot | None: ...


__all__ = ["CaseQueueSlice", "OperatorReadRepository", "ReviewQueueSlice"]
