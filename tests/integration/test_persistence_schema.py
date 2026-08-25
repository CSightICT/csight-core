"""Opt-in PostgreSQL verification for the Sprint 1 migrated schema."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, inspect
from sqlalchemy.engine.interfaces import ReflectedForeignKeyConstraint

from alembic import command
from app.adapters.persistence.engine import clear_engine_cache, get_engine
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "tenants",
    "users",
    "roles",
    "user_roles",
    "cases",
    "case_evidence",
    "case_status_history",
    "idempotency_records",
}


@pytest.fixture(scope="module")
def migrated_engine() -> Generator[Engine, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to verify the migrated schema")

    settings = Settings()
    database_url = settings.database_url_value
    if not database_url:
        pytest.fail("DATABASE_URL is required for persistence integration tests")

    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")

    engine = get_engine(settings)
    try:
        yield engine
    finally:
        clear_engine_cache()


def _foreign_keys_by_name(
    engine: Engine,
    table_name: str,
) -> dict[str, ReflectedForeignKeyConstraint]:
    return {
        str(foreign_key["name"]): foreign_key
        for foreign_key in inspect(engine).get_foreign_keys(table_name)
    }


def test_migration_creates_all_sprint_1_tables(migrated_engine: Engine) -> None:
    assert EXPECTED_TABLES.issubset(inspect(migrated_engine).get_table_names())


def test_database_enforces_composite_tenant_foreign_keys(migrated_engine: Engine) -> None:
    case_evidence_foreign_keys = _foreign_keys_by_name(migrated_engine, "case_evidence")
    case_history_foreign_keys = _foreign_keys_by_name(
        migrated_engine,
        "case_status_history",
    )
    idempotency_foreign_keys = _foreign_keys_by_name(
        migrated_engine,
        "idempotency_records",
    )

    evidence_case = case_evidence_foreign_keys["fk_case_evidence_tenant_id_case_id_cases"]
    assert evidence_case["constrained_columns"] == ["tenant_id", "case_id"]
    assert evidence_case["referred_table"] == "cases"
    assert evidence_case["referred_columns"] == ["tenant_id", "id"]

    history_actor = case_history_foreign_keys["fk_case_status_history_tenant_id_actor_id_users"]
    assert history_actor["constrained_columns"] == ["tenant_id", "actor_id"]
    assert history_actor["referred_table"] == "users"
    assert history_actor["referred_columns"] == ["tenant_id", "id"]

    idempotency_case = idempotency_foreign_keys[
        "fk_idempotency_records_tenant_id_resource_id_cases"
    ]
    assert idempotency_case["constrained_columns"] == ["tenant_id", "resource_id"]
    assert idempotency_case["referred_table"] == "cases"
    assert idempotency_case["referred_columns"] == ["tenant_id", "id"]
    idempotency_options = idempotency_case.get("options") or {}
    assert idempotency_options.get("deferrable") is True
    assert idempotency_options.get("initially") == "DEFERRED"
    assert idempotency_options.get("ondelete") == "RESTRICT"


def test_database_has_named_checks_and_idempotency_uniqueness(
    migrated_engine: Engine,
) -> None:
    inspector = inspect(migrated_engine)
    case_checks = {check["name"] for check in inspector.get_check_constraints("cases")}
    idempotency_uniques = {
        unique["name"]: unique["column_names"]
        for unique in inspector.get_unique_constraints("idempotency_records")
    }

    assert "ck_cases_status_allowed" in case_checks
    assert "ck_cases_requested_action_allowed" in case_checks
    assert idempotency_uniques["uq_idempotency_records_tenant_operation_key"] == [
        "tenant_id",
        "operation",
        "idempotency_key",
    ]
