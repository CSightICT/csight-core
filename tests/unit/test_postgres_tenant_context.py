"""Network-free contracts for transaction-local tenant context validation."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.adapters.persistence.session import create_session_factory
from app.adapters.persistence.tenant_context import (
    login_tenant_context,
    oidc_session_context,
    tenant_context,
    worker_event_context,
)

pytestmark = pytest.mark.unit


def test_contexts_accept_only_bounded_opaque_identifiers() -> None:
    with tenant_context(str(uuid4())):
        pass
    with worker_event_context(str(uuid4())):
        pass
    with login_tenant_context("tenant-one"):
        pass
    with oidc_session_context("a" * 64):
        pass

    with pytest.raises(ValueError), tenant_context("not-a-uuid"):
        pass
    with pytest.raises(ValueError), worker_event_context("not-a-uuid"):
        pass
    with pytest.raises(ValueError), login_tenant_context("../tenant"):
        pass
    with pytest.raises(ValueError), oidc_session_context("short"):
        pass


def test_tenant_aware_session_keeps_non_postgres_unit_tests_network_free() -> None:
    factory = create_session_factory(create_engine("sqlite+pysqlite:///:memory:"))
    with tenant_context(str(uuid4())), factory.begin() as session:
        assert session.scalar(text("SELECT 1")) == 1
