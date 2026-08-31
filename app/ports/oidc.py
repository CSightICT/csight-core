"""Ports for OIDC providers, login transactions, and hashed server sessions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from app.platform.oidc import (
    OidcAuthorizationRequest,
    OidcCodeExchangeRequest,
    OidcLoginTransaction,
    OidcLogoutRevocationResult,
    OidcSession,
    ValidatedOidcClaims,
    ValidatedOidcLogoutToken,
    VerifiedOidcIdentity,
)


class OidcProviderError(RuntimeError):
    """Safe provider boundary error; response bodies and tokens must not be attached."""


class OidcProviderTemporarilyUnavailableError(OidcProviderError):
    """The provider backchannel could not complete a bounded request."""


@runtime_checkable
class SecureTokenGenerator(Protocol):
    def token_urlsafe(self, *, entropy_bytes: int) -> str: ...


@runtime_checkable
class OidcProvider(Protocol):
    @property
    def provider_key(self) -> str: ...

    def authorization_url(self, request: OidcAuthorizationRequest) -> str: ...

    def exchange_code(self, request: OidcCodeExchangeRequest) -> VerifiedOidcIdentity: ...

    def validate_logout_token(self, logout_token: str) -> ValidatedOidcLogoutToken: ...


@runtime_checkable
class OidcLoginTransactionRepository(Protocol):
    def add(self, value: OidcLoginTransaction) -> None: ...

    def consume(self, *, state_hash: str, now: datetime) -> OidcLoginTransaction | None: ...


@runtime_checkable
class OidcSessionRepository(Protocol):
    def add(self, value: OidcSession) -> None: ...

    def get_and_touch(
        self,
        *,
        session_id_hash: str,
        now: datetime,
        idle_timeout: timedelta,
    ) -> OidcSession | None: ...

    def validate_csrf_and_touch(
        self,
        *,
        session_id_hash: str,
        csrf_token_hash: str,
        now: datetime,
        idle_timeout: timedelta,
    ) -> OidcSession | None: ...

    def rotate_csrf_and_touch(
        self,
        *,
        session_id_hash: str,
        new_csrf_token_hash: str,
        now: datetime,
        idle_timeout: timedelta,
    ) -> OidcSession | None: ...

    def revoke(
        self,
        *,
        session_id_hash: str,
        now: datetime,
        reason: str,
    ) -> bool: ...

    def revoke_by_provider_logout(
        self,
        *,
        logout: ValidatedOidcLogoutToken,
        now: datetime,
    ) -> OidcLogoutRevocationResult: ...


class OidcBackchannel(Protocol):
    """Injected network/JWKS boundary used by the standard provider adapter.

    Implementations must validate TLS, signature, issuer, audience, expiry and nonce
    before returning a mapped identity. They must enforce bounded timeouts and must
    not log authorization codes, tokens, the PKCE verifier, or provider response bodies.
    """

    def exchange_and_validate(
        self,
        *,
        token_endpoint: str,
        jwks_uri: str,
        issuer: str,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str,
        allowed_algorithms: tuple[str, ...],
        groups_claim: str,
        code: str,
        pkce_verifier: str,
        expected_nonce: str,
    ) -> VerifiedOidcIdentity: ...

    def validate_logout_token(
        self,
        *,
        raw_logout_token: str,
        jwks_uri: str,
        issuer: str,
        client_id: str,
        allowed_algorithms: tuple[str, ...],
    ) -> ValidatedOidcLogoutToken: ...


@runtime_checkable
class OidcClaimsIdentityMapper(Protocol):
    """Map verified external claims to one current, active local account."""

    def map_identity(self, claims: ValidatedOidcClaims) -> VerifiedOidcIdentity: ...
