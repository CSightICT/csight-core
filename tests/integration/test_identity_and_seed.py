"""Opt-in PostgreSQL integration coverage for identity lookup and seed idempotency."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from alembic import command
from app.adapters.persistence.engine import clear_engine_cache, get_engine
from app.adapters.persistence.identity import SQLAlchemyIdentityRepository
from app.adapters.persistence.models import RoleModel, UserModel, UserRoleModel
from app.adapters.security import Argon2PasswordHasher
from app.bootstrap.seed import (
    DevelopmentSeedPasswords,
    DevelopmentSeedPlan,
    DevelopmentSeedUser,
    seed_development_identities,
)
from app.bootstrap.settings import Settings
from app.platform.tenant import Role

pytestmark = pytest.mark.integration

INTEGRATION_PLAN = DevelopmentSeedPlan(
    tenant_slug="csight-integration-seed",
    tenant_name="CSight Integration Seed",
    users=(
        DevelopmentSeedUser(
            email="admin@integration.test",
            display_name="Integration Admin",
            role=Role.ADMIN,
        ),
        DevelopmentSeedUser(
            email="reviewer@integration.test",
            display_name="Integration Reviewer",
            role=Role.REVIEWER,
        ),
        DevelopmentSeedUser(
            email="viewer@integration.test",
            display_name="Integration Viewer",
            role=Role.QUALITY_VIEWER,
        ),
    ),
)
INTEGRATION_PASSWORDS = DevelopmentSeedPasswords(
    admin=SecretStr("a" * 20),
    reviewer=SecretStr("r" * 20),
    quality_viewer=SecretStr("q" * 20),
)


@pytest.fixture(scope="module")
def migrated_engine() -> Generator[Engine, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to verify identity persistence")
    settings = Settings()
    database_url = settings.database_url_value
    if not database_url:
        pytest.fail("DATABASE_URL is required for identity integration tests")

    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    engine = get_engine(settings)
    try:
        yield engine
    finally:
        clear_engine_cache()


def test_seed_is_idempotent_and_identity_reads_current_security_state(
    migrated_engine: Engine,
) -> None:
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    hasher = Argon2PasswordHasher()
    try:
        first = seed_development_identities(
            session=session,
            password_hasher=hasher,
            passwords=INTEGRATION_PASSWORDS,
            plan=INTEGRATION_PLAN,
        )
        first_hashes = {
            email: password_hash
            for email, password_hash in session.execute(
                select(UserModel.email, UserModel.password_hash).where(
                    UserModel.tenant_id == first.tenant_id
                )
            )
        }
        second = seed_development_identities(
            session=session,
            password_hasher=hasher,
            passwords=INTEGRATION_PASSWORDS,
            plan=INTEGRATION_PLAN,
        )
        second_hashes = {
            email: password_hash
            for email, password_hash in session.execute(
                select(UserModel.email, UserModel.password_hash).where(
                    UserModel.tenant_id == first.tenant_id
                )
            )
        }

        assert second == first
        assert second_hashes == first_hashes
        assert len(first.user_ids) == 3

        repository = SQLAlchemyIdentityRepository(session)
        reviewer = repository.find_for_login(
            tenant_slug=" CSIGHT-INTEGRATION-SEED ",
            email=" REVIEWER@INTEGRATION.TEST ",
        )
        assert reviewer is not None
        assert reviewer.roles == frozenset({Role.REVIEWER})
        assert hasher.verify_password("r" * 20, reviewer.password_hash)

        role_ids = {
            name: role_id for name, role_id in session.execute(select(RoleModel.name, RoleModel.id))
        }
        reviewer_model = session.scalar(
            select(UserModel).where(
                UserModel.tenant_id == first.tenant_id,
                UserModel.email == "reviewer@integration.test",
            )
        )
        assert reviewer_model is not None
        session.execute(
            delete(UserRoleModel).where(
                UserRoleModel.tenant_id == first.tenant_id,
                UserRoleModel.user_id == reviewer_model.id,
            )
        )
        session.add(
            UserRoleModel(
                tenant_id=first.tenant_id,
                user_id=reviewer_model.id,
                role_id=role_ids[Role.QUALITY_VIEWER.value],
            )
        )
        reviewer_model.is_active = False
        session.flush()

        current = repository.get_by_tenant_and_subject(
            tenant_id=str(first.tenant_id),
            subject=str(reviewer_model.id),
        )
        assert current is not None
        assert current.roles == frozenset({Role.QUALITY_VIEWER})
        assert current.is_active is False
        assert current.can_authenticate is False
    finally:
        session.close()
        transaction.rollback()
        connection.close()
