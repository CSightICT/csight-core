"""HS256 access-token adapter backed by PyJWT."""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import jwt
from jwt.exceptions import ExpiredSignatureError, PyJWTError

from app.ports.security import AccessTokenClaims, ExpiredTokenError, InvalidTokenError

_ALGORITHM = "HS256"
_REQUIRED_CLAIMS = ("iss", "aud", "sub", "tenant_id", "roles", "iat", "exp", "jti")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_token_id() -> str:
    return str(uuid4())


class PyJWTAccessTokenCodec:
    """Issue and validate local PoC JWTs with a fixed HS256 allowlist."""

    def __init__(
        self,
        *,
        secret_key: str,
        issuer: str,
        audience: str,
        access_token_ttl: timedelta,
        clock: Callable[[], datetime] = _utc_now,
        token_id_factory: Callable[[], str] = _new_token_id,
    ) -> None:
        if len(secret_key.encode("utf-8")) < 32:
            raise ValueError("secret_key must contain at least 32 bytes")
        self._issuer = _require_non_empty("issuer", issuer)
        self._audience = _require_non_empty("audience", audience)
        if access_token_ttl <= timedelta(0):
            raise ValueError("access_token_ttl must be positive")

        self._secret_key = secret_key
        self._access_token_ttl = access_token_ttl
        self._clock = clock
        self._token_id_factory = token_id_factory

    def issue_token(
        self,
        *,
        subject: str,
        tenant_id: str,
        roles: tuple[str, ...],
    ) -> str:
        issued_at = _as_utc(self._clock())
        claims = AccessTokenClaims(
            subject=subject,
            tenant_id=tenant_id,
            roles=roles,
            issued_at=issued_at,
            expires_at=issued_at + self._access_token_ttl,
            token_id=self._token_id_factory(),
        )
        payload: dict[str, object] = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": claims.subject,
            "tenant_id": claims.tenant_id,
            "roles": list(claims.roles),
            "iat": claims.issued_at,
            "exp": claims.expires_at,
            "jti": claims.token_id,
        }
        return jwt.encode(payload, self._secret_key, algorithm=_ALGORITHM)

    def decode_token(self, token: str) -> AccessTokenClaims:
        if not token:
            raise InvalidTokenError("access token is invalid")
        try:
            decoded = jwt.decode(
                token,
                self._secret_key,
                algorithms=[_ALGORITHM],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": list(_REQUIRED_CLAIMS)},
            )
        except ExpiredSignatureError as error:
            raise ExpiredTokenError("access token has expired") from error
        except PyJWTError as error:
            raise InvalidTokenError("access token is invalid") from error

        payload = cast(Mapping[str, object], decoded)
        return _parse_claims(payload)


def _parse_claims(payload: Mapping[str, object]) -> AccessTokenClaims:
    roles_value = payload.get("roles")
    if not isinstance(roles_value, (list, tuple)) or any(
        not isinstance(role, str) or not role or role != role.strip() for role in roles_value
    ):
        raise InvalidTokenError("access token contains invalid roles")

    try:
        return AccessTokenClaims(
            subject=_require_string_claim(payload, "sub"),
            tenant_id=_require_string_claim(payload, "tenant_id"),
            roles=tuple(roles_value),
            issued_at=_require_timestamp_claim(payload, "iat"),
            expires_at=_require_timestamp_claim(payload, "exp"),
            token_id=_require_string_claim(payload, "jti"),
        )
    except ValueError as error:
        raise InvalidTokenError("access token contains invalid claims") from error


def _require_string_claim(payload: Mapping[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value or value != value.strip():
        raise InvalidTokenError(f"access token contains invalid {name} claim")
    return value


def _require_timestamp_claim(payload: Mapping[str, object], name: str) -> datetime:
    value = payload.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidTokenError(f"access token contains invalid {name} claim")
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OSError, OverflowError, ValueError) as error:
        raise InvalidTokenError(f"access token contains invalid {name} claim") from error


def _require_non_empty(name: str, value: str) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC)
