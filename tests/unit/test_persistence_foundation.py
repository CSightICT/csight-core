"""SQLAlchemy foundation tests that require no external PostgreSQL process."""

import logging

import pytest
from pydantic import SecretStr
from sqlalchemy import CheckConstraint, Column, Integer, MetaData, Table, text

from app.adapters.persistence.base import NAMING_CONVENTION
from app.adapters.persistence.engine import (
    DatabaseConfigurationError,
    clear_engine_cache,
    get_engine,
)
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.unit


def test_naming_convention_generates_stable_constraint_names() -> None:
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    table = Table(
        "foundation_probe",
        metadata,
        Column("id", Integer, primary_key=True),
        CheckConstraint("id > 0", name="positive_id"),
    )

    names = {constraint.name for constraint in table.constraints}

    assert "pk_foundation_probe" in names
    assert "ck_foundation_probe_positive_id" in names


def test_engine_fails_closed_without_database_url() -> None:
    with pytest.raises(DatabaseConfigurationError, match="DATABASE_URL"):
        get_engine(Settings(_env_file=None))  # pyright: ignore[reportCallIssue]


def test_engine_echo_never_logs_bound_parameter_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "SENSITIVE-CUSTOMER-TEXT"
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
        database_echo=True,
    )
    clear_engine_cache()
    try:
        engine = get_engine(settings)
        caplog.set_level(logging.INFO, logger="sqlalchemy.engine.Engine")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT :customer_message"), {"customer_message": marker})

        assert engine.hide_parameters is True
        assert marker not in caplog.text
    finally:
        clear_engine_cache()
