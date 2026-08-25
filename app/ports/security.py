"""Technology-neutral password and access-token boundaries."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


class SecurityError(RuntimeError):
    """Base error for security boundary failures safe for application handling."""


class InvalidTokenError(SecurityError):
    """Raised when an access token is malformed or fails validation."""


class ExpiredTokenError(InvalidTokenError):
    """Raised when an otherwise parseable access token has expired."""


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """Validated identity claims returned by an access-token adapter."""

    subject: str
    tenant_id: str
    roles: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    token_id: str

    def __post_init__(self) -> None:
        _require_non_empty_claim("subject", self.subject)
        _require_non_empty_claim("tenant_id", self.tenant_id)
        _require_non_empty_claim("token_id", self.token_id)
        if any(not role or role != role.strip() for role in self.roles):
            raise ValueError("roles must be a tuple of non-empty strings")

        issued_at = _as_utc("issued_at", self.issued_at)
        expires_at = _as_utc("expires_at", self.expires_at)
        if expires_at <= issued_at:
            raise ValueError("expires_at must be after issued_at")

        object.__setattr__(self, "issued_at", issued_at)
        object.__setattr__(self, "expires_at", expires_at)


def _require_non_empty_claim(name: str, value: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _as_utc(name: str, value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


@runtime_checkable
class PasswordHasher(Protocol):
    """Hash and verify passwords without exposing a concrete hash library."""

    def hash_password(self, password: str) -> str: ...

    def verify_password(self, password: str, encoded_hash: str | None) -> bool:
        """Verify a hash, using a dummy hash when no user hash is available."""
        ...


@runtime_checkable
class AccessTokenCodec(Protocol):
    """Issue and validate application access tokens."""

    def issue_token(
        self,
        *,
        subject: str,
        tenant_id: str,
        roles: tuple[str, ...],
    ) -> str: ...

    def decode_token(self, token: str) -> AccessTokenClaims: ...
