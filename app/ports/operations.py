"""Read-only operations visibility port."""

from datetime import datetime
from typing import Protocol

from app.platform.operations import (
    OperationalFailurePage,
    OperationalFailureResolutionResult,
    OperationsFailures,
    OperationsOverview,
)


class OperationsReadRepository(Protocol):
    def get_overview(
        self,
        *,
        tenant_id: str,
        now: datetime,
        stalled_before: datetime,
    ) -> OperationsOverview: ...

    def get_failures(
        self,
        *,
        tenant_id: str,
        now: datetime,
        since: datetime,
        stalled_before: datetime,
    ) -> OperationsFailures: ...


class OperationalFailureRepository(Protocol):
    def list_failures(
        self,
        *,
        tenant_id: str,
        since: datetime,
        limit: int,
        cursor: str | None,
    ) -> OperationalFailurePage: ...

    def replay_failure(
        self,
        *,
        tenant_id: str,
        failure_id: str,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> OperationalFailureResolutionResult: ...

    def cancel_failure(
        self,
        *,
        tenant_id: str,
        failure_id: str,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> OperationalFailureResolutionResult: ...


__all__ = ["OperationalFailureRepository", "OperationsReadRepository"]
