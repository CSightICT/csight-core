"""Opt-in PostgreSQL contract checks for one-statement operator reads."""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import sessionmaker

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.operator_read import SQLAlchemyOperatorReadRepository
from app.adapters.persistence.session import create_session_factory
from app.bootstrap.settings import Settings
from app.platform.operator_read import QueueSort, QueueView

pytestmark = pytest.mark.integration


def test_operator_reads_execute_one_postgresql_statement_each() -> None:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test operator read SQL")
    settings = Settings()
    if settings.database_url_value is None:
        pytest.skip("DATABASE_URL is required to test operator read SQL")
    engine = get_engine(settings)
    repository = SQLAlchemyOperatorReadRepository(create_session_factory(engine))
    statement_count = 0

    with engine.connect() as connection:
        existing_case = (
            connection.execute(
                text("SELECT tenant_id, id FROM cases ORDER BY created_at, id LIMIT 1")
            )
            .mappings()
            .one_or_none()
        )

    def count_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        *_args: object,
    ) -> None:
        nonlocal statement_count
        if "set_config" not in statement:
            statement_count += 1

    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        tenant_id = str(existing_case["tenant_id"]) if existing_case is not None else str(uuid4())
        case_id = str(existing_case["id"]) if existing_case is not None else str(uuid4())
        actor_id = str(uuid4())
        cases = repository.list_cases(
            tenant_id=tenant_id,
            actor_id=actor_id,
            can_view_all=True,
            view=QueueView.ALL,
            sort=QueueSort.NEWEST,
            query=None,
            limit=25,
            after_created_at=None,
            after_id=None,
        )
        assert statement_count == 1
        if existing_case is None:
            assert cases.items == ()
            assert cases.counts.all == 0
        else:
            assert cases.counts.all >= 1
            assert cases.items

        statement_count = 0
        reviews = repository.list_reviews(
            tenant_id=tenant_id,
            actor_id=actor_id,
            can_view_all=True,
            view=QueueView.ALL,
            sort=QueueSort.NEWEST,
            query=None,
            limit=25,
            after_created_at=None,
            after_id=None,
        )
        assert statement_count == 1
        assert len(reviews.items) <= reviews.counts.all
        assert all(
            item.inquiry_preview is None or len(item.inquiry_preview) <= 160
            for item in reviews.items
        )

        statement_count = 0
        snapshot = repository.get_workflow_snapshot(tenant_id=tenant_id, case_id=case_id)
        assert statement_count == 1
        assert (snapshot is not None) is (existing_case is not None)
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)


def test_queue_preview_is_bounded_and_excludes_expired_content() -> None:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("requires disposable integration database")
    engine = get_engine(Settings())
    with engine.connect() as connection, connection.begin():
        source = (
            connection.execute(
                text("""
            SELECT sp.tenant_id, sp.case_id, sp.customer_message
            FROM case_sensitive_payloads sp
            WHERE sp.purged_at IS NULL AND sp.expires_at > CURRENT_TIMESTAMP
            ORDER BY sp.case_id LIMIT 1
        """)
            )
            .mappings()
            .one_or_none()
        )
        if source is None:
            pytest.skip("no unexpired inquiry fixture in disposable clone")
        repository = SQLAlchemyOperatorReadRepository(sessionmaker(bind=connection))
        arguments: dict[str, Any] = dict(
            tenant_id=str(source["tenant_id"]),
            actor_id=str(uuid4()),
            can_view_all=True,
            view=QueueView.ALL,
            sort=QueueSort.NEWEST,
            query=str(source["case_id"]),
            limit=25,
            after_created_at=None,
            after_id=None,
        )
        cases = repository.list_cases(**arguments)
        expected = " ".join(source["customer_message"].split())[:160].strip()
        assert cases.items[0].inquiry_preview == expected
        reviews = repository.list_reviews(**arguments)
        assert all(item.inquiry_preview == expected for item in reviews.items)
        connection.execute(
            text("""
            UPDATE case_sensitive_payloads SET expires_at = CURRENT_TIMESTAMP - interval '1 second'
            WHERE tenant_id = :tenant AND case_id = :case
        """),
            {"tenant": source["tenant_id"], "case": source["case_id"]},
        )
        assert repository.list_cases(**arguments).items[0].inquiry_preview is None
        assert all(
            item.inquiry_preview is None for item in repository.list_reviews(**arguments).items
        )
        arguments["tenant_id"] = str(uuid4())
        assert repository.list_cases(**arguments).items == ()
        assert repository.list_reviews(**arguments).items == ()
