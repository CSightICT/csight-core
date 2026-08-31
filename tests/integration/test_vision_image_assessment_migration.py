"""Disposable PostgreSQL lifecycle gate for image-level Vision assessment."""

from __future__ import annotations

import os
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from alembic import command
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = "20260827_0014_review_report_poc_metrics"
REVISION = "20260827_0015_vision_image_assessment"
HEAD = "head"


@dataclass(frozen=True, slots=True)
class MigrationDatabase:
    config: Config
    engine: Engine


@pytest.fixture(scope="module")
def migration_database() -> Generator[MigrationDatabase, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test migration 0015")
    configured_url = Settings().database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for migration 0015 integration tests")
    source_url = make_url(configured_url)
    if not source_url.drivername.startswith("postgresql"):
        pytest.fail("migration 0015 integration tests require PostgreSQL")

    database_name = f"csight_migration_0015_{uuid4().hex[:16]}"
    admin_engine = create_engine(
        source_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    temporary_engine: Engine | None = None
    created = False
    try:
        with admin_engine.connect() as connection:
            quoted_name = connection.dialect.identifier_preparer.quote(database_name)
            connection.exec_driver_sql(f"CREATE DATABASE {quoted_name} TEMPLATE template0")
            created = True
        temporary_url = source_url.set(database=database_name)
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            temporary_url.render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, PREVIOUS)
        temporary_engine = create_engine(temporary_url, pool_pre_ping=True, poolclass=NullPool)
        yield MigrationDatabase(config=config, engine=temporary_engine)
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        if created:
            with admin_engine.connect() as connection:
                quoted_name = connection.dialect.identifier_preparer.quote(database_name)
                connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {quoted_name} WITH (FORCE)")
                assert (
                    connection.scalar(
                        text("SELECT count(*) FROM pg_database WHERE datname = :name"),
                        {"name": database_name},
                    )
                    == 0
                )
        admin_engine.dispose()


def test_migration_round_trip_constraints_and_drift(
    migration_database: MigrationDatabase,
) -> None:
    config, engine = migration_database.config, migration_database.engine
    command.upgrade(config, REVISION)

    inspector = inspect(engine)
    assert "vision_image_assessments" in inspector.get_table_names()
    constraint_names = {
        str(item["name"])
        for item in (
            inspector.get_check_constraints("vision_image_assessments")
            + inspector.get_foreign_keys("vision_image_assessments")
            + inspector.get_unique_constraints("vision_image_assessments")
        )
        if item.get("name") is not None
    }
    assert {
        "fk_vision_image_assessments_tenant_result_vision_results",
        "ck_vision_image_assessments_score_range",
        "ck_vision_image_assessments_threshold_range",
        "ck_vision_image_assessments_outcome_matches_threshold",
        "uq_vision_image_assessments_tenant_result",
    } <= constraint_names

    command.downgrade(config, PREVIOUS)
    assert "vision_image_assessments" not in inspect(engine).get_table_names()
    assert "vision_analysis_results" in inspect(engine).get_table_names()
    assert "vision_detections" in inspect(engine).get_table_names()

    command.upgrade(config, REVISION)
    command.upgrade(config, HEAD)
    command.check(config)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            ScriptDirectory.from_config(config).get_current_head()
        )
