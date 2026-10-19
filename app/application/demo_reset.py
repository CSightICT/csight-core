"""Explicit local-only reset of synthetic review outcomes."""

from typing import Any

from app.platform.errors import ForbiddenError
from app.platform.tenant import Principal, Role
from app.ports.demo_reset import DemoResetRepository


class DemoReset:
    def __init__(self, repository: DemoResetRepository, *, enabled: bool) -> None:
        self.repository = repository
        self.enabled = enabled

    def execute(self, principal: Principal, expected: str | None = None) -> dict[str, Any]:
        if Role.ADMIN not in principal.roles:
            raise ForbiddenError("관리자만 시연 초기화를 사용할 수 있습니다.")
        if not self.enabled:
            return {"enabled": False, "count": 0, "fingerprint": "", "reset_id": None}
        return self.repository.run(principal.tenant_id, principal.user_id, expected)
