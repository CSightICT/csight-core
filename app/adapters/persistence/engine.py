"""Synchronous SQLAlchemy 2 engine construction."""

from functools import lru_cache
from weakref import WeakSet

from sqlalchemy import Engine, create_engine

from app.bootstrap.settings import Settings, get_settings


class DatabaseConfigurationError(RuntimeError):
    """Raised when a process attempts DB work without deployment configuration."""


_created_engines: WeakSet[Engine] = WeakSet()


@lru_cache(maxsize=8)
def _cached_engine(database_url: str, echo: bool) -> Engine:
    # SQL echo is useful for local diagnostics, but customer messages and other
    # sensitive values can be SQL bind parameters. Keep parameter values hidden
    # even when statement logging is explicitly enabled.
    engine = create_engine(
        database_url,
        echo=echo,
        hide_parameters=True,
        pool_pre_ping=True,
    )
    _created_engines.add(engine)
    return engine


def get_engine(settings: Settings | None = None) -> Engine:
    """Return a process-cached engine for the supplied settings."""

    resolved_settings = settings or get_settings()
    database_url = resolved_settings.database_url_value
    if not database_url:
        raise DatabaseConfigurationError("DATABASE_URL is not configured")
    return _cached_engine(database_url, resolved_settings.database_echo)


def clear_engine_cache() -> None:
    """Dispose cached pools and reset them; intended for tests and process teardown."""

    for engine in tuple(_created_engines):
        engine.dispose()
    _created_engines.clear()
    _cached_engine.cache_clear()
