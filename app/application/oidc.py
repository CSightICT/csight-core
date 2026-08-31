"""OIDC Authorization Code + PKCE login and hashed server-session use cases."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from app.platform.oidc import (
    InvalidOidcCallbackError,
    InvalidOidcCsrfTokenError,
    InvalidOidcLogoutTokenError,
    InvalidOidcSessionError,
    OidcAuthorizationRequest,
    OidcCodeExchangeRequest,
    OidcLoginTransaction,
    OidcLogoutRevocationResult,
    OidcProviderUnavailableError,
    OidcSession,
    ReturnPathAllowlist,
)
from app.platform.tenant import Principal, UserAccount
from app.ports.identity import IdentityRepository
from app.ports.oidc import (
    OidcLoginTransactionRepository,
    OidcProvider,
    OidcProviderError,
    OidcProviderTemporarilyUnavailableError,
    OidcSessionRepository,
    SecureTokenGenerator,
)
from app.ports.runtime import Clock, IdGenerator

OIDC_LOGIN_TRANSACTION_TTL = timedelta(minutes=10)
OIDC_SESSION_ABSOLUTE_TIMEOUT = timedelta(hours=8)
OIDC_SESSION_IDLE_TIMEOUT = timedelta(minutes=30)
OIDC_SESSION_EXPIRY_WARNING = timedelta(minutes=5)
_URLSAFE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class StartOidcLoginCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    return_path: str = Field(min_length=1, max_length=2048)


class StartOidcLoginResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_url: str = Field(min_length=1, max_length=8192, repr=False)
    browser_state: str = Field(min_length=32, max_length=512, repr=False)
    expires_at: datetime


class CompleteOidcLoginCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=4096, repr=False)
    state: str = Field(min_length=32, max_length=512, repr=False)


class OidcSessionExpiryInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    idle_expires_at: datetime
    absolute_expires_at: datetime
    effective_expires_at: datetime
    expiry_warning_at: datetime
    expires_in_seconds: int = Field(ge=0)
    expires_within_five_minutes: bool


class CompleteOidcLoginResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(min_length=32, max_length=512, repr=False)
    csrf_token: str = Field(min_length=32, max_length=512, repr=False)
    principal: Principal
    return_path: str = Field(min_length=1, max_length=2048)
    expiry: OidcSessionExpiryInfo


class ResolvedOidcSession(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    principal: Principal
    expiry: OidcSessionExpiryInfo


class RefreshedOidcSession(BaseModel):
    """Current session plus a newly rotated raw CSRF token returned once."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    csrf_token: str = Field(min_length=32, max_length=512, repr=False)
    principal: Principal
    expiry: OidcSessionExpiryInfo


class OidcSessionService:
    """Coordinate one-time login state and fixed-lifetime server-side sessions."""

    def __init__(
        self,
        *,
        login_transactions: OidcLoginTransactionRepository,
        sessions: OidcSessionRepository,
        identities: IdentityRepository,
        provider: OidcProvider,
        secure_tokens: SecureTokenGenerator,
        clock: Clock,
        id_generator: IdGenerator,
        return_paths: ReturnPathAllowlist,
        absolute_timeout: timedelta = OIDC_SESSION_ABSOLUTE_TIMEOUT,
        idle_timeout: timedelta = OIDC_SESSION_IDLE_TIMEOUT,
        expiry_warning: timedelta = OIDC_SESSION_EXPIRY_WARNING,
    ) -> None:
        if not timedelta(0) < absolute_timeout <= OIDC_SESSION_ABSOLUTE_TIMEOUT:
            raise ValueError("absolute_timeout must be positive and no greater than 8 hours")
        if not timedelta(0) < idle_timeout <= OIDC_SESSION_IDLE_TIMEOUT:
            raise ValueError("idle_timeout must be positive and no greater than 30 minutes")
        if idle_timeout > absolute_timeout:
            raise ValueError("idle_timeout must not exceed absolute_timeout")
        if not timedelta(0) < expiry_warning < idle_timeout:
            raise ValueError("expiry_warning must be positive and shorter than idle_timeout")
        self._login_transactions = login_transactions
        self._sessions = sessions
        self._identities = identities
        self._provider = provider
        self._secure_tokens = secure_tokens
        self._clock = clock
        self._id_generator = id_generator
        self._return_paths = return_paths
        self._absolute_timeout = absolute_timeout
        self._idle_timeout = idle_timeout
        self._expiry_warning = expiry_warning

    def start_login(self, command: StartOidcLoginCommand) -> StartOidcLoginResult:
        return_path = self._return_paths.require_allowed(command.return_path)
        now = _now(self._clock)
        state = self._secret(entropy_bytes=32, minimum_length=32)
        nonce = self._secret(entropy_bytes=32, minimum_length=32)
        verifier = self._secret(entropy_bytes=64, minimum_length=43)
        challenge = _pkce_challenge(verifier)
        try:
            authorization_url = self._provider.authorization_url(
                OidcAuthorizationRequest(
                    state=state,
                    nonce=nonce,
                    code_challenge=challenge,
                )
            )
        except OidcProviderTemporarilyUnavailableError as error:
            raise OidcProviderUnavailableError() from error
        expires_at = now + OIDC_LOGIN_TRANSACTION_TTL
        self._login_transactions.add(
            OidcLoginTransaction(
                transaction_id=self._id_generator.new_id(),
                provider_key=self._provider.provider_key,
                state_hash=_secret_hash(state),
                nonce=nonce,
                pkce_verifier=verifier,
                return_path=return_path,
                created_at=now,
                expires_at=expires_at,
            )
        )
        return StartOidcLoginResult(
            authorization_url=authorization_url,
            browser_state=state,
            expires_at=expires_at,
        )

    def complete_login(self, command: CompleteOidcLoginCommand) -> CompleteOidcLoginResult:
        now = _now(self._clock)
        transaction = self._login_transactions.consume(
            state_hash=_secret_hash(command.state),
            now=now,
        )
        if transaction is None or transaction.provider_key != self._provider.provider_key:
            raise InvalidOidcCallbackError()
        try:
            identity = self._provider.exchange_code(
                OidcCodeExchangeRequest(
                    code=command.code,
                    pkce_verifier=transaction.pkce_verifier,
                    expected_nonce=transaction.nonce,
                )
            )
        except OidcProviderTemporarilyUnavailableError as error:
            raise OidcProviderUnavailableError() from error
        except OidcProviderError as error:
            raise InvalidOidcCallbackError() from error
        if not hmac.compare_digest(
            identity.nonce.encode("utf-8"),
            transaction.nonce.encode("utf-8"),
        ):
            raise InvalidOidcCallbackError()

        account = self._active_account(identity.tenant_id, identity.user_id)
        if (
            account is None
            or not identity.email_verified
            or not hmac.compare_digest(
                identity.email.casefold().encode("utf-8"),
                account.email.casefold().encode("utf-8"),
            )
        ):
            raise InvalidOidcCallbackError()
        principal = _principal(account)

        raw_session_id = self._secret(entropy_bytes=48, minimum_length=32)
        raw_csrf_token = self._secret(entropy_bytes=32, minimum_length=32)
        absolute_expires_at = now + self._absolute_timeout
        idle_expires_at = min(now + self._idle_timeout, absolute_expires_at)
        session = OidcSession(
            session_record_id=self._id_generator.new_id(),
            session_id_hash=_secret_hash(raw_session_id),
            csrf_token_hash=_secret_hash(raw_csrf_token),
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            provider_issuer=identity.issuer,
            provider_subject=identity.subject,
            provider_session_id=identity.session_id,
            created_at=now,
            last_seen_at=now,
            idle_expires_at=idle_expires_at,
            absolute_expires_at=absolute_expires_at,
        )
        self._sessions.add(session)
        return CompleteOidcLoginResult(
            session_id=raw_session_id,
            csrf_token=raw_csrf_token,
            principal=principal,
            return_path=transaction.return_path,
            expiry=_expiry_info(session, now, warning_window=self._expiry_warning),
        )

    def resolve_session(self, *, session_id: str) -> RefreshedOidcSession:
        now = _now(self._clock)
        raw_csrf_token = self._secret(entropy_bytes=32, minimum_length=32)
        session = self._sessions.rotate_csrf_and_touch(
            session_id_hash=_secret_hash(session_id),
            new_csrf_token_hash=_secret_hash(raw_csrf_token),
            now=now,
            idle_timeout=self._idle_timeout,
        )
        resolved = self._resolve_active(session, now=now)
        return RefreshedOidcSession(
            csrf_token=raw_csrf_token,
            principal=resolved.principal,
            expiry=resolved.expiry,
        )

    def authenticate_without_rotation(self, *, session_id: str) -> ResolvedOidcSession:
        """Authenticate an ordinary request while preserving the current CSRF bearer."""

        now = _now(self._clock)
        session = self._sessions.get_and_touch(
            session_id_hash=_secret_hash(session_id),
            now=now,
            idle_timeout=self._idle_timeout,
        )
        return self._resolve_active(session, now=now)

    def validate_csrf(self, *, session_id: str, csrf_token: str) -> ResolvedOidcSession:
        now = _now(self._clock)
        session = self._sessions.validate_csrf_and_touch(
            session_id_hash=_secret_hash(session_id),
            csrf_token_hash=_secret_hash(csrf_token),
            now=now,
            idle_timeout=self._idle_timeout,
        )
        if session is None:
            raise InvalidOidcCsrfTokenError()
        return self._resolve_active(session, now=now)

    def logout(self, *, session_id: str, csrf_token: str) -> None:
        self.validate_csrf(session_id=session_id, csrf_token=csrf_token)
        self._sessions.revoke(
            session_id_hash=_secret_hash(session_id),
            now=_now(self._clock),
            reason="LOGOUT",
        )

    def backchannel_logout(self, *, logout_token: str) -> OidcLogoutRevocationResult:
        """Validate one provider push and revoke its matching server sessions atomically."""

        if not 1 <= len(logout_token) <= 65536:
            raise InvalidOidcLogoutTokenError()
        try:
            logout = self._provider.validate_logout_token(logout_token)
        except OidcProviderTemporarilyUnavailableError as error:
            raise OidcProviderUnavailableError() from error
        except OidcProviderError as error:
            raise InvalidOidcLogoutTokenError() from error
        return self._sessions.revoke_by_provider_logout(
            logout=logout,
            now=_now(self._clock),
        )

    def _resolve_active(
        self,
        session: OidcSession | None,
        *,
        now: datetime,
    ) -> ResolvedOidcSession:
        if session is None:
            raise InvalidOidcSessionError()
        account = self._active_account(session.tenant_id, session.user_id)
        if account is None:
            self._sessions.revoke(
                session_id_hash=session.session_id_hash,
                now=now,
                reason="IDENTITY_INACTIVE",
            )
            raise InvalidOidcSessionError()
        return ResolvedOidcSession(
            principal=_principal(account),
            expiry=_expiry_info(session, now, warning_window=self._expiry_warning),
        )

    def _active_account(self, tenant_id: str, user_id: str) -> UserAccount | None:
        account = self._identities.get_by_tenant_and_subject(
            tenant_id=tenant_id,
            subject=user_id,
        )
        if (
            account is None
            or account.tenant_id != tenant_id
            or account.user_id != user_id
            or not account.can_authenticate
        ):
            return None
        return account

    def _secret(self, *, entropy_bytes: int, minimum_length: int) -> str:
        value = self._secure_tokens.token_urlsafe(entropy_bytes=entropy_bytes)
        if (
            len(value) < minimum_length
            or len(value) > 512
            or _URLSAFE_TOKEN_PATTERN.fullmatch(value) is None
        ):
            raise ValueError("secure token generator returned an invalid value")
        return value


def _now(clock: Clock) -> datetime:
    value = clock.now()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


def _secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _principal(account: UserAccount) -> Principal:
    return Principal(
        user_id=account.user_id,
        tenant_id=account.tenant_id,
        email=account.email,
        display_name=account.display_name,
        roles=account.roles,
    )


def _expiry_info(
    session: OidcSession,
    now: datetime,
    *,
    warning_window: timedelta,
) -> OidcSessionExpiryInfo:
    effective_expires_at = session.effective_expires_at
    warning_at = effective_expires_at - warning_window
    remaining = max(0, int((effective_expires_at - now).total_seconds()))
    return OidcSessionExpiryInfo(
        idle_expires_at=session.idle_expires_at,
        absolute_expires_at=session.absolute_expires_at,
        effective_expires_at=effective_expires_at,
        expiry_warning_at=warning_at,
        expires_in_seconds=remaining,
        expires_within_five_minutes=now >= warning_at,
    )
