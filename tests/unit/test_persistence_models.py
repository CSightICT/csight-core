"""Metadata contract tests for the Sprint 1 persistence schema."""

from collections.abc import Iterable

import pytest
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import JSONB

from app.adapters.persistence.base import Base
from app.adapters.persistence.models import PERSISTENCE_MODELS

pytestmark = pytest.mark.unit

EXPECTED_TABLES = {
    "tenants",
    "users",
    "roles",
    "user_roles",
    "cases",
    "case_evidence",
    "case_status_history",
    "idempotency_records",
}


def _constraints(table: Table, constraint_type: type[object]) -> Iterable[object]:
    return (
        constraint for constraint in table.constraints if isinstance(constraint, constraint_type)
    )


def _foreign_key_contract(table_name: str) -> dict[str, tuple[list[str], list[str]]]:
    table = Base.metadata.tables[table_name]
    return {
        str(constraint.name): (
            [column.name for column in constraint.columns],
            [element.target_fullname for element in constraint.elements],
        )
        for constraint in _constraints(table, ForeignKeyConstraint)
        if isinstance(constraint, ForeignKeyConstraint)
    }


def test_all_sprint_1_models_are_registered_on_shared_metadata() -> None:
    assert EXPECTED_TABLES.issubset({model.__tablename__ for model in PERSISTENCE_MODELS})
    assert EXPECTED_TABLES.issubset(Base.metadata.tables)


def test_constraints_and_indexes_have_deterministic_names() -> None:
    unnamed_constraints = [
        (table.name, type(constraint).__name__)
        for table in Base.metadata.sorted_tables
        for constraint in table.constraints
        if constraint.name is None
    ]
    unnamed_indexes = [
        (table.name, tuple(column.name for column in index.columns))
        for table in Base.metadata.sorted_tables
        for index in table.indexes
        if index.name is None
    ]

    assert unnamed_constraints == []
    assert unnamed_indexes == []


@pytest.mark.parametrize(
    ("table_name", "column_name", "check_name"),
    [
        ("roles", "name", "ck_roles_name_allowed"),
        ("cases", "domain_type", "ck_cases_domain_type_allowed"),
        ("cases", "status", "ck_cases_status_allowed"),
        ("cases", "requested_action", "ck_cases_requested_action_allowed"),
        (
            "case_evidence",
            "evidence_type",
            "ck_case_evidence_evidence_type_allowed",
        ),
        (
            "case_evidence",
            "upload_status",
            "ck_case_evidence_upload_status_allowed",
        ),
        (
            "case_status_history",
            "to_status",
            "ck_case_status_history_to_status_allowed",
        ),
        (
            "idempotency_records",
            "operation",
            "ck_idempotency_records_operation_allowed",
        ),
        (
            "idempotency_records",
            "resource_type",
            "ck_idempotency_records_resource_type_allowed",
        ),
    ],
)
def test_enum_like_values_use_varchar_and_named_check_constraints(
    table_name: str,
    column_name: str,
    check_name: str,
) -> None:
    table = Base.metadata.tables[table_name]
    column_type = table.c[column_name].type
    check_names = {
        constraint.name
        for constraint in _constraints(table, CheckConstraint)
        if isinstance(constraint, CheckConstraint)
    }

    assert isinstance(column_type, String)
    assert not isinstance(column_type, SQLAlchemyEnum)
    assert check_name in check_names


def test_tenant_ownership_is_enforced_by_composite_foreign_keys() -> None:
    assert _foreign_key_contract("user_roles")["fk_user_roles_tenant_id_user_id_users"] == (
        ["tenant_id", "user_id"],
        ["users.tenant_id", "users.id"],
    )
    assert _foreign_key_contract("cases")["fk_cases_tenant_id_created_by_users"] == (
        ["tenant_id", "created_by"],
        ["users.tenant_id", "users.id"],
    )
    assert _foreign_key_contract("case_evidence")["fk_case_evidence_tenant_id_case_id_cases"] == (
        ["tenant_id", "case_id"],
        ["cases.tenant_id", "cases.id"],
    )
    assert _foreign_key_contract("case_evidence")[
        "fk_case_evidence_tenant_id_created_by_users"
    ] == (["tenant_id", "created_by"], ["users.tenant_id", "users.id"])
    assert _foreign_key_contract("case_status_history")[
        "fk_case_status_history_tenant_id_case_id_cases"
    ] == (["tenant_id", "case_id"], ["cases.tenant_id", "cases.id"])
    assert _foreign_key_contract("case_status_history")[
        "fk_case_status_history_tenant_id_actor_id_users"
    ] == (["tenant_id", "actor_id"], ["users.tenant_id", "users.id"])
    assert _foreign_key_contract("idempotency_records")[
        "fk_idempotency_records_tenant_id_resource_id_cases"
    ] == (["tenant_id", "resource_id"], ["cases.tenant_id", "cases.id"])


def test_idempotency_resource_foreign_key_is_deferred_until_commit() -> None:
    table = Base.metadata.tables["idempotency_records"]
    foreign_key = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_idempotency_records_tenant_id_resource_id_cases"
    )

    assert foreign_key.deferrable is True
    assert foreign_key.initially == "DEFERRED"


@pytest.mark.parametrize(
    ("table_name", "constraint_name", "columns"),
    [
        ("users", "uq_users_tenant_id_id", ("tenant_id", "id")),
        ("users", "uq_users_tenant_id_email", ("tenant_id", "email")),
        ("cases", "uq_cases_tenant_id_id", ("tenant_id", "id")),
        (
            "case_evidence",
            "uq_case_evidence_tenant_id_id",
            ("tenant_id", "id"),
        ),
        (
            "idempotency_records",
            "uq_idempotency_records_tenant_operation_key",
            ("tenant_id", "operation", "idempotency_key"),
        ),
    ],
)
def test_composite_reference_keys_and_idempotency_key_are_unique(
    table_name: str,
    constraint_name: str,
    columns: tuple[str, ...],
) -> None:
    table = Base.metadata.tables[table_name]
    unique_contract = {
        str(constraint.name): tuple(column.name for column in constraint.columns)
        for constraint in _constraints(table, UniqueConstraint)
        if isinstance(constraint, UniqueConstraint)
    }

    assert unique_contract[constraint_name] == columns


def test_temporal_columns_are_timezone_aware() -> None:
    temporal_columns = {
        (table.name, column.name): column
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if column.name in {"created_at", "updated_at", "occurred_at", "expires_at"}
    }

    assert temporal_columns
    assert all(
        isinstance(column.type, DateTime) and column.type.timezone is True
        for column in temporal_columns.values()
    )


def test_cases_attributes_use_postgresql_jsonb() -> None:
    assert isinstance(Base.metadata.tables["cases"].c.attributes.type, JSONB)


def test_query_indexes_cover_sprint_1_access_patterns() -> None:
    actual_indexes = {
        str(index.name): tuple(column.name for column in index.columns)
        for table in Base.metadata.sorted_tables
        for index in table.indexes
    }

    assert actual_indexes["ix_cases_tenant_status_created_id"] == (
        "tenant_id",
        "status",
        "created_at",
        "id",
    )
    assert actual_indexes["ix_cases_tenant_product_ref"] == (
        "tenant_id",
        "product_ref",
    )
    assert actual_indexes["ix_cases_tenant_order_ref"] == ("tenant_id", "order_ref")
    assert actual_indexes["ix_case_evidence_tenant_case_created_id"] == (
        "tenant_id",
        "case_id",
        "created_at",
        "id",
    )
    assert actual_indexes["ix_case_evidence_case_sha256"] == ("case_id", "sha256")
    assert actual_indexes["ix_case_status_history_tenant_case_occurred_id"] == (
        "tenant_id",
        "case_id",
        "occurred_at",
        "id",
    )
