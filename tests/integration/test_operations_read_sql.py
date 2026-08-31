"""Opt-in PostgreSQL contract checks for aggregate operations reads."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.operations import SQLAlchemyOperationsReadRepository
from app.adapters.persistence.session import create_session_factory
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.integration


def _assert_no_tenant_or_case_labels(value: object, *, tenant_id: str) -> None:
    if isinstance(value, dict):
        assert "tenant_id" not in value
        assert "case_id" not in value
        for item in value.values():
            _assert_no_tenant_or_case_labels(item, tenant_id=tenant_id)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_tenant_or_case_labels(item, tenant_id=tenant_id)
    elif isinstance(value, str):
        assert value != tenant_id


def test_operations_reads_execute_one_postgresql_statement_and_bound_dimensions() -> None:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test operations read SQL")
    settings = Settings()
    if settings.database_url_value is None:
        pytest.skip("DATABASE_URL is required to test operations read SQL")

    engine = get_engine(settings)
    repository = SQLAlchemyOperationsReadRepository(create_session_factory(engine))
    with engine.connect() as connection:
        existing_tenant_id = connection.execute(
            text("SELECT id FROM tenants ORDER BY created_at, id LIMIT 1")
        ).scalar_one_or_none()
    tenant_id = str(existing_tenant_id) if existing_tenant_id is not None else str(uuid4())
    now = datetime.now(UTC)
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
        overview = repository.get_overview(
            tenant_id=tenant_id,
            now=now,
            stalled_before=now - timedelta(minutes=5),
        )
        assert statement_count == 1
        assert tenant_context_applied is True
        assert len(overview.queues) == 7
        assert len(overview.processing) == 7
        assert len(overview.active_versions) <= 64
        assert overview.total_backlog_count >= 0
        _assert_no_tenant_or_case_labels(
            overview.model_dump(mode="python"),
            tenant_id=tenant_id,
        )

        statement_count = 0
        tenant_context_applied = False
        failures = repository.get_failures(
            tenant_id=tenant_id,
            now=now,
            since=now - timedelta(hours=24),
            stalled_before=now - timedelta(minutes=5),
        )
        assert statement_count == 1
        assert tenant_context_applied is True
        assert len(failures.components) == 7
        assert all(len(component.top_failure_codes) <= 3 for component in failures.components)
        _assert_no_tenant_or_case_labels(
            failures.model_dump(mode="python"),
            tenant_id=tenant_id,
        )
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)
