"""Opt-in checks against the Docker Compose Core infrastructure."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app.adapters.messaging import RabbitMQReadinessProbe
from app.adapters.persistence.engine import clear_engine_cache, get_engine
from app.adapters.storage import MinioReadinessProbe
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def core_settings() -> Settings:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to probe local Core infrastructure")
    settings = Settings()
    if not settings.database_url_value:
        pytest.fail("DATABASE_URL is required for Core integration tests")
    if not settings.rabbitmq_url_value:
        pytest.fail("RABBITMQ_URL is required for Core integration tests")
    if not settings.minio_endpoint:
        pytest.fail("MINIO_ENDPOINT is required for Core integration tests")
    return settings


def test_postgresql_connection(core_settings: Settings) -> None:
    engine = get_engine(core_settings)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_alembic_upgrade_and_vector_extension(core_settings: Settings) -> None:
    project_root = Path(__file__).resolve().parents[2]
    database_url = core_settings.database_url_value
    assert database_url is not None
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    command.upgrade(config, "head")

    engine = get_engine(core_settings)
    with engine.connect() as connection:
        extension_count = connection.execute(
            text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one()
    assert extension_count == 1


def test_rabbitmq_connection(core_settings: Settings) -> None:
    rabbitmq_url = core_settings.rabbitmq_url_value
    assert rabbitmq_url is not None
    probe = RabbitMQReadinessProbe(
        rabbitmq_url,
        timeout_seconds=core_settings.readiness_timeout_seconds,
    )

    assert probe.check() is True


def test_minio_bucket_exists(core_settings: Settings) -> None:
    endpoint = core_settings.minio_endpoint
    access_key = core_settings.minio_access_key_value
    secret_key = core_settings.minio_secret_key_value
    assert endpoint is not None
    assert access_key is not None
    assert secret_key is not None
    probe = MinioReadinessProbe(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        bucket=core_settings.minio_bucket,
        secure=core_settings.minio_secure,
        timeout_seconds=core_settings.readiness_timeout_seconds,
    )

    assert probe.check() is True


@pytest.fixture(scope="module", autouse=True)
def dispose_cached_database_engines() -> Generator[None, None, None]:
    yield
    clear_engine_cache()
