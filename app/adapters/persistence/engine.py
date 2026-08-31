"""Synchronous SQLAlchemy 2 engine construction."""

from functools import lru_cache
from typing import Any
from weakref import WeakSet

from sqlalchemy import Engine, create_engine, event

from app.bootstrap.settings import Settings, get_settings


class DatabaseConfigurationError(RuntimeError):
    """Raised when a process attempts DB work without deployment configuration."""


_created_engines: WeakSet[Engine] = WeakSet()
_PILOT_GROUP_ROLES = {
    "api": "csight_api_role",
    "worker": "csight_worker_role",
    "dispatcher": "csight_dispatcher_role",
}


def _verify_pilot_connection(
    dbapi_connection: Any,
    expected_group_role: str,
) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(
            """
            SELECT current_user,
                   current_setting('is_superuser') = 'on',
                   COALESCE(
                       (SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user),
                       false
                   ),
                   pg_has_role(current_user, %s, 'member')
            """,
            (expected_group_role,),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    if row is None or bool(row[1]) or bool(row[2]) or not bool(row[3]):
        raise DatabaseConfigurationError(
            "database login does not satisfy the required non-bypass runtime role"
        )


@lru_cache(maxsize=16)
def _cached_engine(
    database_url: str,
    echo: bool,
    database_rls_required: bool,
    database_runtime_role: str,
) -> Engine:
    # SQL echo is useful for local diagnostics, but customer messages and other
    # sensitive values can be SQL bind parameters. Keep parameter values hidden
    # even when statement logging is explicitly enabled.
    engine = create_engine(
        database_url,
        echo=echo,
        hide_parameters=True,
        pool_pre_ping=True,
    )
    if database_rls_required:
        expected_group_role = _PILOT_GROUP_ROLES[database_runtime_role]

        def verify_connection(connection: Any, _record: Any) -> None:
            _verify_pilot_connection(connection, expected_group_role)

        event.listen(engine, "connect", verify_connection)
    _created_engines.add(engine)
    return engine


def get_engine(settings: Settings | None = None) -> Engine:
    """Return a process-cached engine for the supplied settings."""

    resolved_settings = settings or get_settings()
    database_url = resolved_settings.database_url_value
    if not database_url:
        raise DatabaseConfigurationError("DATABASE_URL is not configured")
    return _cached_engine(
        database_url,
        resolved_settings.database_echo,
        resolved_settings.database_rls_required,
        resolved_settings.database_runtime_role,
    )


def clear_engine_cache() -> None:
    """Dispose cached pools and reset them; intended for tests and process teardown."""

    for engine in tuple(_created_engines):
        engine.dispose()
    _created_engines.clear()
    _cached_engine.cache_clear()
