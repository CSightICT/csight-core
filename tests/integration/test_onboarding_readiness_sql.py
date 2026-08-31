"""Opt-in PostgreSQL contract check for the tenant readiness snapshot."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, text

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.onboarding_readiness import (
    SQLAlchemyOnboardingReadinessRepository,
)
from app.adapters.persistence.session import create_session_factory
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.integration


def test_onboarding_readiness_uses_one_tenant_scoped_postgresql_statement() -> None:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test onboarding readiness SQL")
    settings = Settings()
    if settings.database_url_value is None:
        pytest.skip("DATABASE_URL is required to test onboarding readiness SQL")

    engine = get_engine(settings)
    repository = SQLAlchemyOnboardingReadinessRepository(create_session_factory(engine))
    with engine.connect() as connection:
        existing_tenant_id = connection.execute(
            text("SELECT id FROM tenants ORDER BY created_at, id LIMIT 1")
        ).scalar_one_or_none()
    if existing_tenant_id is None:
        pytest.skip("an existing tenant is required to test onboarding readiness SQL")

    statement_count = 0
    tenant_context_applied = False

    def count_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        *_args: object,
    ) -> None:
        nonlocal statement_count, tenant_context_applied
        if "set_config" not in statement:
            statement_count += 1
        elif "app.tenant_id" in str(_args):
            tenant_context_applied = True

    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        facts = repository.get_facts(
            tenant_id=str(existing_tenant_id),
            configured_signed_actor_ids=(),
            as_of_date=datetime.now(UTC).date(),
        )
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)

    assert statement_count == 1
    assert tenant_context_applied is True
    assert facts.configured_no_role_actor_count == 0
    assert facts.active_admin_count >= 0
    assert facts.active_reviewer_count >= 0
    assert facts.active_policy_index_count >= 0
    assert facts.active_rule_set_count >= 0
    assert 0 <= facts.active_primary_model_route_count <= 3
