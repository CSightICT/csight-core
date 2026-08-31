"""Provision password-backed PostgreSQL login roles for the strict pilot runtime.

Passwords are read from private files and are never accepted as CLI values or
written to output. The migration-owned NOLOGIN group roles remain the source of
database privileges.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

_ROLE_NAME_PATTERN: Final = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_MIN_PASSWORD_BYTES: Final = 32
_MAX_PASSWORD_BYTES: Final = 4096


@dataclass(frozen=True, slots=True)
class RuntimeLogin:
    process: str
    login_name: str
    group_role: str
    password_file: Path


def read_private_password(path: Path) -> str:
    if path.is_symlink():
        raise ValueError(f"{path}: password file must not be a symbolic link")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ValueError(f"{path}: password file cannot be read") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{path}: password source must be a regular file")
    if metadata.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ValueError(f"{path}: password file permissions must be 0600 or stricter")
    if metadata.st_size > _MAX_PASSWORD_BYTES + 2:
        raise ValueError(f"{path}: password file exceeds the {_MAX_PASSWORD_BYTES}-byte limit")
    try:
        password = path.read_text(encoding="utf-8").rstrip("\r\n")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"{path}: password file cannot be read as UTF-8") from exc
    password_bytes = password.encode("utf-8")
    if "\n" in password or "\r" in password:
        raise ValueError(f"{path}: password file must contain exactly one line")
    if len(password_bytes) < _MIN_PASSWORD_BYTES:
        raise ValueError(
            f"{path}: password must contain at least {_MIN_PASSWORD_BYTES} UTF-8 bytes"
        )
    if len(password_bytes) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"{path}: password exceeds the {_MAX_PASSWORD_BYTES}-byte limit")
    return password


def validate_login_name(login_name: str) -> str:
    if not _ROLE_NAME_PATTERN.fullmatch(login_name):
        raise ValueError(
            f"invalid PostgreSQL login name {login_name!r}; use lowercase letters, digits, "
            "and underscores"
        )
    if login_name.startswith("pg_"):
        raise ValueError("PostgreSQL login names beginning with pg_ are reserved")
    return login_name


def psycopg_url(database_url: str) -> str:
    parsed = make_url(database_url)
    if not parsed.drivername.startswith("postgresql"):
        raise ValueError("MIGRATION_DATABASE_URL must use PostgreSQL")
    return parsed.set(drivername="postgresql").render_as_string(hide_password=False)


def _role_flags(connection: psycopg.Connection[Any], role_name: str) -> tuple[bool, ...] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                   rolreplication, rolbypassrls
              FROM pg_roles
             WHERE rolname = %s
            """,
            (role_name,),
        )
        row = cursor.fetchone()
    return tuple(bool(value) for value in row) if row is not None else None


def _validate_group_role(connection: psycopg.Connection[Any], group_role: str) -> None:
    flags = _role_flags(connection, group_role)
    if flags is None:
        raise ValueError(f"required migration group role {group_role} does not exist")
    if any(flags):
        raise ValueError(f"required migration group role {group_role} has unsafe attributes")


def _provision_login(
    connection: psycopg.Connection[Any],
    runtime_login: RuntimeLogin,
    password: str,
) -> None:
    flags = _role_flags(connection, runtime_login.login_name)
    if flags is None:
        statement = sql.SQL(
            "CREATE ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOREPLICATION NOBYPASSRLS PASSWORD {}"
        ).format(sql.Identifier(runtime_login.login_name), sql.Literal(password))
    else:
        expected = (True, False, False, False, False, False)
        if flags != expected:
            raise ValueError(
                f"existing login role {runtime_login.login_name} has unsafe attributes"
            )
        statement = sql.SQL("ALTER ROLE {} PASSWORD {}").format(
            sql.Identifier(runtime_login.login_name),
            sql.Literal(password),
        )
    with connection.cursor() as cursor:
        cursor.execute(statement)
        cursor.execute(
            sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(runtime_login.group_role),
                sql.Identifier(runtime_login.login_name),
            )
        )


def provision_runtime_logins(database_url: str, runtime_logins: tuple[RuntimeLogin, ...]) -> None:
    login_names = tuple(validate_login_name(item.login_name) for item in runtime_logins)
    if len(set(login_names)) != len(login_names):
        raise ValueError("runtime login names must be distinct")
    passwords = tuple(read_private_password(item.password_file) for item in runtime_logins)
    if len(set(passwords)) != len(passwords):
        raise ValueError("runtime login passwords must be distinct")

    with (
        psycopg.connect(psycopg_url(database_url), autocommit=False) as connection,
        connection.transaction(),
    ):
        for item in runtime_logins:
            _validate_group_role(connection, item.group_role)
        for item, password in zip(runtime_logins, passwords, strict=True):
            _provision_login(connection, item, password)


def _required_value(explicit: str | None, environment_name: str) -> str:
    value = explicit or os.getenv(environment_name)
    if not value:
        raise ValueError(f"{environment_name} is required")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision three non-bypass CSight PostgreSQL runtime logins."
    )
    parser.add_argument("--migration-database-url")
    parser.add_argument("--api-login", default=os.getenv("API_DATABASE_LOGIN", "csight_api_login"))
    parser.add_argument(
        "--worker-login",
        default=os.getenv("WORKER_DATABASE_LOGIN", "csight_worker_login"),
    )
    parser.add_argument(
        "--dispatcher-login",
        default=os.getenv("DISPATCHER_DATABASE_LOGIN", "csight_dispatcher_login"),
    )
    parser.add_argument("--api-password-file")
    parser.add_argument("--worker-password-file")
    parser.add_argument("--dispatcher-password-file")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        database_url = _required_value(arguments.migration_database_url, "MIGRATION_DATABASE_URL")
        runtime_logins = (
            RuntimeLogin(
                process="API",
                login_name=arguments.api_login,
                group_role="csight_api_role",
                password_file=Path(
                    _required_value(
                        arguments.api_password_file,
                        "API_DATABASE_PASSWORD_HOST_FILE",
                    )
                ),
            ),
            RuntimeLogin(
                process="Worker",
                login_name=arguments.worker_login,
                group_role="csight_worker_role",
                password_file=Path(
                    _required_value(
                        arguments.worker_password_file,
                        "WORKER_DATABASE_PASSWORD_HOST_FILE",
                    )
                ),
            ),
            RuntimeLogin(
                process="Dispatcher",
                login_name=arguments.dispatcher_login,
                group_role="csight_dispatcher_role",
                password_file=Path(
                    _required_value(
                        arguments.dispatcher_password_file,
                        "DISPATCHER_DATABASE_PASSWORD_HOST_FILE",
                    )
                ),
            ),
        )
        provision_runtime_logins(database_url, runtime_logins)
    except ValueError as exc:
        print(f"runtime login provisioning failed: {exc}", file=sys.stderr)
        return 2
    except psycopg.Error:
        print(
            "runtime login provisioning failed: PostgreSQL rejected the operation; "
            "check the migration-owner connection and server logs",
            file=sys.stderr,
        )
        return 2

    safe_summary = ", ".join(
        f"{item.process}={item.login_name}->{item.group_role}" for item in runtime_logins
    )
    print(f"runtime login provisioning complete: {safe_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
