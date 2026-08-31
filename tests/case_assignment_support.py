"""Small service doubles for HTTP tests outside the assignment feature."""

from typing import Any


class AllowCaseAccess:
    """Permit an already in-scope fixture to reach the route under test."""

    def execute(self, **_: Any) -> None:
        return None


__all__ = ["AllowCaseAccess"]
