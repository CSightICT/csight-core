"""Unit tests for local password and JWT security adapters."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.adapters.security import Argon2PasswordHasher, PyJWTAccessTokenCodec
from app.ports.security import (
    AccessTokenCodec,
    ExpiredTokenError,
    InvalidTokenError,
    PasswordHasher,
)

pytestmark = pytest.mark.unit

_SECRET = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
_ISSUER = "csight-core"
_AUDIENCE = "csight-api"


def test_argon2_password_hasher_hashes_and_verifies_passwords() -> None:
    hasher = Argon2PasswordHasher()

    first_hash = hasher.hash_password("correct horse battery staple")
    second_hash = hasher.hash_password("correct horse battery staple")

    assert isinstance(hasher, PasswordHasher)
    assert first_hash.startswith("$argon2id$")
    assert first_hash != second_hash
    assert hasher.verify_password("correct horse battery staple", first_hash)
    assert not hasher.verify_password("wrong password", first_hash)


@pytest.mark.parametrize("encoded_hash", [None, "not-a-password-hash"])
def test_argon2_password_hasher_uses_safe_failure_path_for_missing_or_invalid_hash(
    encoded_hash: str | None,
) -> None:
    hasher = Argon2PasswordHasher()

    assert not hasher.verify_password("attacker supplied password", encoded_hash)


def test_jwt_codec_round_trip_preserves_required_claims_in_utc() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    codec = _build_codec(now=now)

    token = codec.issue_token(
        subject="user-123",
        tenant_id="tenant-a",
        roles=("Admin", "Reviewer"),
    )
    claims = codec.decode_token(token)

    assert isinstance(codec, AccessTokenCodec)
    assert claims.subject == "user-123"
    assert claims.tenant_id == "tenant-a"
    assert claims.roles == ("Admin", "Reviewer")
    assert claims.issued_at == now
    assert claims.expires_at == now + timedelta(minutes=15)
    assert claims.issued_at.tzinfo is UTC
    assert claims.expires_at.tzinfo is UTC
    assert claims.token_id == "token-id-123"


@pytest.mark.parametrize(
    ("issuer", "audience"),
    [("different-issuer", _AUDIENCE), (_ISSUER, "different-audience")],
)
def test_jwt_codec_rejects_wrong_issuer_or_audience(issuer: str, audience: str) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    token = _build_codec(now=now).issue_token(
        subject="user-123",
        tenant_id="tenant-a",
        roles=("Reviewer",),
    )
    rejecting_codec = PyJWTAccessTokenCodec(
        secret_key=_SECRET,
        issuer=issuer,
        audience=audience,
        access_token_ttl=timedelta(minutes=15),
    )

    with pytest.raises(InvalidTokenError, match="invalid"):
        rejecting_codec.decode_token(token)


def test_jwt_codec_rejects_expired_token_with_specific_error() -> None:
    old_time = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    codec = _build_codec(now=old_time, ttl=timedelta(seconds=1))
    token = codec.issue_token(subject="user-123", tenant_id="tenant-a", roles=("Reviewer",))

    with pytest.raises(ExpiredTokenError, match="expired"):
        codec.decode_token(token)


def test_jwt_codec_rejects_algorithm_outside_fixed_hs256_allowlist() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    payload = _valid_payload(now)
    token = jwt.encode(payload, _SECRET, algorithm="HS384")

    with pytest.raises(InvalidTokenError, match="invalid"):
        _build_codec(now=now).decode_token(token)


@pytest.mark.parametrize(
    "roles",
    ["Admin", ["Admin", 7], {"Admin": True}],
)
def test_jwt_codec_strictly_rejects_non_string_role_collections(roles: object) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    payload = _valid_payload(now)
    payload["roles"] = roles
    token = jwt.encode(payload, _SECRET, algorithm="HS256")

    with pytest.raises(InvalidTokenError, match="roles"):
        _build_codec(now=now).decode_token(token)


def test_jwt_codec_requires_all_identity_and_lifecycle_claims() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    payload = _valid_payload(now)
    del payload["jti"]
    token = jwt.encode(payload, _SECRET, algorithm="HS256")

    with pytest.raises(InvalidTokenError, match="invalid"):
        _build_codec(now=now).decode_token(token)


def test_jwt_codec_requires_explicit_secure_constructor_values() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        PyJWTAccessTokenCodec(
            secret_key="too-short",
            issuer=_ISSUER,
            audience=_AUDIENCE,
            access_token_ttl=timedelta(minutes=15),
        )
    with pytest.raises(ValueError, match="positive"):
        PyJWTAccessTokenCodec(
            secret_key=_SECRET,
            issuer=_ISSUER,
            audience=_AUDIENCE,
            access_token_ttl=timedelta(0),
        )


def _build_codec(
    *,
    now: datetime,
    ttl: timedelta = timedelta(minutes=15),
) -> PyJWTAccessTokenCodec:
    return PyJWTAccessTokenCodec(
        secret_key=_SECRET,
        issuer=_ISSUER,
        audience=_AUDIENCE,
        access_token_ttl=ttl,
        clock=lambda: now,
        token_id_factory=lambda: "token-id-123",
    )


def _valid_payload(now: datetime) -> dict[str, object]:
    return {
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "sub": "user-123",
        "tenant_id": "tenant-a",
        "roles": ["Reviewer"],
        "iat": now,
        "exp": now + timedelta(minutes=15),
        "jti": "token-id-123",
    }
