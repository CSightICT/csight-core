"""Persistence boundary for local synthetic review resets."""

from typing import Any, Protocol


class DemoResetRepository(Protocol):
    def run(self, tenant_id: str, actor_id: str, expected: str | None) -> dict[str, Any]: ...


class DemoResetConflict(Exception):
    pass
