"""Metadata contracts for tenant-safe Sprint 2 analysis persistence."""

from collections.abc import Iterable

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.adapters.persistence.base import Base
from app.adapters.persistence.models import PERSISTENCE_MODELS

pytestmark = pytest.mark.unit

SPRINT_2_TABLES = {
    "analysis_runs",
    "analysis_stage_runs",
    "analysis_stage_attempts",
    "llm_extraction_results",
    "analysis_request_idempotency_records",
    "outbox_events",
}


def _constraints(table: Table, kind: type[object]) -> Iterable[object]:
    return (constraint for constraint in table.constraints if isinstance(constraint, kind))


def _foreign_keys(table_name: str) -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    table = Base.metadata.tables[table_name]
    return {
        str(constraint.name): (
            tuple(column.name for column in constraint.columns),
            tuple(element.target_fullname for element in constraint.elements),
        )
        for constraint in _constraints(table, ForeignKeyConstraint)
        if isinstance(constraint, ForeignKeyConstraint)
    }


def _unique_contract(table_name: str) -> dict[str, tuple[str, ...]]:
    table = Base.metadata.tables[table_name]
    return {
        str(constraint.name): tuple(column.name for column in constraint.columns)
        for constraint in _constraints(table, UniqueConstraint)
        if isinstance(constraint, UniqueConstraint)
    }


def test_all_sprint_2_models_are_registered_and_names_fit_postgresql() -> None:
    assert SPRINT_2_TABLES.issubset({model.__tablename__ for model in PERSISTENCE_MODELS})
    assert SPRINT_2_TABLES.issubset(Base.metadata.tables)

    names = [
        str(item.name)
        for table in Base.metadata.sorted_tables
        for item in (*table.constraints, *table.indexes)
        if item.name is not None
    ]
    assert all(len(name) <= 63 for name in names)


def test_analysis_tables_enforce_composite_tenant_ownership() -> None:
    assert _foreign_keys("analysis_runs")["fk_analysis_runs_tenant_id_case_id_cases"] == (
        ("tenant_id", "case_id"),
        ("cases.tenant_id", "cases.id"),
    )
    assert _foreign_keys("analysis_stage_runs")[
        "fk_analysis_stage_runs_tenant_id_analysis_run_id_analysis_runs"
    ] == (
        ("tenant_id", "analysis_run_id"),
        ("analysis_runs.tenant_id", "analysis_runs.id"),
    )
    assert _foreign_keys("analysis_stage_attempts")[
        "fk_analysis_stage_attempts_tenant_run_stage_analysis_stage_runs"
    ] == (
        ("tenant_id", "analysis_run_id", "stage_run_id"),
        (
            "analysis_stage_runs.tenant_id",
            "analysis_stage_runs.analysis_run_id",
            "analysis_stage_runs.id",
        ),
    )


def test_result_is_append_only_one_per_run_and_text_stage() -> None:
    result_uniques = _unique_contract("llm_extraction_results")
    assert result_uniques["uq_llm_extraction_results_tenant_analysis_run"] == (
        "tenant_id",
        "analysis_run_id",
    )
    assert result_uniques["uq_llm_extraction_results_tenant_stage_run"] == (
        "tenant_id",
        "stage_run_id",
    )
    result_foreign_keys = _foreign_keys("llm_extraction_results")
    assert result_foreign_keys["fk_llm_results_tenant_run_stage_type_stage_runs"] == (
        ("tenant_id", "analysis_run_id", "stage_run_id", "stage_type"),
        (
            "analysis_stage_runs.tenant_id",
            "analysis_stage_runs.analysis_run_id",
            "analysis_stage_runs.id",
            "analysis_stage_runs.stage_type",
        ),
    )
    checks = {
        str(constraint.name): str(constraint.sqltext)
        for constraint in _constraints(
            Base.metadata.tables["llm_extraction_results"], CheckConstraint
        )
        if isinstance(constraint, CheckConstraint)
    }
    assert checks["ck_llm_extraction_results_stage_type_text_extraction"] == (
        "stage_type = 'TEXT_EXTRACTION'"
    )
    assert isinstance(Base.metadata.tables["llm_extraction_results"].c.claims.type, JSONB)


def test_idempotency_keeps_sprint_1_fk_and_adds_deferred_analysis_fk() -> None:
    assert "fk_idempotency_records_tenant_id_resource_id_cases" in _foreign_keys(
        "idempotency_records"
    )
    analysis_table = Base.metadata.tables["analysis_request_idempotency_records"]
    analysis_fk = next(
        constraint
        for constraint in analysis_table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_analysis_request_idempotency_tenant_run_analysis_runs"
    )
    assert analysis_fk.deferrable is True
    assert analysis_fk.initially == "DEFERRED"
    assert _unique_contract("analysis_request_idempotency_records")[
        "uq_analysis_request_idempotency_tenant_operation_key"
    ] == ("tenant_id", "operation", "idempotency_key")


def test_claim_and_outbox_recovery_indexes_are_partial() -> None:
    indexes: dict[str, Index] = {
        str(index.name): index for table in Base.metadata.sorted_tables for index in table.indexes
    }
    expected_predicates = {
        "ix_analysis_stage_runs_running_lease": "status = 'RUNNING'",
        "ix_analysis_stage_runs_retry_schedule": "status = 'RETRY_WAITING'",
        "ix_outbox_events_pending_dispatch": "status = 'PENDING'",
        "ix_outbox_events_processing_claimed": "status = 'PROCESSING'",
    }
    for name, expected in expected_predicates.items():
        assert str(indexes[name].dialect_options["postgresql"]["where"]) == expected


def test_outbox_payload_is_strictly_reference_only() -> None:
    checks = {
        str(constraint.name): str(constraint.sqltext)
        for constraint in _constraints(Base.metadata.tables["outbox_events"], CheckConstraint)
        if isinstance(constraint, CheckConstraint)
    }
    allowed = checks["ck_outbox_events_payload_allowed_keys"]
    for key in (
        "event_id",
        "event_type",
        "event_version",
        "tenant_id",
        "case_id",
        "analysis_run_id",
        "stage_run_id",
        "correlation_id",
        "occurred_at",
    ):
        assert key in allowed
    for forbidden in ("customer_message", "prompt", "raw_response", "jwt", "signed_url"):
        assert forbidden not in allowed
