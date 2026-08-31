"""Unit contracts for OIDC PKCE login, hashed sessions, CSRF, and HTTP cookies."""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any, cast
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import TenantModel, UserModel
from app.adapters.persistence.oidc_sessions import (
    OidcLoginTransactionModel,
    OidcLogoutEventModel,
    OidcSessionModel,
    SQLAlchemyOidcRepository,
)
from app.adapters.security.oidc_provider import (
    OidcProviderConfiguration,
    StandardOidcProviderAdapter,
)
from app.application.oidc import (
    OIDC_SESSION_ABSOLUTE_TIMEOUT,
    OIDC_SESSION_IDLE_TIMEOUT,
    CompleteOidcLoginCommand,
    OidcSessionService,
    StartOidcLoginCommand,
)
from app.bootstrap.oidc import (
    OidcConfigurationError,
    OidcRuntime,
    build_oidc_runtime,
    oidc_is_configured,
)
from app.bootstrap.settings import Settings
from app.interface.http import register_exception_handlers
from app.interface.http.dependencies import provide_current_principal
from app.interface.http.oidc_router import (
    OidcCookieConfiguration,
    create_auth_capabilities_router,
    create_oidc_router,
)
from app.interface.http.services import Sprint1ServiceContainer
from app.main import create_app
from app.platform.oidc import (
    InvalidOidcCallbackError,
    InvalidOidcCsrfTokenError,
    InvalidOidcReturnPathError,
    InvalidOidcSessionError,
    OidcLoginTransaction,
    OidcLogoutRevocationResult,
    OidcSession,
    ReturnPathAllowlist,
    ValidatedOidcLogoutToken,
    VerifiedOidcIdentity,
)
from app.platform.tenant import Principal, Role, UserAccount
from app.ports.oidc import OidcProviderError

pytestmark = pytest.mark.unit

# Cookie jars compare Expires against the real wall clock. Keep the frozen service clock aligned
# with the test process date so the HTTP cookie does not become an unrelated time bomb.
NOW = datetime.now(UTC).replace(microsecond=0)
TENANT_ID = "11111111-1111-4111-8111-111111111111"
USER_ID = "22222222-2222-4222-8222-222222222222"


@dataclass(slots=True)
class MutableClock:
    value: datetime = NOW

    def now(self) -> datetime:
        return self.value


@dataclass(slots=True)
class SequenceIds:
    values: list[str]

    def new_id(self) -> str:
        return self.values.pop(0)


@dataclass(slots=True)
class SequenceTokens:
    values: list[str]

    def token_urlsafe(self, *, entropy_bytes: int) -> str:
        assert 16 <= entropy_bytes <= 128
        return self.values.pop(0)


@dataclass(slots=True)
class MemoryLoginTransactions:
    records: dict[str, OidcLoginTransaction] = field(default_factory=dict)

    def add(self, value: OidcLoginTransaction) -> None:
        self.records[value.state_hash] = value

    def consume(self, *, state_hash: str, now: datetime) -> OidcLoginTransaction | None:
        transaction = self.records.get(state_hash)
        if (
            transaction is None
            or transaction.consumed_at is not None
            or now >= transaction.expires_at
        ):
            return None
        consumed = transaction.model_copy(update={"consumed_at": now})
        self.records[state_hash] = consumed
        return consumed


@dataclass(slots=True)
class MemorySessions:
    records: dict[str, OidcSession] = field(default_factory=dict)
    logout_jtis: set[str] = field(default_factory=set)

    def add(self, value: OidcSession) -> None:
        self.records[value.session_id_hash] = value

    def get_and_touch(
        self,
        *,
        session_id_hash: str,
        now: datetime,
        idle_timeout: timedelta,
    ) -> OidcSession | None:
        return self._touch(
            session_id_hash=session_id_hash,
            csrf_token_hash=None,
            now=now,
            idle_timeout=idle_timeout,
        )

    def validate_csrf_and_touch(
        self,
        *,
        session_id_hash: str,
        csrf_token_hash: str,
        now: datetime,
        idle_timeout: timedelta,
    ) -> OidcSession | None:
        return self._touch(
            session_id_hash=session_id_hash,
            csrf_token_hash=csrf_token_hash,
            now=now,
            idle_timeout=idle_timeout,
        )

    def rotate_csrf_and_touch(
        self,
        *,
        session_id_hash: str,
        new_csrf_token_hash: str,
        now: datetime,
        idle_timeout: timedelta,
    ) -> OidcSession | None:
        touched = self._touch(
            session_id_hash=session_id_hash,
            csrf_token_hash=None,
            now=now,
            idle_timeout=idle_timeout,
        )
        if touched is None:
            return None
        rotated = touched.model_copy(update={"csrf_token_hash": new_csrf_token_hash})
        self.records[session_id_hash] = rotated
        return rotated

    def revoke(
        self,
        *,
        session_id_hash: str,
        now: datetime,
        reason: str,
    ) -> bool:
        session = self.records.get(session_id_hash)
        if session is None:
            return False
        self.records[session_id_hash] = session.model_copy(
            update={"revoked_at": now, "revocation_reason": reason}
        )
        return True

    def revoke_by_provider_logout(
        self,
        *,
        logout: ValidatedOidcLogoutToken,
        now: datetime,
    ) -> OidcLogoutRevocationResult:
        if logout.jwt_id in self.logout_jtis:
            return OidcLogoutRevocationResult(revoked_session_count=0, replayed=True)
        self.logout_jtis.add(logout.jwt_id)
        revoked_count = 0
        for session_hash, session in tuple(self.records.items()):
            if session.provider_issuer != logout.issuer or session.revoked_at is not None:
                continue
            subject_matches = (
                logout.subject is not None and session.provider_subject == logout.subject
            )
            session_matches = (
                logout.session_id is not None and session.provider_session_id == logout.session_id
            )
            legacy_matches = session.provider_session_id is None and subject_matches
            targeted = (
                subject_matches if logout.session_id is None else session_matches or legacy_matches
            )
            if not targeted:
                continue
            self.records[session_hash] = session.model_copy(
                update={
                    "revoked_at": now,
                    "revocation_reason": "OIDC_BACKCHANNEL_LOGOUT",
                }
            )
            revoked_count += 1
        return OidcLogoutRevocationResult(
            revoked_session_count=revoked_count,
            replayed=False,
        )

    def _touch(
        self,
        *,
        session_id_hash: str,
        csrf_token_hash: str | None,
        now: datetime,
        idle_timeout: timedelta,
    ) -> OidcSession | None:
        session = self.records.get(session_id_hash)
        if session is None or not session.is_active_at(now):
            return None
        if csrf_token_hash is not None and not hmac.compare_digest(
            csrf_token_hash,
            session.csrf_token_hash,
        ):
            return None
        touched = session.model_copy(
            update={
                "last_seen_at": now,
                "idle_expires_at": min(now + idle_timeout, session.absolute_expires_at),
            }
        )
        self.records[session_id_hash] = touched
        return touched


class FakeIdentityRepository:
    def __init__(self, account: UserAccount) -> None:
        self.account = account

    def find_for_login(self, *, tenant_slug: str, email: str) -> UserAccount | None:
        return None

    def get_by_tenant_and_subject(
        self,
        *,
        tenant_id: str,
        subject: str,
    ) -> UserAccount | None:
        if self.account.tenant_id == tenant_id and self.account.user_id == subject:
            return self.account
        return None


@dataclass(slots=True)
class RecordingBackchannel:
    calls: list[dict[str, str]] = field(default_factory=list)
    logout_calls: list[str] = field(default_factory=list)

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
    ) -> VerifiedOidcIdentity:
        self.calls.append(
            {
                "token_endpoint": token_endpoint,
                "jwks_uri": jwks_uri,
                "issuer": issuer,
                "client_id": client_id,
                "client_secret": client_secret or "",
                "redirect_uri": redirect_uri,
                "allowed_algorithms": ",".join(allowed_algorithms),
                "groups_claim": groups_claim,
                "code": code,
                "pkce_verifier": pkce_verifier,
                "expected_nonce": expected_nonce,
            }
        )
        return VerifiedOidcIdentity(
            issuer=issuer,
            subject="provider-subject",
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            email="reviewer@example.test",
            email_verified=True,
            nonce=expected_nonce,
        )

    def validate_logout_token(
        self,
        *,
        raw_logout_token: str,
        jwks_uri: str,
        issuer: str,
        client_id: str,
        allowed_algorithms: tuple[str, ...],
    ) -> ValidatedOidcLogoutToken:
        assert jwks_uri == "https://idp.example.test/jwks"
        assert client_id == "csight-client"
        assert allowed_algorithms == ("RS256",)
        self.logout_calls.append(raw_logout_token)
        if raw_logout_token == "invalid-logout-token":
            raise OidcProviderError("invalid")
        return ValidatedOidcLogoutToken(
            issuer=issuer,
            subject="provider-subject",
            jwt_id="logout-jti",
        )


@dataclass(slots=True)
class OidcHarness:
    service: OidcSessionService
    clock: MutableClock
    logins: MemoryLoginTransactions
    sessions: MemorySessions
    backchannel: RecordingBackchannel


def _harness(
    *,
    absolute_timeout: timedelta = OIDC_SESSION_ABSOLUTE_TIMEOUT,
    idle_timeout: timedelta = OIDC_SESSION_IDLE_TIMEOUT,
) -> OidcHarness:
    clock = MutableClock()
    logins = MemoryLoginTransactions()
    sessions = MemorySessions()
    backchannel = RecordingBackchannel()
    provider = StandardOidcProviderAdapter(
        configuration=OidcProviderConfiguration(
            provider_key="enterprise",
            issuer="https://idp.example.test",
            client_id="csight-client",
            authorization_endpoint="https://idp.example.test/authorize",
            token_endpoint="https://idp.example.test/token",
            jwks_uri="https://idp.example.test/jwks",
            redirect_uri="https://csight.example.test/auth/oidc/callback",
        ),
        backchannel=backchannel,
    )
    account = UserAccount(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        tenant_slug="tenant-a",
        email="reviewer@example.test",
        display_name="OIDC Reviewer",
        password_hash="not-used-for-oidc",
        roles=frozenset({Role.REVIEWER}),
        is_active=True,
        tenant_is_active=True,
    )
    service = OidcSessionService(
        login_transactions=logins,
        sessions=sessions,
        identities=FakeIdentityRepository(account),
        provider=provider,
        secure_tokens=SequenceTokens(
            values=[
                "A" * 43,
                "B" * 43,
                "C" * 86,
                "D" * 64,
                "E" * 43,
                "F" * 43,
                "G" * 43,
                "H" * 43,
            ]
        ),
        clock=clock,
        id_generator=SequenceIds(values=[str(uuid4()), str(uuid4())]),
        return_paths=ReturnPathAllowlist(("/cases", "/reviews")),
        absolute_timeout=absolute_timeout,
        idle_timeout=idle_timeout,
    )
    return OidcHarness(
        service=service,
        clock=clock,
        logins=logins,
        sessions=sessions,
        backchannel=backchannel,
    )


def test_oidc_provider_http_is_rejected_by_default_and_bounded_by_explicit_opt_in() -> None:
    values: dict[str, Any] = {
        "provider_key": "qualification",
        "issuer": "http://127.0.0.1:18080/realms/csight",
        "client_id": "csight-client",
        "authorization_endpoint": "http://127.0.0.1:18080/authorize",
        "token_endpoint": "http://keycloak:8080/token",
        "jwks_uri": "http://keycloak:8080/jwks",
        "redirect_uri": "http://127.0.0.1:18000/auth/oidc/callback",
    }

    with pytest.raises(ValueError, match="HTTPS"):
        OidcProviderConfiguration(**values)

    configuration = OidcProviderConfiguration(
        **values,
        allow_insecure_http=True,
    )
    assert configuration.allow_insecure_http is True


def _start_and_complete(harness: OidcHarness) -> tuple[str, str, str]:
    started = harness.service.start_login(
        StartOidcLoginCommand(return_path="/cases/active?tab=mine")
    )
    state = parse_qs(urlsplit(started.authorization_url).query)["state"][0]
    completed = harness.service.complete_login(
        CompleteOidcLoginCommand(code="authorization-code", state=state)
    )
    return state, completed.session_id, completed.csrf_token


def test_oidc_pkce_transaction_is_server_side_one_time_and_creates_only_hashed_session() -> None:
    harness = _harness()
    started = harness.service.start_login(
        StartOidcLoginCommand(return_path="/cases/active?tab=mine")
    )
    authorization_query = parse_qs(urlsplit(started.authorization_url).query)
    state = authorization_query["state"][0]
    transaction = next(iter(harness.logins.records.values()))

    assert authorization_query["response_type"] == ["code"]
    assert authorization_query["code_challenge_method"] == ["S256"]
    assert authorization_query["code_challenge"][0] != transaction.pkce_verifier
    assert transaction.state_hash == hashlib.sha256(state.encode()).hexdigest()
    assert not hasattr(transaction, "state")
    assert transaction.nonce == authorization_query["nonce"][0]

    completed = harness.service.complete_login(
        CompleteOidcLoginCommand(code="authorization-code", state=state)
    )
    session = next(iter(harness.sessions.records.values()))

    assert session.session_id_hash == hashlib.sha256(completed.session_id.encode()).hexdigest()
    assert session.csrf_token_hash == hashlib.sha256(completed.csrf_token.encode()).hexdigest()
    assert completed.session_id not in session.model_dump_json()
    assert completed.csrf_token not in session.model_dump_json()
    assert session.absolute_expires_at - session.created_at == OIDC_SESSION_ABSOLUTE_TIMEOUT
    assert session.idle_expires_at - session.last_seen_at == OIDC_SESSION_IDLE_TIMEOUT
    assert completed.expiry.expiry_warning_at == session.idle_expires_at - timedelta(minutes=5)
    assert harness.backchannel.calls[0]["pkce_verifier"] == transaction.pkce_verifier

    with pytest.raises(InvalidOidcCallbackError):
        harness.service.complete_login(CompleteOidcLoginCommand(code="replayed-code", state=state))
    assert len(harness.backchannel.calls) == 1


def test_session_timeouts_are_injectable_with_secure_eight_hour_and_thirty_minute_caps() -> None:
    harness = _harness(
        absolute_timeout=timedelta(hours=2),
        idle_timeout=timedelta(minutes=15),
    )
    _state, raw_session_id, _raw_csrf = _start_and_complete(harness)
    session = harness.sessions.records[hashlib.sha256(raw_session_id.encode()).hexdigest()]

    assert session.absolute_expires_at - session.created_at == timedelta(hours=2)
    assert session.idle_expires_at - session.last_seen_at == timedelta(minutes=15)


@pytest.mark.parametrize(
    "return_path",
    [
        "https://evil.example/cases",
        "//evil.example/cases",
        "/case-study",
        "/cases/../admin",
        "/cases%2f..%2fadmin",
        "/reviews#token",
    ],
)
def test_return_path_allowlist_rejects_external_or_boundary_bypass(return_path: str) -> None:
    with pytest.raises(InvalidOidcReturnPathError):
        ReturnPathAllowlist(("/cases", "/reviews")).require_allowed(return_path)


def test_csrf_idle_absolute_and_inactive_identity_fail_closed() -> None:
    harness = _harness()
    _state, raw_session_id, raw_csrf = _start_and_complete(harness)

    with pytest.raises(InvalidOidcCsrfTokenError):
        harness.service.validate_csrf(session_id=raw_session_id, csrf_token="wrong" * 10)
    resolved = harness.service.validate_csrf(
        session_id=raw_session_id,
        csrf_token=raw_csrf,
    )
    assert resolved.principal.user_id == USER_ID

    session_hash = hashlib.sha256(raw_session_id.encode()).hexdigest()
    session = harness.sessions.records[session_hash]
    near_absolute = session.absolute_expires_at - timedelta(minutes=4)
    harness.sessions.records[session_hash] = session.model_copy(
        update={
            "last_seen_at": near_absolute - timedelta(minutes=20),
            "idle_expires_at": near_absolute + timedelta(minutes=5),
        }
    )
    harness.clock.value = near_absolute
    warning = harness.service.resolve_session(session_id=raw_session_id)
    assert warning.expiry.expires_within_five_minutes is True
    assert warning.expiry.effective_expires_at == session.absolute_expires_at

    harness.clock.value = session.absolute_expires_at
    with pytest.raises(InvalidOidcSessionError):
        harness.service.resolve_session(session_id=raw_session_id)


def test_sqlalchemy_adapter_consumes_state_once_and_never_persists_raw_browser_secrets() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", _register_sqlite_functions)
    tables = [
        cast(Table, TenantModel.__table__),
        cast(Table, UserModel.__table__),
        cast(Table, OidcLoginTransactionModel.__table__),
        cast(Table, OidcSessionModel.__table__),
        cast(Table, OidcLogoutEventModel.__table__),
    ]
    TenantModel.metadata.create_all(engine, tables=tables)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    tenant_id = UUID(TENANT_ID)
    user_id = UUID(USER_ID)
    with factory.begin() as database:
        database.add(TenantModel(id=tenant_id, slug="tenant-a", name="Tenant A", is_active=True))
        database.add(
            UserModel(
                id=user_id,
                tenant_id=tenant_id,
                email="reviewer@example.test",
                password_hash="not-used",
                display_name="Reviewer",
                is_active=True,
            )
        )
    repository = SQLAlchemyOidcRepository(factory)
    raw_state = "state-secret-value"
    state_hash = hashlib.sha256(raw_state.encode()).hexdigest()
    transaction = OidcLoginTransaction(
        transaction_id=str(uuid4()),
        provider_key="enterprise",
        state_hash=state_hash,
        nonce="N" * 43,
        pkce_verifier="V" * 64,
        return_path="/cases",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    repository.add(transaction)

    assert repository.consume(state_hash=state_hash, now=NOW + timedelta(seconds=1)) is not None
    assert repository.consume(state_hash=state_hash, now=NOW + timedelta(seconds=2)) is None

    raw_session = "raw-session-id-that-only-the-browser-receives"
    raw_csrf = "raw-csrf-token-that-only-the-browser-receives"
    session_hash = hashlib.sha256(raw_session.encode()).hexdigest()
    csrf_hash = hashlib.sha256(raw_csrf.encode()).hexdigest()
    repository.add(
        OidcSession(
            session_record_id=str(uuid4()),
            session_id_hash=session_hash,
            csrf_token_hash=csrf_hash,
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider_issuer="https://idp.example.test",
            provider_subject="provider-subject",
            created_at=NOW,
            last_seen_at=NOW,
            idle_expires_at=NOW + timedelta(minutes=30),
            absolute_expires_at=NOW + timedelta(hours=8),
        )
    )
    with factory() as database:
        stored = database.scalar(
            select(OidcSessionModel).where(OidcSessionModel.session_id_hash == session_hash)
        )
        assert stored is not None
        serialized = repr(vars(stored))
        assert stored.session_id_hash == session_hash
        assert stored.csrf_token_hash == csrf_hash
        assert raw_session not in serialized
        assert raw_csrf not in serialized

    assert (
        repository.validate_csrf_and_touch(
            session_id_hash=session_hash,
            csrf_token_hash="f" * 64,
            now=NOW + timedelta(minutes=1),
            idle_timeout=timedelta(minutes=30),
        )
        is None
    )
    assert (
        repository.validate_csrf_and_touch(
            session_id_hash=session_hash,
            csrf_token_hash=csrf_hash,
            now=NOW + timedelta(minutes=1),
            idle_timeout=timedelta(minutes=30),
        )
        is not None
    )
    rotated_hash = "e" * 64
    rotated = repository.rotate_csrf_and_touch(
        session_id_hash=session_hash,
        new_csrf_token_hash=rotated_hash,
        now=NOW + timedelta(seconds=90),
        idle_timeout=timedelta(minutes=30),
    )
    assert rotated is not None and rotated.csrf_token_hash == rotated_hash
    assert repository.revoke(
        session_id_hash=session_hash,
        now=NOW + timedelta(minutes=2),
        reason="LOGOUT",
    )
    assert (
        repository.get_and_touch(
            session_id_hash=session_hash,
            now=NOW + timedelta(minutes=3),
            idle_timeout=timedelta(minutes=30),
        )
        is None
    )

    provider_session_hash = "d" * 64
    repository.add(
        OidcSession(
            session_record_id=str(uuid4()),
            session_id_hash=provider_session_hash,
            csrf_token_hash="c" * 64,
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            provider_issuer="https://idp.example.test",
            provider_subject="provider-subject",
            provider_session_id="provider-session",
            created_at=NOW,
            last_seen_at=NOW,
            idle_expires_at=NOW + timedelta(minutes=30),
            absolute_expires_at=NOW + timedelta(hours=8),
        )
    )
    logout = ValidatedOidcLogoutToken(
        issuer="https://idp.example.test",
        subject="provider-subject",
        session_id="provider-session",
        jwt_id="provider-logout-jti",
    )
    provider_revocation = repository.revoke_by_provider_logout(
        logout=logout,
        now=NOW + timedelta(minutes=4),
    )
    replay = repository.revoke_by_provider_logout(
        logout=logout,
        now=NOW + timedelta(minutes=5),
    )
    assert provider_revocation.revoked_session_count == 1
    assert provider_revocation.replayed is False
    assert replay.replayed is True
    with factory() as database:
        stored_provider_session = database.scalar(
            select(OidcSessionModel).where(
                OidcSessionModel.session_id_hash == provider_session_hash
            )
        )
        events = database.scalars(select(OidcLogoutEventModel)).all()
        assert stored_provider_session is not None
        assert stored_provider_session.revocation_reason == "OIDC_BACKCHANNEL_LOGOUT"
        assert len(events) == 1
        assert events[0].revoked_session_count == 1
        assert events[0].token_jti_hash != logout.jwt_id
    engine.dispose()


def test_router_binds_login_state_to_browser_then_sets_httponly_session_cookie() -> None:
    harness = _harness()
    application = FastAPI()
    register_exception_handlers(application)
    application.include_router(
        create_oidc_router(
            service=harness.service,
            cookie=OidcCookieConfiguration(secure=False),
        )
    )

    with TestClient(application) as client:
        started = client.get(
            "/auth/oidc/login",
            params={"return_path": "/cases/active"},
            follow_redirects=False,
        )
        assert started.status_code == 307
        state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
        login_cookie_header = started.headers["set-cookie"]
        assert client.cookies.get("csight_oidc_state") == state
        assert "HttpOnly" in login_cookie_header
        assert "Path=/auth/oidc/callback" in login_cookie_header
        assert "Max-Age=600" in login_cookie_header
        callback = client.get(
            "/auth/oidc/callback",
            params={"code": "authorization-code", "state": state},
            follow_redirects=False,
        )
        assert callback.status_code == 303
        assert callback.headers["location"] == "/cases/active"
        cookie_header = callback.headers["set-cookie"]
        raw_session_id = client.cookies.get("csight_session")
        assert raw_session_id is not None
        assert client.cookies.get("csight_oidc_state") is None
        assert cookie_header.count("csight_session=") == 1
        assert "HttpOnly" in cookie_header
        assert "csrf" not in cookie_header.lower()
        transaction = next(iter(harness.logins.records.values()))
        assert transaction.nonce not in cookie_header
        assert transaction.pkce_verifier not in cookie_header

        current = client.get("/auth/session")
        assert current.status_code == 200
        assert current.json()["principal"]["user_id"] == USER_ID
        assert current.json()["principal"]["tenant_id"] == TENANT_ID
        assert current.json()["expiry"]["expiry_warning_at"]
        assert current.json()["csrf_token"]
        stored = next(iter(harness.sessions.records.values()))
        assert (
            stored.csrf_token_hash
            == hashlib.sha256(current.json()["csrf_token"].encode()).hexdigest()
        )

        missing_csrf = client.post("/auth/logout")
        assert missing_csrf.status_code == 403
        logged_out = client.post(
            "/auth/logout",
            headers={"X-CSRF-Token": current.json()["csrf_token"]},
        )
        assert logged_out.status_code == 204
        assert client.cookies.get("csight_session") is None


def test_backchannel_logout_revokes_existing_session_and_replay_is_idempotent() -> None:
    harness = _harness()
    application = FastAPI()
    register_exception_handlers(application)
    application.include_router(
        create_oidc_router(
            service=harness.service,
            cookie=OidcCookieConfiguration(secure=False),
        )
    )

    with TestClient(application) as client:
        started = client.get(
            "/auth/oidc/login",
            params={"return_path": "/cases"},
            follow_redirects=False,
        )
        state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
        callback = client.get(
            "/auth/oidc/callback",
            params={"code": "authorization-code", "state": state},
            follow_redirects=False,
        )
        assert callback.status_code == 303
        assert client.get("/auth/session").status_code == 200

        first = client.post(
            "/auth/oidc/backchannel-logout",
            data={"logout_token": "valid-logout-token"},
        )
        replay = client.post(
            "/auth/oidc/backchannel-logout",
            data={"logout_token": "valid-logout-token"},
        )
        invalid = client.post(
            "/auth/oidc/backchannel-logout",
            data={"logout_token": "invalid-logout-token"},
        )

        assert first.status_code == 200
        assert first.headers["cache-control"] == "no-store"
        assert replay.status_code == 200
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "INVALID_OIDC_LOGOUT_TOKEN"
        assert client.get("/auth/session").status_code == 401
        assert harness.sessions.logout_jtis == {"logout-jti"}


def test_router_rejects_login_callback_not_bound_to_the_starting_browser() -> None:
    harness = _harness()
    application = FastAPI()
    register_exception_handlers(application)
    application.include_router(
        create_oidc_router(
            service=harness.service,
            cookie=OidcCookieConfiguration(secure=False),
        )
    )

    with TestClient(application) as initiating_browser:
        started = initiating_browser.get(
            "/auth/oidc/login",
            params={"return_path": "/cases/active"},
            follow_redirects=False,
        )
        state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]

        with TestClient(application) as different_browser:
            swapped = different_browser.get(
                "/auth/oidc/callback",
                params={"code": "attacker-code", "state": state},
                follow_redirects=False,
            )

        assert swapped.status_code == 401
        assert harness.backchannel.calls == []
        assert harness.sessions.records == {}

        legitimate = initiating_browser.get(
            "/auth/oidc/callback",
            params={"code": "authorization-code", "state": state},
            follow_redirects=False,
        )
        assert legitimate.status_code == 303
        assert len(harness.backchannel.calls) == 1


@pytest.mark.parametrize(
    ("oidc_enabled", "legacy_password_enabled"),
    [(True, False), (False, True), (True, True), (False, False)],
)
def test_auth_capabilities_report_only_runtime_login_methods_without_caching(
    oidc_enabled: bool,
    legacy_password_enabled: bool,
) -> None:
    application = FastAPI()
    application.include_router(
        create_auth_capabilities_router(
            oidc_enabled=oidc_enabled,
            legacy_password_enabled=legacy_password_enabled,
        )
    )

    with TestClient(application) as client:
        response = client.get("/auth/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "oidc_enabled": oidc_enabled,
        "legacy_password_enabled": legacy_password_enabled,
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_create_app_registers_exact_public_auth_paths_when_runtime_is_injected() -> None:
    harness = _harness()
    application = create_app(
        Settings(_env_file=None),  # pyright: ignore[reportCallIssue]
        oidc_runtime=OidcRuntime(
            service=harness.service,
            cookie=OidcCookieConfiguration(secure=False),
        ),
    )

    paths = set(application.openapi()["paths"])

    assert {
        "/auth/oidc/login",
        "/auth/oidc/callback",
        "/auth/session",
        "/auth/logout",
    }.issubset(paths)


def test_non_local_oidc_only_omits_password_route_and_rejects_bearer_jwt() -> None:
    harness = _harness()
    application = create_app(
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            environment="pilot",
            legacy_password_auth_enabled=False,
        ),
        oidc_runtime=OidcRuntime(
            service=harness.service,
            cookie=OidcCookieConfiguration(secure=False),
        ),
    )

    with TestClient(application) as client:
        capabilities = client.get("/auth/capabilities")
        password_login = client.post(
            "/api/v1/auth/token",
            json={"tenant_slug": "tenant-a", "email": "x@example.test", "password": "x"},
        )
        bearer = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer legacy-token"},
        )

    assert capabilities.json() == {
        "oidc_enabled": True,
        "legacy_password_enabled": False,
    }
    assert password_login.status_code == 404
    assert bearer.status_code == 401
    assert "/api/v1/auth/token" not in application.openapi()["paths"]


def test_non_local_api_startup_fails_closed_without_complete_oidc() -> None:
    with pytest.raises(OidcConfigurationError, match="required before a non-local API can start"):
        create_app(
            Settings(
                _env_file=None,  # pyright: ignore[reportCallIssue]
                environment="production",
            )
        )


def test_deployment_access_logs_cannot_capture_oidc_code_or_state_query_values() -> None:
    compose = Path("infra/compose.core.yml").read_text(encoding="utf-8")
    dockerfile = Path("infra/docker/Dockerfile").read_text(encoding="utf-8")
    nginx = Path("web/nginx/default.conf.template").read_text(encoding="utf-8")

    assert "--no-access-log" in compose
    assert '"--no-access-log"' in dockerfile
    auth_location = nginx.split("location /auth/ {", 1)[1].split("}", 1)[0]
    assert "access_log off;" in auth_location
    assert "error_log /dev/null crit;" in auth_location


def test_oidc_bootstrap_builds_pooled_runtime_without_contacting_the_provider() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        oidc_enabled=True,
        database_url="postgresql+psycopg://user:secret@invalid:5432/csight",
        oidc_issuer="https://idp.example.test",
        oidc_client_id="csight-client",
        oidc_authorization_endpoint="https://idp.example.test/authorize",
        oidc_token_endpoint="https://idp.example.test/token",
        oidc_jwks_uri="https://idp.example.test/jwks",
        oidc_redirect_uri="https://csight.example.test/auth/oidc/callback",
        oidc_group_mappings={
            "idp/reviewers": {
                "tenant_slug": "tenant-a",
                "allowed_roles": ["REVIEWER"],
            }
        },
        oidc_cookie_secure=False,
    )

    runtime = build_oidc_runtime(settings)

    assert oidc_is_configured(settings) is True
    assert isinstance(runtime.service, OidcSessionService)
    assert runtime.cookie.name == "csight_session"


class _BearerResolver:
    def execute(self, token: str) -> Principal:
        assert token == "valid-token"
        return Principal(
            user_id=USER_ID,
            tenant_id=TENANT_ID,
            email="reviewer@example.test",
            display_name="Bearer Reviewer",
            roles=frozenset({Role.REVIEWER}),
        )


def test_principal_dependency_supports_bearer_or_cookie_and_requires_csrf_for_mutation() -> None:
    harness = _harness()
    _state, raw_session_id, raw_csrf = _start_and_complete(harness)
    session_hash = hashlib.sha256(raw_session_id.encode()).hexdigest()
    initial_csrf_hash = harness.sessions.records[session_hash].csrf_token_hash
    application = FastAPI()
    register_exception_handlers(application)
    application.state.oidc_service = harness.service
    application.state.oidc_cookie_configuration = OidcCookieConfiguration(secure=False)
    application.state.sprint1_services = cast(
        Sprint1ServiceContainer,
        SimpleNamespace(resolve_principal=_BearerResolver()),
    )

    def _protected(
        principal: Annotated[Principal, Depends(provide_current_principal)],
    ) -> dict[str, str]:
        return {"user_id": principal.user_id, "tenant_id": principal.tenant_id}

    application.add_api_route("/protected", _protected, methods=["GET", "POST"])

    with TestClient(application) as client:
        client.cookies.set("csight_session", raw_session_id)
        safe = client.get("/protected")
        assert safe.status_code == 200
        assert harness.sessions.records[session_hash].csrf_token_hash == initial_csrf_hash

        assert client.post("/protected").status_code == 403
        assert (
            client.post(
                "/protected",
                headers={"X-CSRF-Token": raw_csrf},
            ).status_code
            == 200
        )

        client.cookies.set("csight_session", "invalid-session-cookie")
        bearer = client.post(
            "/protected",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert bearer.status_code == 200


def _register_sqlite_functions(dbapi_connection: object, _connection_record: object) -> None:
    connection = cast(sqlite3.Connection, dbapi_connection)
    connection.create_function("btrim", 1, _btrim)


def _btrim(value: object) -> str:
    return str(value).strip()
