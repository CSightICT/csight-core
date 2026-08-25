"""PostgreSQL readiness adapter."""

from collections.abc import Callable

from sqlalchemy import Engine, text


class PostgresReadinessProbe:
    name = "postgresql"

    def __init__(self, engine_factory: Callable[[], Engine]) -> None:
        self._engine_factory = engine_factory

    def check(self) -> bool:
        engine = self._engine_factory()
        with engine.connect() as connection:
            return connection.execute(text("SELECT 1")).scalar_one() == 1
