"""Admin-only application services for aggregate operational reads."""

from __future__ import annotations

from datetime import timedelta

from app.platform.errors import ForbiddenError, ValidationError
from app.platform.operations import (
    OperationalFailurePage,
    OperationalFailureResolutionResult,
    OperationsFailures,
    OperationsOverview,
)
from app.platform.tenant import Principal, Role
from app.ports.operations import OperationalFailureRepository, OperationsReadRepository
from app.ports.runtime import Clock

_DEFAULT_STALLED_AFTER = timedelta(minutes=5)
_MAX_FAILURE_LOOKBACK_HOURS = 24 * 7


class GetOperationsOverview:
    def __init__(
        self,
        repository: OperationsReadRepository,
        clock: Clock,
        *,
        stalled_after: timedelta = _DEFAULT_STALLED_AFTER,
    ) -> None:
        if stalled_after <= timedelta(0):
            raise ValueError("stalled_after must be positive")
        self._repository = repository
        self._clock = clock
        self._stalled_after = stalled_after

    def execute(self, *, principal: Principal) -> OperationsOverview:
        _require_admin(principal)
        now = self._clock.now()
        return self._repository.get_overview(
            tenant_id=principal.tenant_id,
            now=now,
            stalled_before=now - self._stalled_after,
        )


class GetOperationsFailures:
    def __init__(
        self,
        repository: OperationsReadRepository,
        clock: Clock,
        *,
        stalled_after: timedelta = _DEFAULT_STALLED_AFTER,
    ) -> None:
        if stalled_after <= timedelta(0):
            raise ValueError("stalled_after must be positive")
        self._repository = repository
        self._clock = clock
        self._stalled_after = stalled_after

    def execute(
        self,
        *,
        principal: Principal,
        lookback_hours: int = 24,
    ) -> OperationsFailures:
        _require_admin(principal)
        if not 1 <= lookback_hours <= _MAX_FAILURE_LOOKBACK_HOURS:
            raise ValidationError("Operations failure lookback must be between 1 and 168 hours.")
        now = self._clock.now()
        return self._repository.get_failures(
            tenant_id=principal.tenant_id,
            now=now,
            since=now - timedelta(hours=lookback_hours),
            stalled_before=now - self._stalled_after,
        )


class ListOperationalFailures:
    def __init__(self, repository: OperationalFailureRepository, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    def execute(
        self,
        *,
        principal: Principal,
        lookback_hours: int = 24,
        limit: int = 50,
        cursor: str | None = None,
    ) -> OperationalFailurePage:
        _require_admin(principal)
        if not 1 <= lookback_hours <= _MAX_FAILURE_LOOKBACK_HOURS:
            raise ValidationError("Operations failure lookback must be between 1 and 168 hours.")
        if not 1 <= limit <= 100:
            raise ValidationError("Operations failure page size must be between 1 and 100.")
        now = self._clock.now()
        return self._repository.list_failures(
            tenant_id=principal.tenant_id,
            since=now - timedelta(hours=lookback_hours),
            limit=limit,
            cursor=cursor,
        )


class ReplayOperationalFailure:
    def __init__(self, repository: OperationalFailureRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        principal: Principal,
        failure_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> OperationalFailureResolutionResult:
        _require_admin(principal)
        _validate_mutation_input(idempotency_key=idempotency_key, correlation_id=correlation_id)
        return self._repository.replay_failure(
            tenant_id=principal.tenant_id,
            failure_id=failure_id,
            actor_id=principal.user_id,
            idempotency_key=idempotency_key.strip(),
            correlation_id=correlation_id.strip(),
        )


class CancelOperationalFailure:
    def __init__(self, repository: OperationalFailureRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        principal: Principal,
        failure_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> OperationalFailureResolutionResult:
        _require_admin(principal)
        _validate_mutation_input(idempotency_key=idempotency_key, correlation_id=correlation_id)
        return self._repository.cancel_failure(
            tenant_id=principal.tenant_id,
            failure_id=failure_id,
            actor_id=principal.user_id,
            idempotency_key=idempotency_key.strip(),
            correlation_id=correlation_id.strip(),
        )


def _require_admin(principal: Principal) -> None:
    if Role.ADMIN not in principal.roles:
        raise ForbiddenError()


def _validate_mutation_input(*, idempotency_key: str, correlation_id: str) -> None:
    if not 1 <= len(idempotency_key.strip()) <= 255:
        raise ValidationError("Idempotency-Key must contain between 1 and 255 characters.")
    if not 1 <= len(correlation_id.strip()) <= 128:
        raise ValidationError("Correlation identifier is invalid.")


__all__ = [
    "CancelOperationalFailure",
    "GetOperationsFailures",
    "GetOperationsOverview",
    "ListOperationalFailures",
    "ReplayOperationalFailure",
]
