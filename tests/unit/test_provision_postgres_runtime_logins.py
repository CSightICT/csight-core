"""Secret-file and identifier contracts for PostgreSQL runtime provisioning."""

from pathlib import Path

import pytest

from scripts.provision_postgres_runtime_logins import (
    psycopg_url,
    read_private_password,
    validate_login_name,
)

pytestmark = pytest.mark.unit


def _write_private(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def test_private_password_accepts_one_private_bounded_line(tmp_path: Path) -> None:
    password_file = tmp_path / "api-password"
    _write_private(password_file, "a" * 32 + "\n")

    assert read_private_password(password_file) == "a" * 32


def test_private_password_rejects_short_or_exposed_files(tmp_path: Path) -> None:
    short_file = tmp_path / "short-password"
    _write_private(short_file, "too-short")
    with pytest.raises(ValueError, match="at least 32"):
        read_private_password(short_file)

    exposed_file = tmp_path / "exposed-password"
    _write_private(exposed_file, "b" * 32)
    exposed_file.chmod(0o644)
    with pytest.raises(ValueError, match="0600 or stricter"):
        read_private_password(exposed_file)


def test_runtime_login_name_and_admin_url_are_restricted() -> None:
    assert validate_login_name("csight_api_login") == "csight_api_login"
    with pytest.raises(ValueError, match="invalid PostgreSQL login name"):
        validate_login_name("API login")
    with pytest.raises(ValueError, match="reserved"):
        validate_login_name("pg_csight")

    assert psycopg_url("postgresql+psycopg://owner:secret@db/csight").startswith(
        "postgresql://owner:secret@db/"
    )
    with pytest.raises(ValueError, match="must use PostgreSQL"):
        psycopg_url("sqlite:///local.db")
