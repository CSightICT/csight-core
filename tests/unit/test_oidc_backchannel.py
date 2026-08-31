"""Network-free OIDC token, JWKS, claims, and local-authority tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import parse_qs

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from urllib3 import Timeout

from app.adapters.security.oidc_backchannel import Urllib3OidcBackchannel
from app.adapters.security.oidc_identity import ConfiguredOidcIdentityMapper, OidcGroupTarget
from app.platform.oidc import ValidatedOidcClaims, VerifiedOidcIdentity
from app.platform.tenant import Role, UserAccount
from app.ports.oidc import OidcProviderError, OidcProviderTemporarilyUnavailableError

pytestmark = pytest.mark.unit

ISSUER = "https://idp.example.test"
TOKEN_ENDPOINT = f"{ISSUER}/token"
JWKS_URI = f"{ISSUER}/jwks"
CLIENT_ID = "csight-client"
REDIRECT_URI = "https://csight.example.test/auth/oidc/callback"
NONCE = "n" * 43
TENANT_ID = "11111111-1111-4111-8111-111111111111"
USER_ID = "22222222-2222-4222-8222-222222222222"


@dataclass(slots=True)
class FakeResponse:
    status: int
    data: bytes
    released: bool = False
    closed: bool = False

    def read(
        self,
        amt: int | None = None,
        decode_content: bool | None = None,
        cache_content: bool = False,
    ) -> bytes:
        assert decode_content is True
        assert cache_content is False
        return self.data if amt is None else self.data[:amt]

    def release_conn(self) -> None:
        self.released = True

    def close(self) -> None:
        self.closed = True


@dataclass(slots=True)
class HttpCall:
    method: str
    url: str
    body: bytes | None
    headers: dict[str, str]
    timeout: Timeout
    retries: bool


@dataclass(slots=True)
class FakePool:
    responses: dict[str, list[FakeResponse]]
    calls: list[HttpCall] = field(default_factory=list)

    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None,
        headers: dict[str, str],
        timeout: Timeout,
        retries: bool,
        preload_content: bool,
    ) -> FakeResponse:
        assert preload_content is False
        self.calls.append(HttpCall(method, url, body, headers, timeout, retries))
        return self.responses[url].pop(0)


class FakeIdentities:
    def __init__(self, account: UserAccount) -> None:
        self.account = account

    def find_for_login(self, *, tenant_slug: str, email: str) -> UserAccount | None:
        if self.account.tenant_slug == tenant_slug and self.account.email == email:
            return self.account
        return None

    def get_by_tenant_and_subject(
        self,
        *,
        tenant_id: str,
        subject: str,
    ) -> UserAccount | None:
        return None


def _account(*, roles: frozenset[Role] = frozenset({Role.REVIEWER})) -> UserAccount:
    return UserAccount(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        tenant_slug="tenant-a",
        email="reviewer@example.test",
        display_name="Local Reviewer",
        password_hash="not-used",
        roles=roles,
        is_active=True,
        tenant_is_active=True,
    )


def _mapper(
    *,
    account: UserAccount | None = None,
    mappings: dict[str, OidcGroupTarget] | None = None,
) -> ConfiguredOidcIdentityMapper:
    return ConfiguredOidcIdentityMapper(
        identities=FakeIdentities(account or _account()),
        group_mappings=mappings
        or {
            "idp/tenant-a/reviewers": OidcGroupTarget(
                tenant_slug="tenant-a",
                allowed_roles=frozenset({Role.REVIEWER}),
            )
        },
    )


def _signed_fixture(
    *,
    payload_updates: dict[str, object] | None = None,
    signing_key: rsa.RSAPrivateKey | None = None,
) -> tuple[str, dict[str, object]]:
    private_key = signing_key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "provider-subject",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "nonce": NONCE,
        "email": "reviewer@example.test",
        "email_verified": True,
        "groups": ["idp/tenant-a/reviewers"],
    }
    payload.update(payload_updates or {})
    id_token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "key-1"})
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk = cast(dict[str, object], public_jwk)
    jwk.update({"kid": "key-1", "use": "sig", "alg": "RS256", "key_ops": ["verify"]})
    return id_token, {"keys": [jwk]}


def _signed_logout_fixture(
    *,
    payload_updates: dict[str, object] | None = None,
) -> tuple[str, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "provider-subject",
        "sid": "provider-session",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "jti": "logout-jti",
        "events": {"http://schemas.openid.net/event/backchannel-logout": {}},
    }
    payload.update(payload_updates or {})
    logout_token = jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1", "typ": "logout+jwt"},
    )
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk = cast(dict[str, object], public_jwk)
    jwk.update({"kid": "key-1", "use": "sig", "alg": "RS256", "key_ops": ["verify"]})
    return logout_token, {"keys": [jwk]}


def _backchannel(
    *,
    id_token: str,
    jwks: dict[str, object],
    mapper: ConfiguredOidcIdentityMapper | None = None,
    extra_jwks_responses: int = 0,
) -> tuple[Urllib3OidcBackchannel, FakePool]:
    token_body = json.dumps({"id_token": id_token, "token_type": "Bearer"}).encode()
    jwks_body = json.dumps(jwks).encode()
    pool = FakePool(
        {
            TOKEN_ENDPOINT: [FakeResponse(200, token_body), FakeResponse(200, token_body)],
            JWKS_URI: [FakeResponse(200, jwks_body) for _ in range(1 + extra_jwks_responses)],
        }
    )
    return (
        Urllib3OidcBackchannel(
            identity_mapper=mapper or _mapper(),
            http_pool=pool,
            clock_skew_seconds=0,
        ),
        pool,
    )


def _exchange(
    adapter: Urllib3OidcBackchannel,
    *,
    nonce: str = NONCE,
) -> VerifiedOidcIdentity:
    return adapter.exchange_and_validate(
        token_endpoint=TOKEN_ENDPOINT,
        jwks_uri=JWKS_URI,
        issuer=ISSUER,
        client_id=CLIENT_ID,
        client_secret="confidential-client-secret",
        redirect_uri=REDIRECT_URI,
        allowed_algorithms=("RS256",),
        groups_claim="groups",
        code="authorization-code",
        pkce_verifier="v" * 64,
        expected_nonce=nonce,
    )


def test_pooled_exchange_verifies_rs256_and_uses_current_local_identity() -> None:
    id_token, jwks = _signed_fixture()
    adapter, pool = _backchannel(id_token=id_token, jwks=jwks)

    identity = _exchange(adapter)
    second_identity = _exchange(adapter)

    assert identity == second_identity
    assert identity.tenant_id == TENANT_ID
    assert identity.user_id == USER_ID
    assert identity.subject == "provider-subject"
    assert [call.method for call in pool.calls] == ["POST", "GET", "POST"]
    assert all(call.retries is False for call in pool.calls)
    token_call = pool.calls[0]
    assert token_call.body is not None
    assert parse_qs(token_call.body.decode())["code_verifier"] == ["v" * 64]
    assert "client_secret" not in token_call.body.decode()
    assert token_call.headers["Authorization"].startswith("Basic ")


def test_id_token_carries_optional_provider_session_for_targeted_logout() -> None:
    id_token, jwks = _signed_fixture(payload_updates={"sid": "provider-session"})
    adapter, _pool = _backchannel(id_token=id_token, jwks=jwks)

    identity = _exchange(adapter)

    assert identity.session_id == "provider-session"


def test_signed_backchannel_logout_token_validates_without_identity_mapping() -> None:
    logout_token, jwks = _signed_logout_fixture()
    adapter, pool = _backchannel(id_token=logout_token, jwks=jwks)

    result = adapter.validate_logout_token(
        raw_logout_token=logout_token,
        jwks_uri=JWKS_URI,
        issuer=ISSUER,
        client_id=CLIENT_ID,
        allowed_algorithms=("RS256",),
    )

    assert result.issuer == ISSUER
    assert result.subject == "provider-subject"
    assert result.session_id == "provider-session"
    assert result.jwt_id == "logout-jti"
    assert [call.url for call in pool.calls] == [JWKS_URI]


@pytest.mark.parametrize(
    "claim_update",
    [
        {"nonce": NONCE},
        {"events": {}},
        {"events": {"http://schemas.openid.net/event/backchannel-logout": "wrong"}},
        {"sub": None, "sid": None},
        {"aud": "wrong-client"},
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
    ],
)
def test_backchannel_logout_claims_fail_closed(claim_update: dict[str, object]) -> None:
    logout_token, jwks = _signed_logout_fixture(payload_updates=claim_update)
    adapter, _pool = _backchannel(id_token=logout_token, jwks=jwks)

    with pytest.raises(OidcProviderError):
        adapter.validate_logout_token(
            raw_logout_token=logout_token,
            jwks_uri=JWKS_URI,
            issuer=ISSUER,
            client_id=CLIENT_ID,
            allowed_algorithms=("RS256",),
        )


@pytest.mark.parametrize(
    ("claim_update", "expected_nonce"),
    [
        ({"iss": "https://wrong-issuer.example.test"}, NONCE),
        ({"aud": "wrong-client"}, NONCE),
        ({"exp": datetime.now(UTC) - timedelta(minutes=1)}, NONCE),
        ({}, "different-nonce-value-that-is-long-enough"),
    ],
)
def test_issuer_audience_expiry_and_nonce_all_fail_closed(
    claim_update: dict[str, object],
    expected_nonce: str,
) -> None:
    id_token, jwks = _signed_fixture(payload_updates=claim_update)
    adapter, _pool = _backchannel(id_token=id_token, jwks=jwks)

    with pytest.raises(OidcProviderError):
        _exchange(adapter, nonce=expected_nonce)


def test_signature_failure_forces_one_jwks_refresh_then_fails() -> None:
    id_token, _signed_jwks = _signed_fixture()
    _other_token, wrong_jwks = _signed_fixture()
    adapter, pool = _backchannel(
        id_token=id_token,
        jwks=wrong_jwks,
        extra_jwks_responses=1,
    )

    with pytest.raises(OidcProviderError):
        _exchange(adapter)

    assert [call.url for call in pool.calls].count(JWKS_URI) == 2


def test_group_mapping_requires_exactly_one_group_and_current_roles_within_allowlist() -> None:
    claims = ValidatedOidcClaims(
        issuer=ISSUER,
        subject="provider-subject",
        email="reviewer@example.test",
        email_verified=True,
        nonce=NONCE,
        groups=("group-a", "group-b"),
    )
    ambiguous = _mapper(
        mappings={
            "group-a": OidcGroupTarget("tenant-a", frozenset({Role.REVIEWER})),
            "group-b": OidcGroupTarget("tenant-a", frozenset({Role.REVIEWER})),
        }
    )
    disallowed_role = _mapper(account=_account(roles=frozenset({Role.ADMIN})))

    with pytest.raises(OidcProviderError):
        ambiguous.map_identity(claims)
    with pytest.raises(OidcProviderError):
        disallowed_role.map_identity(
            claims.model_copy(update={"groups": ("idp/tenant-a/reviewers",)})
        )


def test_retryable_token_endpoint_status_is_temporary_without_reading_jwks() -> None:
    pool = FakePool(
        {
            TOKEN_ENDPOINT: [FakeResponse(503, b'{"error":"temporarily_unavailable"}')],
            JWKS_URI: [],
        }
    )
    adapter = Urllib3OidcBackchannel(identity_mapper=_mapper(), http_pool=pool)

    with pytest.raises(OidcProviderTemporarilyUnavailableError):
        _exchange(adapter)

    assert [call.url for call in pool.calls] == [TOKEN_ENDPOINT]


def test_oversized_provider_body_is_bounded_and_connection_is_not_reused() -> None:
    oversized = FakeResponse(200, b"x" * 1025)
    pool = FakePool({TOKEN_ENDPOINT: [oversized], JWKS_URI: []})
    adapter = Urllib3OidcBackchannel(
        identity_mapper=_mapper(),
        http_pool=pool,
        max_response_bytes=1024,
    )

    with pytest.raises(OidcProviderError):
        _exchange(adapter)

    assert oversized.closed is True
    assert oversized.released is False
