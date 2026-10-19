"""Run the Core integration suite against a disposable PostgreSQL clone."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import IO
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.bootstrap.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    pytest_arguments = sys.argv[1:]
    if pytest_arguments[:1] == ["--"]:
        pytest_arguments = pytest_arguments[1:]
    source_value = Settings().database_url_value
    if not source_value:
        print("Integration isolation requires DATABASE_URL.", file=sys.stderr)
        return 2
    source_url = make_url(source_value)
    if (
        not source_url.drivername.startswith("postgresql")
        or not source_url.database
        or not source_url.username
    ):
        print("Integration isolation requires a PostgreSQL DATABASE_URL.", file=sys.stderr)
        return 2

    postgres_container = _postgres_container()
    if postgres_container is None:
        print("The Core PostgreSQL container must be running.", file=sys.stderr)
        return 2

    database_name = f"csight_integration_{uuid4().hex[:16]}"
    temporary_url = source_url.set(database=database_name)
    admin_url = source_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    created = False
    test_status = 1

    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        created = True

        with tempfile.TemporaryDirectory(prefix="csight-integration-") as directory:
            archive = Path(directory) / "source.dump"
            with archive.open("wb") as output:
                _run(
                    [
                        "docker",
                        "exec",
                        postgres_container,
                        "pg_dump",
                        "--format=custom",
                        "--no-owner",
                        "--no-acl",
                        "--username",
                        source_url.username,
                        source_url.database,
                    ],
                    output=output,
                )
            with archive.open("rb") as input_stream:
                _run(
                    [
                        "docker",
                        "exec",
                        "--interactive",
                        postgres_container,
                        "pg_restore",
                        "--exit-on-error",
                        "--no-owner",
                        "--no-acl",
                        "--username",
                        source_url.username,
                        "--dbname",
                        database_name,
                    ],
                    input_stream=input_stream,
                )

        test_environment = os.environ.copy()
        test_environment["DATABASE_URL"] = temporary_url.render_as_string(hide_password=False)
        test_environment["RUN_CORE_INTEGRATION"] = "1"
        test_environment["CSIGHT_DISPOSABLE_TEST_DATABASE"] = database_name
        _run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            environment=test_environment,
        )
        test_status = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-m",
                "integration",
                *pytest_arguments,
            ],
            cwd=ROOT,
            env=test_environment,
            check=False,
        ).returncode
    except subprocess.CalledProcessError as error:
        test_status = error.returncode or 1
    finally:
        if created:
            with admin_engine.connect() as connection:
                connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                    ),
                    {"database_name": database_name},
                )
                connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
                remaining = connection.execute(
                    text("SELECT count(*) FROM pg_database WHERE datname = :database_name"),
                    {"database_name": database_name},
                ).scalar_one()
            if remaining != 0:
                print("Disposable integration database was not removed.", file=sys.stderr)
                test_status = 1
            else:
                print("Disposable integration database removed.")
        admin_engine.dispose()

    return test_status


def _postgres_container() -> str | None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(ROOT / ".env"),
            "--file",
            str(ROOT / "infra/compose.core.yml"),
            "ps",
            "--quiet",
            "postgres",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    container = result.stdout.strip()
    return container if result.returncode == 0 and container else None


def _run(
    command: list[str],
    *,
    environment: dict[str, str] | None = None,
    input_stream: IO[bytes] | None = None,
    output: IO[bytes] | None = None,
) -> None:
    subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        stdin=input_stream,
        stdout=output,
        check=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
