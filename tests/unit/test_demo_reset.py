from unittest.mock import Mock

import pytest

from app.application.demo_reset import DemoReset
from app.platform.errors import ForbiddenError
from app.platform.tenant import Principal, Role


def principal(role):
    return Principal(
        user_id="actor",
        tenant_id="tenant",
        email="a@example.test",
        display_name="A",
        roles=frozenset({role}),
    )


def test_disabled_reset_never_touches_database():
    repository = Mock()
    result = DemoReset(repository, enabled=False).execute(principal(Role.ADMIN), "0" * 64)
    assert not result["enabled"]
    repository.run.assert_not_called()


def test_non_admin_cannot_reset():
    repository = Mock()
    with pytest.raises(ForbiddenError):
        DemoReset(repository, enabled=True).execute(principal(Role.REVIEWER))
    repository.run.assert_not_called()


def test_admin_scope_and_preview_fingerprint_reach_repository():
    repository = Mock()
    DemoReset(repository, enabled=True).execute(principal(Role.ADMIN), "a" * 64)
    repository.run.assert_called_once_with("tenant", "actor", "a" * 64)


def test_http_reset_admin_boundary_and_stale_confirmation():
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.interface.http.routers.operations import (
        provide_current_principal,
        provide_operations_services,
        router,
    )
    from app.ports.demo_reset import DemoResetConflict

    app = FastAPI()
    app.include_router(router)
    repository = Mock()
    service = DemoReset(repository, enabled=True)
    app.dependency_overrides[provide_operations_services] = lambda: SimpleNamespace(
        demo_reset=service
    )
    app.dependency_overrides[provide_current_principal] = lambda: principal(Role.REVIEWER)
    with TestClient(app) as client:
        assert client.get("/api/v1/operations/demo-reset").status_code == 403
        repository.run.assert_not_called()
        app.dependency_overrides[provide_current_principal] = lambda: principal(Role.ADMIN)
        assert (
            client.post("/api/v1/operations/demo-reset", json={"fingerprint": "bad"}).status_code
            == 422
        )
        repository.run.side_effect = DemoResetConflict("대상이 변경되었습니다")
        result = client.post("/api/v1/operations/demo-reset", json={"fingerprint": "a" * 64})
        assert result.status_code == 409
