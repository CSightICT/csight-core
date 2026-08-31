"""SQLAlchemy persistence for one-time OIDC logins and hashed browser sessions."""

from __future__ import annotations

import hmac
import re
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    select,
    text,
    update,
)
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from app.adapters.persistence.base import Base
from app.adapters.persistence.tenant_context import (
    oidc_logout_context,
    oidc_session_context,
    tenant_context,
)
from app.platform.oidc import (
    OidcLoginTransaction,
    OidcLogoutRevocationResult,
    OidcPersistenceConflictError,
    OidcSession,
    ValidatedOidcLogoutToken,
    oidc_provider_binding_hash,
)

_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REVOCATION_REASON_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_DUMMY_HASH = "0" * 64


class OidcLoginTransactionModel(Base):
    __tablename__ = "oidc_login_transactions"
    __table_args__ = (
        CheckConstraint("length(btrim(provider_key)) > 0", name="provider_key_nonempty"),
        CheckConstraint(
            "state_hash ~ '^[0-9a-f]{64}$'",
            name="state_hash_valid",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("length(nonce) BETWEEN 32 AND 512", name="nonce_length"),
        CheckConstraint(
            "length(pkce_verifier) BETWEEN 43 AND 128",
            name="pkce_verifier_length",
        ),
        CheckConstraint(
            "length(return_path) BETWEEN 1 AND 2048 AND left(return_path, 1) = '/'",
            name="return_path_relative",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        CheckConstraint(
            "consumed_at IS NULL OR (consumed_at >= created_at AND consumed_at <= expires_at)",
            name="consumed_within_lifetime",
        ),
        UniqueConstraint("state_hash", name="uq_oidc_login_transactions_state_hash"),
        Index(
            "ix_oidc_login_transactions_pending_expiry",
            "expires_at",
            postgresql_where=text("consumed_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce: Mapped[str] = mapped_column(String(512), nullable=False)
    pkce_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    return_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OidcSessionModel(Base):
    __tablename__ = "oidc_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "user_id"),
            ("users.tenant_id", "users.id"),
            name="fk_oidc_sessions_tenant_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "session_id_hash ~ '^[0-9a-f]{64}$'",
            name="session_id_hash_valid",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "csrf_token_hash ~ '^[0-9a-f]{64}$'",
            name="csrf_token_hash_valid",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "provider_subject_hash ~ '^[0-9a-f]{64}$'",
            name="provider_subject_hash_valid",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "provider_session_hash IS NULL OR provider_session_hash ~ '^[0-9a-f]{64}$'",
            name="provider_session_hash_valid",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("last_seen_at >= created_at", name="last_seen_after_creation"),
        CheckConstraint(
            "absolute_expires_at > created_at "
            "AND absolute_expires_at <= created_at + INTERVAL '8 hours'",
            name="absolute_lifetime_max_eight_hours",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "idle_expires_at > last_seen_at "
            "AND idle_expires_at <= last_seen_at + INTERVAL '30 minutes' "
            "AND idle_expires_at <= absolute_expires_at",
            name="idle_lifetime_thirty_minutes",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "(revoked_at IS NULL AND revocation_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)",
            name="revocation_state_consistent",
        ),
        UniqueConstraint("session_id_hash", name="uq_oidc_sessions_session_id_hash"),
        Index(
            "ix_oidc_sessions_active_expiry",
            "idle_expires_at",
            "absolute_expires_at",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index("ix_oidc_sessions_tenant_user", "tenant_id", "user_id"),
        Index(
            "ix_oidc_sessions_active_provider_subject",
            "provider_subject_hash",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "ix_oidc_sessions_active_provider_session",
            "provider_session_hash",
            postgresql_where=text("revoked_at IS NULL AND provider_session_hash IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    session_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    provider_issuer: Mapped[str] = mapped_column(String(2048), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(512), nullable=False)
    provider_session_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    provider_subject_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_session_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)


class OidcLogoutEventModel(Base):
    """PII-minimized append-only receipt for one validated provider logout token."""

    __tablename__ = "oidc_logout_events"
    __table_args__ = (
        CheckConstraint(
            "token_jti_hash ~ '^[0-9a-f]{64}$'",
            name="token_jti_hash_valid",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "provider_subject_hash IS NULL OR provider_subject_hash ~ '^[0-9a-f]{64}$'",
            name="provider_subject_hash_valid",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "provider_session_hash IS NULL OR provider_session_hash ~ '^[0-9a-f]{64}$'",
            name="provider_session_hash_valid",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "provider_subject_hash IS NOT NULL OR provider_session_hash IS NOT NULL",
            name="provider_target_present",
        ),
        CheckConstraint(
            "revoked_session_count >= 0",
            name="revoked_session_count_nonnegative",
        ),
        UniqueConstraint("token_jti_hash", name="uq_oidc_logout_events_token_jti_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    provider_issuer: Mapped[str] = mapped_column(String(2048), nullable=False)
    provider_subject_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_session_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_jti_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_session_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SQLAlchemyOidcRepository:
    """Own short DB transactions and lock one-time or mutable auth rows."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, value: OidcLoginTransaction | OidcSession) -> None:
        try:
            if isinstance(value, OidcLoginTransaction):
                with self._session_factory() as database, database.begin():
                    database.add(_login_model(value))
            else:
                with (
                    tenant_context(value.tenant_id),
                    self._session_factory() as database,
                    database.begin(),
                ):
                    database.add(_session_model(value))
        except IntegrityError as error:
            raise OidcPersistenceConflictError() from error

    def consume(self, *, state_hash: str, now: datetime) -> OidcLoginTransaction | None:
        checked_at = _utc(now)
        if _HASH_PATTERN.fullmatch(state_hash) is None:
            return None
        with self._session_factory() as database, database.begin():
            model = database.scalar(
                select(OidcLoginTransactionModel)
                .where(OidcLoginTransactionModel.state_hash == state_hash)
                .with_for_update()
            )
            if (
                model is None
                or model.consumed_at is not None
                or checked_at >= _utc(model.expires_at)
            ):
                return None
            model.consumed_at = checked_at
            database.flush()
            return _login_entity(model)

    def get_and_touch(
        self,
        *,
        session_id_hash: str,
        now: datetime,
        idle_timeout: timedelta,
    ) -> OidcSession | None:
        return self._validate_and_touch(
            session_id_hash=session_id_hash,
            csrf_token_hash=None,
            replacement_csrf_token_hash=None,
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
        return self._validate_and_touch(
            session_id_hash=session_id_hash,
            csrf_token_hash=csrf_token_hash,
            replacement_csrf_token_hash=None,
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
        return self._validate_and_touch(
            session_id_hash=session_id_hash,
            csrf_token_hash=None,
            replacement_csrf_token_hash=new_csrf_token_hash,
            now=now,
            idle_timeout=idle_timeout,
        )

    def revoke(
        self,
        *,
        session_id_hash: str,
        now: datetime,
        reason: str,
    ) -> bool:
        checked_at = _utc(now)
        if (
            _HASH_PATTERN.fullmatch(session_id_hash) is None
            or _REVOCATION_REASON_PATTERN.fullmatch(reason) is None
        ):
            return False
        with (
            oidc_session_context(session_id_hash),
            self._session_factory() as database,
            database.begin(),
        ):
            model = database.scalar(
                select(OidcSessionModel)
                .where(OidcSessionModel.session_id_hash == session_id_hash)
                .with_for_update()
            )
            if model is None:
                return False
            if model.revoked_at is None:
                model.revoked_at = checked_at
                model.revocation_reason = reason
                database.flush()
            return True

    def revoke_by_provider_logout(
        self,
        *,
        logout: ValidatedOidcLogoutToken,
        now: datetime,
    ) -> OidcLogoutRevocationResult:
        checked_at = _utc(now)
        subject_hash = (
            oidc_provider_binding_hash(logout.issuer, logout.subject)
            if logout.subject is not None
            else None
        )
        session_hash = (
            oidc_provider_binding_hash(logout.issuer, logout.session_id)
            if logout.session_id is not None
            else None
        )
        jti_hash = oidc_provider_binding_hash(logout.issuer, logout.jwt_id)
        with (
            oidc_logout_context(subject_hash=subject_hash, session_hash=session_hash),
            self._session_factory() as database,
            database.begin(),
        ):
            event_model = OidcLogoutEventModel(
                id=uuid4(),
                provider_issuer=logout.issuer,
                provider_subject_hash=subject_hash,
                provider_session_hash=session_hash,
                token_jti_hash=jti_hash,
                received_at=checked_at,
                revoked_session_count=0,
            )
            try:
                with database.begin_nested():
                    database.add(event_model)
                    database.flush()
            except IntegrityError:
                return OidcLogoutRevocationResult(revoked_session_count=0, replayed=True)

            predicate = self._provider_logout_predicate(
                subject_hash=subject_hash,
                session_hash=session_hash,
            )
            result = cast(
                CursorResult[Any],
                database.execute(
                    update(OidcSessionModel)
                    .where(
                        OidcSessionModel.provider_issuer == logout.issuer,
                        OidcSessionModel.revoked_at.is_(None),
                        predicate,
                    )
                    .values(
                        revoked_at=checked_at,
                        revocation_reason="OIDC_BACKCHANNEL_LOGOUT",
                    )
                ),
            )
            revoked_count = int(result.rowcount or 0)
            event_model.revoked_session_count = revoked_count
            database.flush()
            return OidcLogoutRevocationResult(
                revoked_session_count=revoked_count,
                replayed=False,
            )

    @staticmethod
    def _provider_logout_predicate(
        *,
        subject_hash: str | None,
        session_hash: str | None,
    ) -> ColumnElement[bool]:
        if session_hash is None:
            if subject_hash is None:
                raise ValueError("OIDC logout target is missing")
            return OidcSessionModel.provider_subject_hash == subject_hash
        exact_session = OidcSessionModel.provider_session_hash == session_hash
        if subject_hash is None:
            return exact_session
        legacy_subject = OidcSessionModel.provider_session_hash.is_(None) & (
            OidcSessionModel.provider_subject_hash == subject_hash
        )
        return exact_session | legacy_subject

    def _validate_and_touch(
        self,
        *,
        session_id_hash: str,
        csrf_token_hash: str | None,
        replacement_csrf_token_hash: str | None,
        now: datetime,
        idle_timeout: timedelta,
    ) -> OidcSession | None:
        checked_at = _utc(now)
        if idle_timeout <= timedelta(0):
            raise ValueError("idle_timeout must be positive")
        valid_session_hash = _HASH_PATTERN.fullmatch(session_id_hash) is not None
        valid_csrf_hash = (
            csrf_token_hash is None or _HASH_PATTERN.fullmatch(csrf_token_hash) is not None
        )
        valid_replacement_hash = (
            replacement_csrf_token_hash is None
            or _HASH_PATTERN.fullmatch(replacement_csrf_token_hash) is not None
        )
        session_scope = (
            oidc_session_context(session_id_hash)
            if valid_session_hash
            else oidc_session_context(_DUMMY_HASH)
        )
        with session_scope, self._session_factory() as database, database.begin():
            model = None
            if valid_session_hash:
                model = database.scalar(
                    select(OidcSessionModel)
                    .where(OidcSessionModel.session_id_hash == session_id_hash)
                    .with_for_update()
                )
            expected_csrf = model.csrf_token_hash if model is not None else _DUMMY_HASH
            presented_csrf = csrf_token_hash if valid_csrf_hash and csrf_token_hash else _DUMMY_HASH
            csrf_matches = csrf_token_hash is None or hmac.compare_digest(
                expected_csrf,
                presented_csrf,
            )
            if (
                model is None
                or not csrf_matches
                or not valid_replacement_hash
                or model.revoked_at is not None
            ):
                return None

            effective_expires_at = min(
                _utc(model.idle_expires_at),
                _utc(model.absolute_expires_at),
            )
            if checked_at >= effective_expires_at:
                model.revoked_at = checked_at
                model.revocation_reason = "EXPIRED"
                database.flush()
                return None

            model.last_seen_at = checked_at
            model.idle_expires_at = min(
                checked_at + idle_timeout,
                _utc(model.absolute_expires_at),
            )
            if replacement_csrf_token_hash is not None:
                model.csrf_token_hash = replacement_csrf_token_hash
            database.flush()
            return _session_entity(model)


def _login_model(value: OidcLoginTransaction) -> OidcLoginTransactionModel:
    return OidcLoginTransactionModel(
        id=UUID(value.transaction_id),
        provider_key=value.provider_key,
        state_hash=value.state_hash,
        nonce=value.nonce,
        pkce_verifier=value.pkce_verifier,
        return_path=value.return_path,
        created_at=value.created_at,
        expires_at=value.expires_at,
        consumed_at=value.consumed_at,
    )


def _session_model(value: OidcSession) -> OidcSessionModel:
    return OidcSessionModel(
        id=UUID(value.session_record_id),
        session_id_hash=value.session_id_hash,
        csrf_token_hash=value.csrf_token_hash,
        tenant_id=UUID(value.tenant_id),
        user_id=UUID(value.user_id),
        provider_issuer=value.provider_issuer,
        provider_subject=value.provider_subject,
        provider_session_id=value.provider_session_id,
        provider_subject_hash=oidc_provider_binding_hash(
            value.provider_issuer,
            value.provider_subject,
        ),
        provider_session_hash=(
            oidc_provider_binding_hash(value.provider_issuer, value.provider_session_id)
            if value.provider_session_id is not None
            else None
        ),
        created_at=value.created_at,
        last_seen_at=value.last_seen_at,
        idle_expires_at=value.idle_expires_at,
        absolute_expires_at=value.absolute_expires_at,
        revoked_at=value.revoked_at,
        revocation_reason=value.revocation_reason,
    )


def _login_entity(model: OidcLoginTransactionModel) -> OidcLoginTransaction:
    return OidcLoginTransaction(
        transaction_id=str(model.id),
        provider_key=model.provider_key,
        state_hash=model.state_hash,
        nonce=model.nonce,
        pkce_verifier=model.pkce_verifier,
        return_path=model.return_path,
        created_at=_utc(model.created_at),
        expires_at=_utc(model.expires_at),
        consumed_at=_utc(model.consumed_at) if model.consumed_at is not None else None,
    )


def _session_entity(model: OidcSessionModel) -> OidcSession:
    return OidcSession(
        session_record_id=str(model.id),
        session_id_hash=model.session_id_hash,
        csrf_token_hash=model.csrf_token_hash,
        tenant_id=str(model.tenant_id),
        user_id=str(model.user_id),
        provider_issuer=model.provider_issuer,
        provider_subject=model.provider_subject,
        provider_session_id=model.provider_session_id,
        created_at=_utc(model.created_at),
        last_seen_at=_utc(model.last_seen_at),
        idle_expires_at=_utc(model.idle_expires_at),
        absolute_expires_at=_utc(model.absolute_expires_at),
        revoked_at=_utc(model.revoked_at) if model.revoked_at is not None else None,
        revocation_reason=model.revocation_reason,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
