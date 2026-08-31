"""Technology-neutral OIDC login and server-side session contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.platform.errors import (
    AuthenticationRequiredError,
    CSightError,
    ForbiddenError,
    ValidationError,
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class InvalidOidcCallbackError(AuthenticationRequiredError):
    """Reject a missing, expired, replayed, or otherwise invalid callback."""


class InvalidOidcSessionError(AuthenticationRequiredError):
    """Reject an unknown, expired, revoked, or inactive-user session."""


class InvalidOidcCsrfTokenError(ForbiddenError):
    """Reject a state-changing request whose CSRF proof is absent or invalid."""


class InvalidOidcLogoutTokenError(ValidationError):
    """Reject a malformed, unsigned, replay-conflicting, or unrelated logout token."""

    code = "INVALID_OIDC_LOGOUT_TOKEN"
    default_message = "The OIDC logout token is invalid."


class InvalidOidcReturnPathError(ValidationError):
    """Reject a redirect target outside the configured local path allowlist."""


class OidcProviderUnavailableError(CSightError):
    code = "OIDC_PROVIDER_UNAVAILABLE"
    default_message = "The identity provider is temporarily unavailable."


class OidcPersistenceConflictError(CSightError):
    code = "OIDC_PERSISTENCE_CONFLICT"
    default_message = "The authentication state could not be persisted."


def _utc(name: str, value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


class OidcLoginTransaction(BaseModel):
    """One short-lived authorization transaction; browser state is stored hashed."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    transaction_id: str = Field(min_length=1, max_length=255)
    provider_key: str = Field(min_length=1, max_length=64)
    state_hash: str = Field(pattern=SHA256_PATTERN)
    nonce: str = Field(min_length=32, max_length=512, repr=False)
    pkce_verifier: str = Field(min_length=43, max_length=128, repr=False)
    return_path: str = Field(min_length=1, max_length=2048)
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_timeline(self) -> OidcLoginTransaction:
        created_at = _utc("created_at", self.created_at)
        expires_at = _utc("expires_at", self.expires_at)
        consumed_at = (
            _utc("consumed_at", self.consumed_at) if self.consumed_at is not None else None
        )
        if expires_at <= created_at:
            raise ValueError("expires_at must be after created_at")
        if consumed_at is not None and not created_at <= consumed_at <= expires_at:
            raise ValueError("consumed_at must be within the transaction lifetime")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "consumed_at", consumed_at)
        return self


class OidcSession(BaseModel):
    """Server-side session snapshot containing hashes, never browser bearer secrets."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    session_record_id: str = Field(min_length=1, max_length=255)
    session_id_hash: str = Field(pattern=SHA256_PATTERN, repr=False)
    csrf_token_hash: str = Field(pattern=SHA256_PATTERN, repr=False)
    tenant_id: str = Field(min_length=1, max_length=255)
    user_id: str = Field(min_length=1, max_length=255)
    provider_issuer: str = Field(min_length=1, max_length=2048)
    provider_subject: str = Field(min_length=1, max_length=512)
    provider_session_id: str | None = Field(default=None, min_length=1, max_length=512)
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    revoked_at: datetime | None = None
    revocation_reason: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_timeline(self) -> OidcSession:
        created_at = _utc("created_at", self.created_at)
        last_seen_at = _utc("last_seen_at", self.last_seen_at)
        idle_expires_at = _utc("idle_expires_at", self.idle_expires_at)
        absolute_expires_at = _utc("absolute_expires_at", self.absolute_expires_at)
        revoked_at = _utc("revoked_at", self.revoked_at) if self.revoked_at is not None else None
        if not created_at <= last_seen_at < absolute_expires_at:
            raise ValueError("last_seen_at must be within the absolute session lifetime")
        if not last_seen_at < idle_expires_at <= absolute_expires_at:
            raise ValueError(
                "idle_expires_at must be after last_seen_at and within the absolute limit"
            )
        if (revoked_at is None) != (self.revocation_reason is None):
            raise ValueError("revoked_at and revocation_reason must be set together")
        if revoked_at is not None and revoked_at < created_at:
            raise ValueError("revoked_at must not predate the session")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "last_seen_at", last_seen_at)
        object.__setattr__(self, "idle_expires_at", idle_expires_at)
        object.__setattr__(self, "absolute_expires_at", absolute_expires_at)
        object.__setattr__(self, "revoked_at", revoked_at)
        return self

    @property
    def effective_expires_at(self) -> datetime:
        return min(self.idle_expires_at, self.absolute_expires_at)

    def is_active_at(self, now: datetime) -> bool:
        checked_at = _utc("now", now)
        return self.revoked_at is None and checked_at < self.effective_expires_at


class OidcAuthorizationRequest(BaseModel):
    """Values required to construct an Authorization Code + PKCE redirect."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: str = Field(min_length=32, max_length=512, repr=False)
    nonce: str = Field(min_length=32, max_length=512, repr=False)
    code_challenge: str = Field(min_length=43, max_length=128, repr=False)


class OidcCodeExchangeRequest(BaseModel):
    """One-time server-side inputs for the provider token endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=4096, repr=False)
    pkce_verifier: str = Field(min_length=43, max_length=128, repr=False)
    expected_nonce: str = Field(min_length=32, max_length=512, repr=False)


class VerifiedOidcIdentity(BaseModel):
    """Verified IdP identity mapped by the adapter to one local tenant user."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(min_length=1, max_length=512)
    session_id: str | None = Field(default=None, min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=255)
    user_id: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    email_verified: bool
    nonce: str = Field(min_length=32, max_length=512, repr=False)


class ValidatedOidcClaims(BaseModel):
    """Signature-verified IdP claims before any local authorization mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(min_length=1, max_length=512)
    session_id: str | None = Field(default=None, min_length=1, max_length=512)
    email: str = Field(min_length=3, max_length=320)
    email_verified: bool
    nonce: str = Field(min_length=32, max_length=512, repr=False)
    groups: tuple[str, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_groups(self) -> ValidatedOidcClaims:
        if any(not group or group != group.strip() or len(group) > 512 for group in self.groups):
            raise ValueError("groups must contain only bounded non-blank values")
        if len(self.groups) != len(set(self.groups)):
            raise ValueError("groups must be unique")
        return self


class ValidatedOidcLogoutToken(BaseModel):
    """Signature-verified OIDC Back-Channel Logout token identifiers."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    issuer: str = Field(min_length=1, max_length=2048)
    subject: str | None = Field(default=None, min_length=1, max_length=512)
    session_id: str | None = Field(default=None, min_length=1, max_length=512)
    jwt_id: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_target(self) -> ValidatedOidcLogoutToken:
        if self.subject is None and self.session_id is None:
            raise ValueError("logout token must identify a subject or provider session")
        return self


class OidcLogoutRevocationResult(BaseModel):
    """Idempotent persistence outcome without exposing external identifiers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    revoked_session_count: int = Field(ge=0)
    replayed: bool = False


def oidc_provider_binding_hash(issuer: str, value: str) -> str:
    """Hash one issuer-scoped provider identifier for DB capability matching."""

    if not issuer or not value or "\x00" in issuer or "\x00" in value:
        raise ValueError("OIDC provider binding values must be non-blank and NUL-free")
    return hashlib.sha256(f"{issuer}\x00{value}".encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ReturnPathAllowlist:
    """Allow only same-origin relative paths with segment-aware prefix matching."""

    allowed_prefixes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.allowed_prefixes:
            raise ValueError("allowed_prefixes must not be empty")
        normalized: list[str] = []
        for prefix in self.allowed_prefixes:
            path, query = _validate_relative_path(prefix)
            if query:
                raise ValueError("return path allowlist prefixes must not contain a query")
            normalized.append(path.rstrip("/") or "/")
        if len(set(normalized)) != len(normalized):
            raise ValueError("allowed_prefixes must be unique")
        object.__setattr__(self, "allowed_prefixes", tuple(normalized))

    def require_allowed(self, return_path: str) -> str:
        try:
            path, _query = _validate_relative_path(return_path)
        except ValueError as error:
            raise InvalidOidcReturnPathError() from error
        if not any(_matches_prefix(path, prefix) for prefix in self.allowed_prefixes):
            raise InvalidOidcReturnPathError()
        return return_path


def _validate_relative_path(value: str) -> tuple[str, str]:
    if not value or len(value) > 2048 or value != value.strip():
        raise ValueError("return path must be a bounded non-blank value")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment or not parsed.path.startswith("/"):
        raise ValueError("return path must be same-origin and fragment-free")
    decoded = unquote(parsed.path)
    if decoded.startswith("//") or "\\" in decoded:
        raise ValueError("return path must not contain an authority-like path")
    if any(ord(character) < 32 or ord(character) == 127 for character in decoded):
        raise ValueError("return path must not contain control characters")
    if any(segment in {".", ".."} for segment in decoded.split("/")):
        raise ValueError("return path must not contain dot segments")
    return decoded.rstrip("/") or "/", parsed.query


def _matches_prefix(path: str, prefix: str) -> bool:
    if prefix == "/":
        return True
    return path == prefix or path.startswith(f"{prefix}/")
