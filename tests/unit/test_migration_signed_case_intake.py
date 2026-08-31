"""Offline contract for migration 0032 signed Case intake."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit
PREVIOUS = "20260830_0031_oidc_backchannel_logout"
REVISION = "20260831_0032_signed_case_intake"


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_signed_intake_migration_follows_oidc_backchannel_revision() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    migration = scripts.get_revision(REVISION)
    assert migration is not None and migration.down_revision == PREVIOUS


def test_upgrade_adds_only_the_distinct_signed_intake_operation() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()
    assert "case.create.v1" in sql
    assert "case.intake.signed.v1" in sql
    assert "source_scope" not in sql
