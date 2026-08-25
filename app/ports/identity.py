"""Tenant-scoped user identity persistence boundary."""

from typing import Protocol, runtime_checkable

from app.platform.tenant import UserAccount


@runtime_checkable
class IdentityRepository(Protocol):
    """Load current authentication snapshots without exposing ORM entities."""

    def find_for_login(self, *, tenant_slug: str, email: str) -> UserAccount | None:
        """Find a user and tenant by normalized login identifiers, including inactive ones."""
        ...

    def get_by_tenant_and_subject(
        self,
        *,
        tenant_id: str,
        subject: str,
    ) -> UserAccount | None:
        """Reload the current user, tenant state, and roles for an access-token subject."""
        ...
