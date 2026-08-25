"""Unit tests for the SQLAlchemy tenant identity repository."""

import sqlite3
from collections.abc import Generator
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import Table, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.identity import (
    SQLAlchemyIdentityRepository,
    SQLAlchemyIdentityRepositoryFactoryAdapter,
)
from app.adapters.persistence.models import RoleModel, TenantModel, UserModel, UserRoleModel
from app.platform.tenant import Role
from app.ports.identity import IdentityRepository

pytestmark = pytest.mark.unit


def _register_sqlite_functions(dbapi_connection: object, _connection_record: object) -> None:
    connection = cast(sqlite3.Connection, dbapi_connection)
    connection.create_function("btrim", 1, _btrim)


def _btrim(value: object) -> str:
    return str(value).strip()


@pytest.fixture
def identity_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(engine, "connect", _register_sqlite_functions)
    tables: list[Table] = [
        cast(Table, TenantModel.__table__),
        cast(Table, RoleModel.__table__),
        cast(Table, UserModel.__table__),
        cast(Table, UserRoleModel.__table__),
    ]
    TenantModel.metadata.create_all(engine, tables=tables)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_identity_rows(session: Session) -> tuple[TenantModel, UserModel, RoleModel, RoleModel]:
    tenant = TenantModel(id=uuid4(), slug="tenant-a", name="Tenant A", is_active=True)
    user = UserModel(
        id=uuid4(),
        tenant_id=tenant.id,
        email="reviewer@example.com",
        password_hash="$argon2id$test-hash",
        display_name="Reviewer",
        is_active=True,
    )
    reviewer = RoleModel(id=uuid4(), name=Role.REVIEWER.value)
    viewer = RoleModel(id=uuid4(), name=Role.QUALITY_VIEWER.value)
    session.add_all([tenant, user, reviewer, viewer])
    session.flush()
    session.add(UserRoleModel(tenant_id=tenant.id, user_id=user.id, role_id=reviewer.id))
    session.flush()
    return tenant, user, reviewer, viewer


def test_login_lookup_normalizes_identifiers_and_returns_current_snapshot(
    identity_session: Session,
) -> None:
    tenant, user, _reviewer, _viewer = _seed_identity_rows(identity_session)
    repository = SQLAlchemyIdentityRepository(identity_session)

    account = repository.find_for_login(
        tenant_slug=" TENANT-A ",
        email=" Reviewer@Example.COM ",
    )

    assert account is not None
    assert account.user_id == str(user.id)
    assert account.tenant_id == str(tenant.id)
    assert account.password_hash == "$argon2id$test-hash"
    assert account.roles == frozenset({Role.REVIEWER})
    assert account.can_authenticate is True


def test_subject_lookup_returns_inactive_state_and_reloads_current_roles(
    identity_session: Session,
) -> None:
    tenant, user, reviewer, viewer = _seed_identity_rows(identity_session)
    repository = SQLAlchemyIdentityRepository(identity_session)

    user.is_active = False
    tenant.is_active = False
    identity_session.query(UserRoleModel).filter_by(
        tenant_id=tenant.id,
        user_id=user.id,
        role_id=reviewer.id,
    ).delete()
    identity_session.add(UserRoleModel(tenant_id=tenant.id, user_id=user.id, role_id=viewer.id))
    identity_session.flush()

    account = repository.get_by_tenant_and_subject(
        tenant_id=str(tenant.id),
        subject=str(user.id),
    )

    assert account is not None
    assert account.is_active is False
    assert account.tenant_is_active is False
    assert account.roles == frozenset({Role.QUALITY_VIEWER})
    assert account.can_authenticate is False


def test_roleless_and_invalid_identity_lookups_fail_closed(identity_session: Session) -> None:
    tenant, user, reviewer, _viewer = _seed_identity_rows(identity_session)
    identity_session.query(UserRoleModel).filter_by(role_id=reviewer.id).delete()
    identity_session.flush()
    repository = SQLAlchemyIdentityRepository(identity_session)

    account = repository.get_by_tenant_and_subject(
        tenant_id=str(tenant.id),
        subject=str(user.id),
    )

    assert account is not None
    assert account.roles == frozenset()
    assert account.can_authenticate is False
    assert (
        repository.get_by_tenant_and_subject(tenant_id="not-a-uuid", subject=str(user.id)) is None
    )
    assert repository.find_for_login(tenant_slug="", email=user.email) is None


def test_factory_adapter_opens_short_sessions_and_is_safe_for_singleton_reuse(
    identity_session: Session,
) -> None:
    tenant, user, _reviewer, _viewer = _seed_identity_rows(identity_session)
    identity_session.commit()
    factory = sessionmaker(
        bind=identity_session.get_bind(),
        class_=Session,
        expire_on_commit=False,
    )
    repository = SQLAlchemyIdentityRepositoryFactoryAdapter(factory)

    first = repository.find_for_login(tenant_slug=tenant.slug, email=user.email)
    second = repository.get_by_tenant_and_subject(
        tenant_id=str(tenant.id),
        subject=str(user.id),
    )

    assert isinstance(repository, IdentityRepository)
    assert first is not None
    assert second is not None
    assert first == second
