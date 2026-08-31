"""Regression checks for mandatory tenant scope on policy-query Case reads."""

from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.adapters.persistence.policy_query_runs import (
    _tenant_case_message_statement,  # pyright: ignore[reportPrivateUsage]
    _tenant_case_statement,  # pyright: ignore[reportPrivateUsage]
)

pytestmark = pytest.mark.unit


def test_policy_query_case_reads_require_tenant_and_case_identity() -> None:
    tenant_id = uuid4()
    case_id = uuid4()
    statement = _tenant_case_statement(tenant_id=tenant_id, case_id=case_id)
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "cases.tenant_id =" in compiled
    assert "cases.id =" in compiled
    assert set(statement.compile().params.values()) == {tenant_id, case_id}


def test_policy_query_message_reads_only_the_restricted_payload_boundary() -> None:
    tenant_id = uuid4()
    case_id = uuid4()
    statement = _tenant_case_message_statement(tenant_id=tenant_id, case_id=case_id)
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "case_sensitive_payloads.customer_message" in compiled
    assert "case_sensitive_payloads.tenant_id =" in compiled
    assert "case_sensitive_payloads.case_id =" in compiled
    assert "cases.customer_message" not in compiled
    assert set(statement.compile().params.values()) == {tenant_id, case_id}
