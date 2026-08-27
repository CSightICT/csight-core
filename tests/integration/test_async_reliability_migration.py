"""Disposable PostgreSQL lifecycle gates for migration 0012 integrity constraints."""

from __future__ import annotations

import os
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Connection, Engine, MetaData, Table, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from alembic import command as alembic_command
from app.bootstrap.settings import Settings

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
REVISION_0011 = "20260827_0011_human_review"
REVISION_0012 = "20260827_0012_async_reliability"


@dataclass(frozen=True, slots=True)
class MigrationDatabase:
    config: Config
    engine: Engine


@dataclass(frozen=True, slots=True)
class LegacyGraph:
    tenant_id: UUID
    user_id: UUID
    case_id: UUID
    other_case_id: UUID
    analysis_result_id: UUID
    retrieval_run_id: UUID
    grounding_run_id: UUID
    policy_evaluation_run_id: UUID
    review_task_id: UUID
    assignment_id: UUID
    decision_id: UUID
    citation_item_id: UUID
    citation_clause_id: UUID
    other_clause_id: UUID
    resolved_at: datetime


@pytest.fixture(scope="module")
def migration_database() -> Generator[MigrationDatabase, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test migration 0012")
    configured_url = Settings().database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for migration 0012 integration tests")
    source_url = make_url(configured_url)
    if not source_url.drivername.startswith("postgresql"):
        pytest.fail("migration 0012 integration tests require PostgreSQL")

    database_name = f"csight_migration_0012_{uuid4().hex[:16]}"
    admin_url = source_url.set(database="postgres")
    temporary_url = source_url.set(database=database_name)
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    temporary_engine: Engine | None = None
    created = False
    try:
        with admin_engine.connect() as connection:
            quoted_name = connection.dialect.identifier_preparer.quote(database_name)
            connection.exec_driver_sql(f"CREATE DATABASE {quoted_name} TEMPLATE template0")
            created = True

        config = Config(str(ROOT / "alembic.ini"))
        migration_url = temporary_url.render_as_string(hide_password=False)
        config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))
        alembic_command.upgrade(config, REVISION_0011)
        temporary_engine = create_engine(temporary_url, pool_pre_ping=True, poolclass=NullPool)
        yield MigrationDatabase(config=config, engine=temporary_engine)
    finally:
        try:
            if temporary_engine is not None:
                temporary_engine.dispose()
        finally:
            try:
                if created:
                    with admin_engine.connect() as connection:
                        quoted_name = connection.dialect.identifier_preparer.quote(database_name)
                        connection.exec_driver_sql(
                            f"DROP DATABASE IF EXISTS {quoted_name} WITH (FORCE)"
                        )
                        remaining = connection.scalar(
                            text("SELECT count(*) FROM pg_database WHERE datname = :name"),
                            {"name": database_name},
                        )
                        if remaining != 0:
                            raise RuntimeError("temporary migration 0012 database was not removed")
            finally:
                admin_engine.dispose()


def _table(connection: Connection, name: str) -> Table:
    return Table(
        name,
        MetaData(),
        autoload_with=connection,
        resolve_fks=False,
    )


def _seed_legacy_graph(connection: Connection) -> LegacyGraph:
    now = datetime.now(UTC).replace(microsecond=0)
    tenant_id = uuid4()
    user_id = uuid4()
    case_id, other_case_id = uuid4(), uuid4()
    analysis_run_id, stage_run_id, analysis_result_id = uuid4(), uuid4(), uuid4()
    ingestion_run_id, document_id = uuid4(), uuid4()
    citation_clause_id, other_clause_id = uuid4(), uuid4()
    embedding_profile_id, index_id, query_profile_id = uuid4(), uuid4(), uuid4()
    retrieval_run_id, citation_pack_id, citation_item_id = uuid4(), uuid4(), uuid4()
    grounding_profile_id, grounding_run_id = uuid4(), uuid4()
    rule_set_id, policy_evaluation_run_id = uuid4(), uuid4()
    review_task_id, assignment_id, decision_id = uuid4(), uuid4(), uuid4()
    basis_id = uuid4()
    resolved_at = now

    connection.execute(
        _table(connection, "tenants").insert(),
        {
            "id": tenant_id,
            "slug": f"migration-{tenant_id.hex[:12]}",
            "name": "Migration 0012 Tenant",
            "is_active": True,
        },
    )
    connection.execute(
        _table(connection, "users").insert(),
        {
            "id": user_id,
            "tenant_id": tenant_id,
            "email": f"reviewer-{user_id.hex[:12]}@migration.test",
            "password_hash": "migration-test-password-hash",
            "display_name": "Migration Reviewer",
            "is_active": True,
        },
    )
    connection.execute(
        _table(connection, "cases").insert(),
        [
            {
                "id": case_id,
                "tenant_id": tenant_id,
                "domain_type": "product_defect_cs",
                "status": "RECEIVED",
                "order_ref": "MIGRATION-ORDER-1",
                "product_ref": "MIGRATION-PRODUCT-1",
                "customer_message": "합성 migration case one",
                "requested_action": "REFUND",
                "attributes": {},
                "created_by": user_id,
            },
            {
                "id": other_case_id,
                "tenant_id": tenant_id,
                "domain_type": "product_defect_cs",
                "status": "RECEIVED",
                "order_ref": "MIGRATION-ORDER-2",
                "product_ref": "MIGRATION-PRODUCT-2",
                "customer_message": "합성 migration case two",
                "requested_action": "EXCHANGE",
                "attributes": {},
                "created_by": user_id,
            },
        ],
    )
    connection.execute(
        _table(connection, "analysis_runs").insert(),
        {
            "id": analysis_run_id,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "pipeline_name": "product_defect_text_extraction",
            "pipeline_version": "2.0.0",
            "trigger_type": "USER_REQUEST",
            "status": "SUCCEEDED",
            "requested_by": user_id,
            "correlation_id": "migration-analysis",
            "idempotency_key": f"migration-analysis-{analysis_run_id}",
            "request_hash": "a" * 64,
            "requested_at": now,
            "started_at": now,
            "completed_at": now,
        },
    )
    connection.execute(
        _table(connection, "analysis_stage_runs").insert(),
        {
            "id": stage_run_id,
            "tenant_id": tenant_id,
            "analysis_run_id": analysis_run_id,
            "stage_type": "TEXT_EXTRACTION",
            "status": "SUCCEEDED",
            "attempt_count": 1,
            "provider_name": "mock",
            "model_name": "migration-model",
            "model_version": "1.0.0",
            "model_revision": "migration",
            "prompt_name": "migration-prompt",
            "prompt_version": "2.0.0",
            "prompt_content_hash": "b" * 64,
            "input_schema_version": "2.0",
            "output_schema_version": "2.0",
            "execution_provider_name": "mock",
            "execution_model_name": "migration-model",
            "execution_model_version": "1.0.0",
            "execution_model_revision": "migration",
            "provider_request_id": "migration-request",
            "input_token_count": 1,
            "output_token_count": 1,
            "latency_ms": 1,
            "last_attempt_started_at": now,
            "last_attempt_completed_at": now,
            "started_at": now,
            "completed_at": now,
        },
    )
    connection.execute(
        _table(connection, "llm_extraction_results_v2").insert(),
        {
            "id": analysis_result_id,
            "tenant_id": tenant_id,
            "analysis_run_id": analysis_run_id,
            "stage_run_id": stage_run_id,
            "stage_type": "TEXT_EXTRACTION",
            "schema_version": "2.0",
            "language": "ko",
            "issue_types": ["BREAKAGE"],
            "claims": [],
            "requested_actions": [{"action": "REFUND"}],
            "text_ambiguities": [],
            "summary": "Migration extraction result",
            "system_missing_information": [],
            "action_consistency": "MATCH",
            "completeness_rule_version": "1.0.0",
        },
    )
    connection.execute(
        _table(connection, "policy_ingestion_runs").insert(),
        {
            "id": ingestion_run_id,
            "corpus_name": "migration-corpus",
            "corpus_version": "1.0.0",
            "corpus_source_hash": "c" * 64,
            "manifest_hash": "d" * 64,
            "status": "SUCCEEDED",
            "started_at": now,
            "completed_at": now,
            "expected_document_count": 1,
            "ingested_document_count": 1,
            "expected_clause_count": 2,
            "ingested_clause_count": 2,
            "builder_version": "1.0.0",
            "schema_version": "1.0.0",
        },
    )
    connection.execute(
        _table(connection, "policy_documents").insert(),
        {
            "id": document_id,
            "tenant_id": tenant_id,
            "document_id": "MIGRATION-DOC",
            "document_version": "1.0.0",
            "title": "Migration Policy",
            "policy_type": "REFUND",
            "authority_level": "COMPANY_POLICY",
            "product_categories": ["GENERAL"],
            "effective_from": date(2026, 1, 1),
            "document_status": "ACTIVE",
            "source_type": "SYNTHETIC_REFERENCE",
            "source_hash": "e" * 64,
            "ingestion_run_id": ingestion_run_id,
        },
    )
    clause_table = _table(connection, "policy_clauses")
    connection.execute(
        clause_table.insert(),
        [
            {
                "id": clause_id,
                "tenant_id": tenant_id,
                "document_row_id": document_id,
                "document_id": "MIGRATION-DOC",
                "document_version": "1.0.0",
                "title": "Migration Policy",
                "clause_id": clause_name,
                "section_path": ["Migration"],
                "clause_type": "RULE",
                "text": f"Migration policy clause {position}",
                "policy_type": "REFUND",
                "product_categories": ["GENERAL"],
                "defect_types": ["BREAKAGE"],
                "actions": ["REFUND"],
                "requires_human_review": True,
                "effective_from": date(2026, 1, 1),
                "document_status": "ACTIVE",
                "source_type": "SYNTHETIC_REFERENCE",
                "source_hash": source_hash,
                "content_hash": content_hash,
                "ingestion_run_id": ingestion_run_id,
            }
            for position, clause_id, clause_name, source_hash, content_hash in (
                (1, citation_clause_id, "MIGRATION-CLAUSE-1", "f" * 64, "1" * 64),
                (2, other_clause_id, "MIGRATION-CLAUSE-2", "0" * 64, "2" * 64),
            )
        ],
    )
    connection.execute(
        _table(connection, "policy_embedding_profiles").insert(),
        {
            "id": embedding_profile_id,
            "profile_name": f"migration-{embedding_profile_id}",
            "profile_version": "1.0.0",
            "provider_name": "fixture",
            "model_artifact": "fixture",
            "model_revision": "fixture",
            "embedding_dimension": 2,
            "pooling_strategy": "mean",
            "normalize_embeddings": True,
            "query_instruction": "fixture",
            "query_instruction_hash": "3" * 64,
            "document_template_name": "fixture",
            "document_template_version": "1.0.0",
            "document_template_hash": "4" * 64,
            "max_query_tokens": 8,
            "max_document_tokens": 8,
        },
    )
    connection.execute(
        _table(connection, "policy_index_versions").insert(),
        {
            "id": index_id,
            "tenant_id": tenant_id,
            "index_name": f"migration-{index_id}",
            "index_version": "1.0.0",
            "corpus_name": "migration-corpus",
            "corpus_version": "1.0.0",
            "corpus_source_hash": "c" * 64,
            "lexical_profile_name": "fixture",
            "lexical_profile_version": "1.0.0",
            "lexical_k1": 1.2,
            "lexical_b": 0.75,
            "embedding_profile_id": embedding_profile_id,
            "fusion_profile_name": "fixture",
            "fusion_profile_version": "1.0.0",
            "fusion_rrf_k": 20,
            "fusion_lexical_weight": 1.0,
            "fusion_dense_weight": 1.0,
            "status": "ACTIVE",
            "expected_clause_count": 2,
            "indexed_clause_count": 2,
            "activated_at": now,
        },
    )
    connection.execute(
        _table(connection, "policy_query_builder_profiles").insert(),
        {
            "id": query_profile_id,
            "profile_name": f"migration-{query_profile_id}",
            "profile_version": "1.0.0",
            "strategy": "RAW",
            "schema_version": "1.0",
            "max_queries": 1,
            "max_query_tokens": 32,
            "filter_hint_policy": "none",
            "filter_hint_policy_version": "1.0.0",
            "profile_hash": "5" * 64,
        },
    )
    connection.execute(
        _table(connection, "policy_retrieval_runs").insert(),
        {
            "id": retrieval_run_id,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "analysis_run_id": analysis_run_id,
            "text_result_id": analysis_result_id,
            "strategy": "RAW",
            "status": "QUEUED",
            "as_of_date": date(2026, 8, 27),
            "top_k": 3,
            "query_builder_profile_id": query_profile_id,
            "base_index_version_id": index_id,
            "base_retrieval_profile_hash": "6" * 64,
            "multi_query_fusion_profile": "fixture",
            "multi_query_fusion_version": "1.0.0",
            "requested_by": user_id,
            "correlation_id": "migration-retrieval",
            "idempotency_key": f"migration-retrieval-{retrieval_run_id}",
            "request_hash": "7" * 64,
        },
    )
    connection.execute(
        _table(connection, "policy_citation_packs").insert(),
        {
            "id": citation_pack_id,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "retrieval_run_id": retrieval_run_id,
            "schema_version": "1.0",
            "retrieval_profile_hash": "6" * 64,
            "content_hash": "8" * 64,
        },
    )
    connection.execute(
        _table(connection, "policy_citation_pack_items").insert(),
        {
            "id": citation_item_id,
            "tenant_id": tenant_id,
            "citation_pack_id": citation_pack_id,
            "citation_id": "CIT-001",
            "rank": 1,
            "policy_clause_row_id": citation_clause_id,
            "policy_clause_id": "MIGRATION-CLAUSE-1",
            "document_id": "MIGRATION-DOC",
            "document_version": "1.0.0",
            "title": "Migration Policy",
            "section_path": ["Migration"],
            "clause_type": "RULE",
            "clause_text": "Migration policy clause 1",
            "effective_from": date(2026, 1, 1),
            "source_type": "SYNTHETIC_REFERENCE",
            "source_hash": "f" * 64,
            "retrieval_mode": "HYBRID",
            "query_strategy": "RAW",
            "matched_query_ids": ["Q-001"],
            "retrieval_profile_hash": "6" * 64,
        },
    )
    connection.execute(
        _table(connection, "grounding_profiles").insert(),
        {
            "id": grounding_profile_id,
            "profile_name": f"migration-{grounding_profile_id}",
            "profile_version": "1.0.0",
            "provider_name": "mock",
            "model_artifact": "fixture",
            "model_revision": "fixture",
            "prompt_name": "fixture",
            "prompt_version": "1.0.0",
            "prompt_hash": "9" * 64,
            "input_schema_version": "1.0",
            "output_schema_version": "1.0",
            "validator_name": "fixture",
            "validator_version": "1.0.0",
            "profile_hash": "a" * 64,
        },
    )
    connection.execute(
        _table(connection, "grounded_explanation_runs").insert(),
        {
            "id": grounding_run_id,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "retrieval_run_id": retrieval_run_id,
            "citation_pack_id": citation_pack_id,
            "grounding_profile_id": grounding_profile_id,
            "status": "QUEUED",
            "requested_by": user_id,
            "correlation_id": "migration-grounding",
            "idempotency_key": f"migration-grounding-{grounding_run_id}",
            "request_hash": "b" * 64,
        },
    )
    connection.execute(
        _table(connection, "policy_rule_sets").insert(),
        {
            "id": rule_set_id,
            "tenant_id": tenant_id,
            "rule_set_name": "migration-rule-set",
            "rule_set_version": "1.0.0",
            "effective_from": date(2026, 1, 1),
            "source_corpus_name": "migration-corpus",
            "source_corpus_version": "1.0.0",
            "source_corpus_hash": "c" * 64,
            "source_type": "SYNTHETIC_REFERENCE",
            "rule_schema_version": "1.0.0",
            "field_registry_version": "1.0.0",
            "operator_registry_version": "1.0.0",
            "aggregation_version": "1.0.0",
            "content_hash": "d" * 64,
        },
    )
    connection.execute(
        _table(connection, "policy_evaluation_runs").insert(),
        {
            "id": policy_evaluation_run_id,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "analysis_run_id": analysis_run_id,
            "rule_set_id": rule_set_id,
            "rule_set_version": "1.0.0",
            "rule_set_hash": "d" * 64,
            "as_of_date": date(2026, 8, 27),
            "status": "SUCCEEDED",
            "summary_status": "REQUIRE_HUMAN_REVIEW",
            "requested_by": user_id,
            "correlation_id": "migration-policy",
            "idempotency_key": f"migration-policy-{policy_evaluation_run_id}",
            "request_hash": "e" * 64,
            "started_at": now,
            "completed_at": now,
        },
    )
    connection.execute(
        _table(connection, "human_review_tasks").insert(),
        {
            "id": review_task_id,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "policy_evaluation_run_id": policy_evaluation_run_id,
            "task_type": "STANDARD_REVIEW",
            "priority": "NORMAL",
            "status": "RESOLVED",
            "current_assignee_id": user_id,
            "version": 2,
            "mapping_rule_name": "migration",
            "mapping_rule_version": "1.0.0",
            "resolved_at": resolved_at,
        },
    )
    connection.execute(
        _table(connection, "human_review_assignments").insert(),
        {
            "id": assignment_id,
            "tenant_id": tenant_id,
            "review_task_id": review_task_id,
            "assignee_id": user_id,
            "assigned_by": user_id,
            "assignment_type": "SELF_CLAIM",
            "assigned_at": now - timedelta(minutes=1),
            "released_at": None,
        },
    )
    connection.execute(
        _table(connection, "human_review_decisions").insert(),
        {
            "id": decision_id,
            "tenant_id": tenant_id,
            "review_task_id": review_task_id,
            "decision_type": "APPROVE_REFUND",
            "reason_codes": ["POLICY_MATCH"],
            "rationale": "Migration integrity decision rationale.",
            "outcome_relation": "CONSISTENT_WITH_RECOMMENDATION",
            "outcome_relation_rule_version": "1.0.0",
            "decided_by": user_id,
            "decided_at": resolved_at,
            "decision_schema_version": "1.0.0",
            "content_hash": "f" * 64,
        },
    )
    connection.execute(
        _table(connection, "human_review_decision_basis").insert(),
        {
            "id": basis_id,
            "tenant_id": tenant_id,
            "human_review_decision_id": decision_id,
            "basis_type": "POLICY_CITATION",
            "reference_id": "CIT-001",
            "policy_clause_row_id": citation_clause_id,
            "citation_item_id": citation_item_id,
        },
    )
    return LegacyGraph(
        tenant_id=tenant_id,
        user_id=user_id,
        case_id=case_id,
        other_case_id=other_case_id,
        analysis_result_id=analysis_result_id,
        retrieval_run_id=retrieval_run_id,
        grounding_run_id=grounding_run_id,
        policy_evaluation_run_id=policy_evaluation_run_id,
        review_task_id=review_task_id,
        assignment_id=assignment_id,
        decision_id=decision_id,
        citation_item_id=citation_item_id,
        citation_clause_id=citation_clause_id,
        other_clause_id=other_clause_id,
        resolved_at=resolved_at,
    )


def _constraint_names(connection: Connection, table_name: str) -> set[str]:
    schema = inspect(connection)
    return {
        str(item["name"])
        for item in (
            schema.get_check_constraints(table_name)
            + schema.get_foreign_keys(table_name)
            + schema.get_unique_constraints(table_name)
        )
        if item.get("name") is not None
    }


def _assert_constraint_rejects(
    connection: Connection,
    table: Table,
    values: dict[str, object],
    constraint_name: str,
) -> None:
    savepoint = connection.begin_nested()
    try:
        with pytest.raises(IntegrityError) as captured:
            connection.execute(table.insert(), values)
        diagnostic = getattr(captured.value.orig, "diag", None)
        assert diagnostic is not None
        assert diagnostic.constraint_name == constraint_name
    finally:
        savepoint.rollback()


def _assert_resolved_projection(
    connection: Connection,
    graph: LegacyGraph,
    *,
    assignee_id: UUID | None,
    assignment_released: bool,
) -> None:
    actual_assignee = connection.scalar(
        text("SELECT current_assignee_id FROM human_review_tasks WHERE id = :id"),
        {"id": graph.review_task_id},
    )
    released_at = connection.scalar(
        text("SELECT released_at FROM human_review_assignments WHERE id = :id"),
        {"id": graph.assignment_id},
    )
    assert actual_assignee == assignee_id
    assert (released_at is not None) is assignment_released
    if assignment_released:
        assert released_at == graph.resolved_at


def _assert_run_case_fences(connection: Connection, graph: LegacyGraph) -> None:
    now = datetime.now(UTC)
    events = (
        (
            "policy_retrieval_outbox_events",
            "retrieval_run_id",
            graph.retrieval_run_id,
            "fk_policy_retrieval_outbox_run_case",
        ),
        (
            "grounded_explanation_outbox_events",
            "grounded_explanation_run_id",
            graph.grounding_run_id,
            "fk_grounded_explanation_outbox_run_case",
        ),
        (
            "policy_evaluation_outbox_events",
            "policy_evaluation_run_id",
            graph.policy_evaluation_run_id,
            "fk_policy_evaluation_outbox_run_case",
        ),
        (
            "human_review_request_events",
            "policy_evaluation_run_id",
            graph.policy_evaluation_run_id,
            "fk_human_review_request_events_policy_run_case",
        ),
    )
    for table_name, run_column, run_id, constraint_name in events:
        table = _table(connection, table_name)
        _assert_constraint_rejects(
            connection,
            table,
            {
                "id": uuid4(),
                "tenant_id": graph.tenant_id,
                "case_id": graph.other_case_id,
                run_column: run_id,
                "correlation_id": f"mismatch-{table_name}",
                "status": "PENDING",
                "attempt_count": 0,
                "available_at": now,
            },
            constraint_name,
        )


def _assert_decision_basis_fences(connection: Connection, graph: LegacyGraph) -> None:
    table = _table(connection, "human_review_decision_basis")
    for basis_type in (
        "POLICY_RULE_RESULT",
        "POLICY_CITATION",
        "CASE_EVIDENCE",
        "ANALYSIS_RESULT",
    ):
        values: dict[str, object] = {
            "id": uuid4(),
            "tenant_id": graph.tenant_id,
            "human_review_decision_id": graph.decision_id,
            "basis_type": basis_type,
            "reference_id": f"INVALID-{basis_type}",
        }
        if basis_type == "POLICY_CITATION":
            values["analysis_result_id"] = graph.analysis_result_id
        else:
            values["citation_item_id"] = graph.citation_item_id
            values["policy_clause_row_id"] = graph.citation_clause_id
        _assert_constraint_rejects(
            connection,
            table,
            values,
            "ck_human_review_decision_basis_typed_reference_consistent",
        )

    _assert_constraint_rejects(
        connection,
        table,
        {
            "id": uuid4(),
            "tenant_id": graph.tenant_id,
            "human_review_decision_id": graph.decision_id,
            "basis_type": "POLICY_CITATION",
            "reference_id": "CIT-MISMATCH",
            "citation_item_id": graph.citation_item_id,
            "policy_clause_row_id": graph.other_clause_id,
        },
        "fk_human_review_decision_basis_citation_clause",
    )


def test_migration_0012_round_trip_normalizes_and_fences_integrity(
    migration_database: MigrationDatabase,
) -> None:
    config, engine = migration_database.config, migration_database.engine
    with engine.begin() as connection:
        graph = _seed_legacy_graph(connection)
        assert "ck_human_review_tasks_assignee_status_consistent" in _constraint_names(
            connection, "human_review_tasks"
        )
        _assert_resolved_projection(
            connection,
            graph,
            assignee_id=graph.user_id,
            assignment_released=False,
        )

    alembic_command.upgrade(config, REVISION_0012)
    with engine.begin() as connection:
        _assert_resolved_projection(
            connection,
            graph,
            assignee_id=None,
            assignment_released=True,
        )
        assert "ck_human_review_decision_basis_typed_reference_consistent" in _constraint_names(
            connection, "human_review_decision_basis"
        )
        assert "fk_human_review_decision_basis_citation_clause" in _constraint_names(
            connection, "human_review_decision_basis"
        )
        assert "uq_policy_citation_pack_items_tenant_id_clause" in _constraint_names(
            connection, "policy_citation_pack_items"
        )

    alembic_command.downgrade(config, REVISION_0011)
    with engine.begin() as connection:
        _assert_resolved_projection(
            connection,
            graph,
            assignee_id=graph.user_id,
            assignment_released=True,
        )
        basis_constraints = _constraint_names(connection, "human_review_decision_basis")
        assert "ck_human_review_decision_basis_one_typed_reference" in basis_constraints
        assert "ck_human_review_decision_basis_typed_reference_consistent" not in basis_constraints
        assert "fk_human_review_decision_basis_citation_clause" not in basis_constraints
        connection.execute(
            text(
                "UPDATE human_review_assignments SET released_at = NULL WHERE id = :assignment_id"
            ),
            {"assignment_id": graph.assignment_id},
        )

    alembic_command.upgrade(config, REVISION_0012)
    with engine.begin() as connection:
        _assert_resolved_projection(
            connection,
            graph,
            assignee_id=None,
            assignment_released=True,
        )
        _assert_run_case_fences(connection, graph)
        _assert_decision_basis_fences(connection, graph)
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert revision == REVISION_0012

    alembic_command.check(config)
