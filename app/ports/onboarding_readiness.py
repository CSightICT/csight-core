"""Tenant-scoped read port for onboarding readiness facts."""

from datetime import date
from typing import Protocol

from app.platform.onboarding_readiness import OnboardingReadinessFacts


class OnboardingReadinessRepository(Protocol):
    def get_facts(
        self,
        *,
        tenant_id: str,
        configured_signed_actor_ids: tuple[str, ...],
        as_of_date: date,
    ) -> OnboardingReadinessFacts: ...


__all__ = ["OnboardingReadinessRepository"]
