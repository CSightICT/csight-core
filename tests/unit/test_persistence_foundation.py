"""SQLAlchemy foundation tests that require no external PostgreSQL process."""

import pytest
from sqlalchemy import CheckConstraint, Column, Integer, Table

from app.adapters.persistence.base import Base
from app.adapters.persistence.engine import DatabaseConfigurationError, get_engine
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.unit


def test_naming_convention_generates_stable_constraint_names() -> None:
    table = Table(
        "foundation_probe",
        Base.metadata,
        Column("id", Integer, primary_key=True),
        CheckConstraint("id > 0", name="positive_id"),
        extend_existing=True,
    )

    names = {constraint.name for constraint in table.constraints}

    assert "pk_foundation_probe" in names
    assert "ck_foundation_probe_positive_id" in names


def test_engine_fails_closed_without_database_url() -> None:
    with pytest.raises(DatabaseConfigurationError, match="DATABASE_URL"):
        get_engine(Settings(_env_file=None))  # pyright: ignore[reportCallIssue]
