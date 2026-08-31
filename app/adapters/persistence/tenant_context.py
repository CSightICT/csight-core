"""Transaction-local PostgreSQL contexts used by fail-closed RLS policies.

The context variables keep infrastructure details out of application and domain
objects.  ``TenantAwareSession`` copies only validated opaque identifiers into
PostgreSQL with ``set_config(..., true)`` when a transaction starts.  The final
``true`` makes every value transaction-local, so pooled connections cannot leak
one request's tenant into the next request.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from re import Pattern
from re import compile as compile_pattern
from uuid import UUID

from sqlalchemy import Connection, event
from sqlalchemy.orm import Session
from sqlalchemy.orm.session import SessionTransaction

from app.platform.tenant_context import (
    case_access_context,
    current_actor_id,
    current_case_access_all,
    current_tenant_id,
    system_case_access_context,
    tenant_context,
)

TENANT_SETTING = "app.tenant_id"
LOGIN_TENANT_SLUG_SETTING = "app.login_tenant_slug"
OIDC_SESSION_HASH_SETTING = "app.oidc_session_hash"
OIDC_LOGOUT_SUBJECT_HASH_SETTING = "app.oidc_logout_subject_hash"
OIDC_LOGOUT_SESSION_HASH_SETTING = "app.oidc_logout_session_hash"
WORKER_EVENT_ID_SETTING = "app.worker_event_id"
ACTOR_ID_SETTING = "app.actor_id"
CASE_ACCESS_ALL_SETTING = "app.case_access_all"

_login_tenant_slug: ContextVar[str | None] = ContextVar("csight_login_tenant_slug", default=None)
_oidc_session_hash: ContextVar[str | None] = ContextVar("csight_oidc_session_hash", default=None)
_oidc_logout_subject_hash: ContextVar[str | None] = ContextVar(
    "csight_oidc_logout_subject_hash",
    default=None,
)
_oidc_logout_session_hash: ContextVar[str | None] = ContextVar(
    "csight_oidc_logout_session_hash",
    default=None,
)
_worker_event_id: ContextVar[str | None] = ContextVar("csight_worker_event_id", default=None)

_SLUG_PATTERN: Pattern[str] = compile_pattern(r"^[a-z0-9][a-z0-9-]{0,62}$")
_HASH_PATTERN: Pattern[str] = compile_pattern(r"^[0-9a-f]{64}$")


class TenantAwareSession(Session):
    """Session subclass that applies validated ContextVar values after BEGIN."""


def _uuid(value: str) -> str:
    return str(UUID(value))


def _slug(value: str) -> str:
    normalized = value.strip().lower()
    if _SLUG_PATTERN.fullmatch(normalized) is None:
        raise ValueError("tenant slug is invalid")
    return normalized


def _hash(value: str) -> str:
    normalized = value.strip().lower()
    if _HASH_PATTERN.fullmatch(normalized) is None:
        raise ValueError("session hash is invalid")
    return normalized


def _set_local(connection: Connection, setting: str, value: str) -> None:
    if connection.dialect.name != "postgresql":
        return
    connection.exec_driver_sql(
        "SELECT set_config(%s, %s, true)",
        (setting, value),
    )


@event.listens_for(TenantAwareSession, "after_begin")
def apply_transaction_context(
    _session: Session,
    _transaction: SessionTransaction,
    connection: Connection,
) -> None:
    values = (
        (TENANT_SETTING, current_tenant_id()),
        (ACTOR_ID_SETTING, current_actor_id()),
        (CASE_ACCESS_ALL_SETTING, "true" if current_case_access_all() else "false"),
        (LOGIN_TENANT_SLUG_SETTING, _login_tenant_slug.get()),
        (OIDC_SESSION_HASH_SETTING, _oidc_session_hash.get()),
        (OIDC_LOGOUT_SUBJECT_HASH_SETTING, _oidc_logout_subject_hash.get()),
        (OIDC_LOGOUT_SESSION_HASH_SETTING, _oidc_logout_session_hash.get()),
        (WORKER_EVENT_ID_SETTING, _worker_event_id.get()),
    )
    for setting, value in values:
        if value is not None:
            _set_local(connection, setting, value)


@contextmanager
def login_tenant_context(tenant_slug: str) -> Generator[None, None, None]:
    token = _login_tenant_slug.set(_slug(tenant_slug))
    try:
        yield
    finally:
        _login_tenant_slug.reset(token)


@contextmanager
def oidc_session_context(session_id_hash: str) -> Generator[None, None, None]:
    token = _oidc_session_hash.set(_hash(session_id_hash))
    try:
        yield
    finally:
        _oidc_session_hash.reset(token)


@contextmanager
def oidc_logout_context(
    *,
    subject_hash: str | None,
    session_hash: str | None,
) -> Generator[None, None, None]:
    if subject_hash is None and session_hash is None:
        raise ValueError("OIDC logout context requires a subject or session hash")
    subject_token = (
        _oidc_logout_subject_hash.set(_hash(subject_hash)) if subject_hash is not None else None
    )
    session_token = (
        _oidc_logout_session_hash.set(_hash(session_hash)) if session_hash is not None else None
    )
    try:
        yield
    finally:
        if session_token is not None:
            _oidc_logout_session_hash.reset(session_token)
        if subject_token is not None:
            _oidc_logout_subject_hash.reset(subject_token)


@contextmanager
def worker_event_context(event_id: str) -> Generator[None, None, None]:
    token = _worker_event_id.set(_uuid(event_id))
    try:
        yield
    finally:
        _worker_event_id.reset(token)


def set_tenant_context(session: Session, tenant_id: str) -> None:
    """Explicitly bind a tenant to an already-open transaction.

    Most HTTP and Worker paths use ``tenant_context`` before the session starts.
    This helper is the repository/UoW escape hatch for a transaction whose tenant
    becomes known only after a non-tenant lookup.
    """

    _set_local(session.connection(), TENANT_SETTING, _uuid(tenant_id))


__all__ = [
    "TenantAwareSession",
    "apply_transaction_context",
    "case_access_context",
    "login_tenant_context",
    "oidc_logout_context",
    "oidc_session_context",
    "set_tenant_context",
    "system_case_access_context",
    "tenant_context",
    "worker_event_context",
]
