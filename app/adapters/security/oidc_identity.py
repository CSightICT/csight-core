"""Fail-closed IdP-group to authoritative local-account mapping."""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from app.platform.oidc import ValidatedOidcClaims, VerifiedOidcIdentity
from app.platform.tenant import Role
from app.ports.identity import IdentityRepository
from app.ports.oidc import OidcProviderError


@dataclass(frozen=True, slots=True)
class OidcGroupTarget:
    """One external group may admit one tenant and a bounded local role set."""

    tenant_slug: str
    allowed_roles: frozenset[Role]

    def __post_init__(self) -> None:
        if (
            not self.tenant_slug
            or self.tenant_slug != self.tenant_slug.strip().lower()
            or len(self.tenant_slug) > 63
        ):
            raise ValueError("tenant_slug must be a normalized bounded value")
        if not self.allowed_roles:
            raise ValueError("allowed_roles must not be empty")


class ConfiguredOidcIdentityMapper:
    """Use IdP groups only as admission; use the current local account as authority."""

    def __init__(
        self,
        *,
        identities: IdentityRepository,
        group_mappings: dict[str, OidcGroupTarget],
    ) -> None:
        if not group_mappings:
            raise ValueError("group_mappings must not be empty")
        if any(not group or group != group.strip() or len(group) > 512 for group in group_mappings):
            raise ValueError("group mapping keys must be bounded non-blank values")
        self._identities = identities
        self._group_mappings = dict(group_mappings)

    def map_identity(self, claims: ValidatedOidcClaims) -> VerifiedOidcIdentity:
        matches = [
            self._group_mappings[group] for group in claims.groups if group in self._group_mappings
        ]
        if len(matches) != 1 or not claims.email_verified:
            raise OidcProviderError("OIDC identity is not admitted by exactly one group mapping")
        target = matches[0]
        account = self._identities.find_for_login(
            tenant_slug=target.tenant_slug,
            email=claims.email,
        )
        if (
            account is None
            or not account.can_authenticate
            or account.tenant_slug != target.tenant_slug
            or not account.roles.issubset(target.allowed_roles)
            or not hmac.compare_digest(
                account.email.casefold().encode("utf-8"),
                claims.email.casefold().encode("utf-8"),
            )
        ):
            raise OidcProviderError("OIDC identity does not map to an active local account")
        return VerifiedOidcIdentity(
            issuer=claims.issuer,
            subject=claims.subject,
            session_id=claims.session_id,
            tenant_id=account.tenant_id,
            user_id=account.user_id,
            email=account.email,
            email_verified=True,
            nonce=claims.nonce,
        )


__all__ = ["ConfiguredOidcIdentityMapper", "OidcGroupTarget"]
