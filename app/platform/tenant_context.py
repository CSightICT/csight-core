"""Technology-neutral request tenant scope shared with persistence adapters."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

_tenant_id: ContextVar[str | None] = ContextVar("csight_tenant_id", default=None)
_actor_id: ContextVar[str | None] = ContextVar("csight_actor_id", default=None)
_case_access_all: ContextVar[bool] = ContextVar("csight_case_access_all", default=False)


def current_tenant_id() -> str | None:
    return _tenant_id.get()


def current_actor_id() -> str | None:
    return _actor_id.get()


def current_case_access_all() -> bool:
    return _case_access_all.get()


@contextmanager
def tenant_context(tenant_id: str) -> Generator[None, None, None]:
    token = _tenant_id.set(str(UUID(tenant_id)))
    try:
        yield
    finally:
        _tenant_id.reset(token)


@contextmanager
def case_access_context(actor_id: str, *, can_view_all: bool) -> Generator[None, None, None]:
    actor_token = _actor_id.set(str(UUID(actor_id)))
    access_token = _case_access_all.set(can_view_all)
    try:
        yield
    finally:
        _case_access_all.reset(access_token)
        _actor_id.reset(actor_token)


@contextmanager
def system_case_access_context() -> Generator[None, None, None]:
    """Allow a tenant-bound maintenance process to read every Case without a human actor."""

    access_token = _case_access_all.set(True)
    try:
        yield
    finally:
        _case_access_all.reset(access_token)


__all__ = [
    "case_access_context",
    "current_actor_id",
    "current_case_access_all",
    "current_tenant_id",
    "system_case_access_context",
    "tenant_context",
]
