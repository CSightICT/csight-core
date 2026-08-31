"""Disposable PostgreSQL proof for runtime analysis-text erasure."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, select, text, update
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from alembic import command
from app.adapters.persistence.analysis_repositories import (
    SQLAlchemyLLMExtractionResultV2Repository,
)
from app.adapters.persistence.models import (
    AnalysisRunModel,
    AnalysisStageRunModel,
    CaseModel,
    CaseSensitivePayloadModel,
    DataLifecycleEventModel,
    LLMExtractionResultModel,
    LLMExtractionResultV2Model,
    TenantModel,
    UserModel,
)
from app.adapters.persistence.privacy_lifecycle import (
    create_privacy_lifecycle_unit_of_work_factory,
)
from app.adapters.persistence.session import create_session_factory
from app.application.privacy_lifecycle import PurgeExpiredSensitivePayloads
from app.bootstrap.settings import Settings
from app.interface.maintenance.privacy_lifecycle import run_retention_sweep
from app.platform.privacy_lifecycle import PURGED_CUSTOMER_MESSAGE

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
REVISION = "20260830_0027_analysis_text_erasure"
PREVIOUS = "20260830_0026_case_assignment_ownership"
MARKER = "CSIGHT-SYNTHETIC-PII-MARKER-0027"


@dataclass(frozen=True, slots=True)
class ErasureDatabase:
    engine: Engine
    factory: sessionmaker[Session]


@dataclass(frozen=True, slots=True)
class MigrationDatabase:
    config: Config
    engine: Engine


@pytest.fixture(scope="module")
def erasure_database() -> Generator[ErasureDatabase, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test analysis-text erasure")
    configured_url = Settings().database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for analysis-text erasure integration")
    source_url = make_url(configured_url)
    if not source_url.drivername.startswith("postgresql"):
        pytest.fail("analysis-text erasure integration requires PostgreSQL")

    database_name = f"csight_erasure_head_{uuid4().hex[:16]}"
    admin_engine = create_engine(
        source_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    temporary_engine: Engine | None = None
    created = False
    try:
        with admin_engine.connect() as connection:
            quoted_name = connection.dialect.identifier_preparer.quote(database_name)
            connection.exec_driver_sql(f"CREATE DATABASE {quoted_name} TEMPLATE template0")
            created = True
        temporary_url = source_url.set(database=database_name)
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            temporary_url.render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, "head")
        temporary_engine = create_engine(
            temporary_url,
            pool_pre_ping=True,
            poolclass=NullPool,
        )
        yield ErasureDatabase(
            engine=temporary_engine,
            factory=create_session_factory(temporary_engine),
        )
        command.check(config)
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        if created:
            with admin_engine.connect() as connection:
                quoted_name = connection.dialect.identifier_preparer.quote(database_name)
                connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {quoted_name} WITH (FORCE)")
        admin_engine.dispose()


@pytest.fixture(scope="module")
def previous_migration_database() -> Generator[MigrationDatabase, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test analysis-text erasure migration")
    configured_url = Settings().database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for analysis-text erasure migration")
    source_url = make_url(configured_url)
    database_name = f"csight_erasure_prev_{uuid4().hex[:16]}"
    admin_engine = create_engine(
        source_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    temporary_engine: Engine | None = None
    created = False
    try:
        with admin_engine.connect() as connection:
            quoted_name = connection.dialect.identifier_preparer.quote(database_name)
            connection.exec_driver_sql(f"CREATE DATABASE {quoted_name} TEMPLATE template0")
            created = True
        temporary_url = source_url.set(database=database_name)
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            temporary_url.render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, PREVIOUS)
        temporary_engine = create_engine(temporary_url, pool_pre_ping=True, poolclass=NullPool)
        yield MigrationDatabase(config=config, engine=temporary_engine)
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        if created:
            with admin_engine.connect() as connection:
                quoted_name = connection.dialect.identifier_preparer.quote(database_name)
                connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {quoted_name} WITH (FORCE)")
        admin_engine.dispose()


class StaticClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class UUIDs:
    def new_id(self) -> str:
        return str(uuid4())


def _seed_expired_analysis(factory: sessionmaker[Session]) -> tuple[UUID, UUID, UUID]:
    now = datetime.now(UTC)
    created_at = now - timedelta(days=2)
    tenant_id, user_id, case_id, run_id, stage_id = (uuid4() for _ in range(5))
    message = f"{MARKER} 고객이 환불을 요청합니다."
    with factory.begin() as session:
        session.add(
            TenantModel(
                id=tenant_id,
                slug=f"erasure-{tenant_id.hex[:16]}",
                name="Erasure Integration",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        session.add(
            UserModel(
                id=user_id,
                tenant_id=tenant_id,
                email=f"erasure-{user_id.hex}@example.test",
                password_hash="synthetic-hash",
                display_name="Erasure Admin",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        session.flush()
        session.add(
            CaseModel(
                id=case_id,
                tenant_id=tenant_id,
                domain_type="product_defect_cs",
                status="RECEIVED",
                order_ref="ERASURE-ORDER",
                product_ref="ERASURE-PRODUCT",
                customer_message=message,
                requested_action="REFUND",
                attributes={},
                created_by=user_id,
                current_assignee_id=None,
                assignment_version=0,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        session.flush()
        session.add(
            CaseSensitivePayloadModel(
                id=uuid4(),
                tenant_id=tenant_id,
                case_id=case_id,
                schema_version="case_sensitive_payload/1.0.0",
                customer_message=message,
                payload_sha256=hashlib.sha256(message.encode()).hexdigest(),
                retention_policy_version="integration/1d",
                expires_at=now - timedelta(days=1),
                purged_at=None,
                legacy_redacted_at=None,
                analysis_text_purged_at=None,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        session.flush()
        session.add(
            AnalysisRunModel(
                id=run_id,
                tenant_id=tenant_id,
                case_id=case_id,
                pipeline_name="product_defect_text_extraction",
                pipeline_version="2.0.0",
                execution_mode="PRIMARY",
                trigger_type="USER_REQUEST",
                status="SUCCEEDED",
                requested_by=user_id,
                correlation_id=f"erasure-{uuid4()}",
                idempotency_key=f"erasure-{uuid4()}",
                request_hash="a" * 64,
                requested_at=created_at,
                started_at=created_at,
                completed_at=created_at,
                failure_code=None,
                failure_message=None,
                failure_retryable=None,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        session.flush()
        session.add(
            AnalysisStageRunModel(
                id=stage_id,
                tenant_id=tenant_id,
                analysis_run_id=run_id,
                stage_type="TEXT_EXTRACTION",
                status="SUCCEEDED",
                attempt_count=1,
                provider_name="mock",
                model_name="mock-erasure",
                model_version="1.0",
                model_revision="integration",
                prompt_name="erasure",
                prompt_version="1.0",
                prompt_content_hash="b" * 64,
                input_schema_version="2.0",
                output_schema_version="2.0",
                execution_provider_name="mock",
                execution_model_name="mock-erasure",
                execution_model_version="1.0",
                execution_model_revision="integration",
                provider_request_id="synthetic",
                input_token_count=1,
                output_token_count=1,
                latency_ms=1,
                claim_token=None,
                lease_expires_at=None,
                next_attempt_at=None,
                last_attempt_started_at=created_at,
                last_attempt_completed_at=created_at,
                started_at=created_at,
                completed_at=created_at,
                failure_code=None,
                failure_message=None,
                failure_retryable=None,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        session.flush()
        session.add_all(
            [
                LLMExtractionResultModel(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    analysis_run_id=run_id,
                    stage_run_id=stage_id,
                    stage_type="TEXT_EXTRACTION",
                    schema_version="1.0",
                    language="ko",
                    issue_types=["BREAKAGE"],
                    claims=[
                        {
                            "type": "BREAKAGE",
                            "location": "UNKNOWN",
                            "description": MARKER,
                            "source_quote": MARKER,
                        }
                    ],
                    requested_action="REFUND",
                    missing_information=[MARKER],
                    summary=f"summary {MARKER}",
                    created_at=created_at,
                ),
                LLMExtractionResultV2Model(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    analysis_run_id=run_id,
                    stage_run_id=stage_id,
                    stage_type="TEXT_EXTRACTION",
                    schema_version="2.0",
                    language="ko",
                    issue_types=["BREAKAGE"],
                    claims=[
                        {
                            "type": "BREAKAGE",
                            "location": "UNKNOWN",
                            "description": MARKER,
                            "source_quote": MARKER,
                        }
                    ],
                    requested_actions=[{"action": "REFUND", "source_quote": MARKER}],
                    text_ambiguities=["DESCRIPTION_TOO_VAGUE"],
                    summary=f"summary {MARKER}",
                    system_missing_information=["IMAGE_EVIDENCE"],
                    action_consistency="MATCH",
                    completeness_rule_version="1.0.0",
                    created_at=created_at,
                ),
            ]
        )
    return tenant_id, user_id, case_id


def test_expired_purge_removes_model_text_and_keeps_results_readable(
    erasure_database: ErasureDatabase,
) -> None:
    tenant_id, _user_id, case_id = _seed_expired_analysis(erasure_database.factory)
    now = datetime.now(UTC)
    strict_engine = create_engine(
        erasure_database.engine.url,
        pool_pre_ping=True,
        poolclass=NullPool,
    )

    def _use_api_role(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("SET ROLE csight_api_role")
        finally:
            cursor.close()

    sqlalchemy_event.listen(strict_engine, "connect", _use_api_role)
    try:
        service = PurgeExpiredSensitivePayloads(
            uow_factory=create_privacy_lifecycle_unit_of_work_factory(strict_engine),
            clock=StaticClock(now),
            id_generator=UUIDs(),
        )
        report = run_retention_sweep(
            service,
            tenant_id=str(tenant_id),
            batch_size=100,
            max_batches=2,
        )
    finally:
        strict_engine.dispose()

    assert report.applied_count == 1
    with erasure_database.factory() as session:
        payload = session.scalar(
            select(CaseSensitivePayloadModel).where(
                CaseSensitivePayloadModel.tenant_id == tenant_id,
                CaseSensitivePayloadModel.case_id == case_id,
            )
        )
        case = session.get(CaseModel, case_id)
        v1 = session.scalar(
            select(LLMExtractionResultModel).where(LLMExtractionResultModel.tenant_id == tenant_id)
        )
        v2 = session.scalar(
            select(LLMExtractionResultV2Model).where(
                LLMExtractionResultV2Model.tenant_id == tenant_id
            )
        )
        event = session.scalar(
            select(DataLifecycleEventModel).where(
                DataLifecycleEventModel.tenant_id == tenant_id,
                DataLifecycleEventModel.event_type == "SENSITIVE_PAYLOAD_PURGED",
            )
        )
        assert payload is not None and case is not None and v1 is not None and v2 is not None
        assert payload.customer_message is None
        assert payload.analysis_text_purged_at == payload.purged_at
        assert case.customer_message == PURGED_CUSTOMER_MESSAGE
        assert v1.claims == [] and v1.missing_information == []
        assert v1.summary == PURGED_CUSTOMER_MESSAGE
        assert v2.claims == [] and v2.requested_actions == []
        assert v2.text_ambiguities == [] and v2.system_missing_information == []
        assert v2.summary == PURGED_CUSTOMER_MESSAGE
        assert event is not None
        assert event.actor_id is None
        assert event.details["initiator"] == "SYSTEM_RETENTION_SCHEDULER"
        assert event.details["analysis_text_redacted"] is True
        redacted_counts = event.details["redacted_row_counts"]
        assert isinstance(redacted_counts, dict)
        assert redacted_counts["llm_v1"] == 1
        assert redacted_counts["llm_v2"] == 1
        assert redacted_counts["generated_queries"] == 0
        assert redacted_counts["grounded_results"] == 0

        run_id = str(v2.analysis_run_id)
        reloaded = SQLAlchemyLLMExtractionResultV2Repository(session).get_by_run(
            tenant_id=str(tenant_id),
            analysis_run_id=run_id,
        )
        assert reloaded is not None
        assert reloaded.result.summary == PURGED_CUSTOMER_MESSAGE
        assert reloaded.result.claims == ()

        marker_count = session.scalar(
            text(
                """
                SELECT count(*) FROM (
                    SELECT customer_message AS value FROM cases WHERE tenant_id = :tenant_id
                    UNION ALL
                    SELECT customer_message FROM case_sensitive_payloads
                     WHERE tenant_id = :tenant_id
                    UNION ALL
                    SELECT claims::text FROM llm_extraction_results
                     WHERE tenant_id = :tenant_id
                    UNION ALL
                    SELECT missing_information::text FROM llm_extraction_results
                     WHERE tenant_id = :tenant_id
                    UNION ALL
                    SELECT summary FROM llm_extraction_results WHERE tenant_id = :tenant_id
                    UNION ALL
                    SELECT claims::text FROM llm_extraction_results_v2
                     WHERE tenant_id = :tenant_id
                    UNION ALL
                    SELECT requested_actions::text FROM llm_extraction_results_v2
                     WHERE tenant_id = :tenant_id
                    UNION ALL
                    SELECT summary FROM llm_extraction_results_v2 WHERE tenant_id = :tenant_id
                ) AS values_to_scan
                WHERE value LIKE :marker
                """
            ),
            {"tenant_id": tenant_id, "marker": f"%{MARKER}%"},
        )
        assert marker_count == 0

    with erasure_database.engine.begin() as connection:
        transaction = connection.begin_nested()
        try:
            with pytest.raises(DBAPIError, match="derived prose remains"):
                connection.execute(
                    update(LLMExtractionResultV2Model)
                    .where(LLMExtractionResultV2Model.tenant_id == tenant_id)
                    .values(summary=f"restored {MARKER}")
                )
                connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        finally:
            if transaction.is_active:
                transaction.rollback()


def test_upgrade_redacts_analysis_text_for_already_purged_cases(
    previous_migration_database: MigrationDatabase,
) -> None:
    config, engine = previous_migration_database.config, previous_migration_database.engine
    tenant_id, user_id, case_id, run_id, stage_id = (uuid4() for _ in range(5))
    created_at = datetime.now(UTC) - timedelta(days=3)
    purged_at = created_at + timedelta(days=2)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, 'Erasure Previous')"),
            {"id": tenant_id, "slug": f"erasure-prev-{tenant_id.hex[:12]}"},
        )
        connection.execute(
            text(
                "INSERT INTO users (id, tenant_id, email, password_hash, display_name) "
                "VALUES (:id, :tenant_id, :email, 'hash', 'Erasure Previous')"
            ),
            {
                "id": user_id,
                "tenant_id": tenant_id,
                "email": f"erasure-prev-{user_id.hex}@example.test",
            },
        )
        connection.execute(
            text(
                "INSERT INTO cases "
                "(id, tenant_id, order_ref, product_ref, customer_message, requested_action, "
                " attributes, created_by, created_at, updated_at) VALUES "
                "(:id, :tenant_id, 'ORDER', 'PRODUCT', :message, 'REFUND', '{}'::jsonb, "
                " :user_id, :created_at, :purged_at)"
            ),
            {
                "id": case_id,
                "tenant_id": tenant_id,
                "message": PURGED_CUSTOMER_MESSAGE,
                "user_id": user_id,
                "created_at": created_at,
                "purged_at": purged_at,
            },
        )
        connection.execute(
            text(
                "INSERT INTO case_sensitive_payloads "
                "(id, tenant_id, case_id, schema_version, customer_message, payload_sha256, "
                " retention_policy_version, expires_at, purged_at, legacy_redacted_at, "
                " created_at, updated_at) VALUES "
                "(:id, :tenant_id, :case_id, 'case_sensitive_payload/1.0.0', NULL, :digest, "
                " 'integration/1d', :expires_at, :purged_at, :purged_at, "
                " :created_at, :purged_at)"
            ),
            {
                "id": uuid4(),
                "tenant_id": tenant_id,
                "case_id": case_id,
                "digest": "a" * 64,
                "expires_at": created_at + timedelta(days=1),
                "created_at": created_at,
                "purged_at": purged_at,
            },
        )
        connection.execute(
            text(
                "INSERT INTO analysis_runs "
                "(id, tenant_id, case_id, pipeline_name, pipeline_version, execution_mode, "
                " trigger_type, status, requested_by, correlation_id, idempotency_key, "
                " request_hash, requested_at, started_at, completed_at, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :case_id, 'product_defect_text_extraction', '2.0.0', "
                " 'PRIMARY', 'USER_REQUEST', 'SUCCEEDED', :user_id, 'corr', 'idem', :digest, "
                " :created_at, :created_at, :created_at, :created_at, :created_at)"
            ),
            {
                "id": run_id,
                "tenant_id": tenant_id,
                "case_id": case_id,
                "user_id": user_id,
                "digest": "b" * 64,
                "created_at": created_at,
            },
        )
        connection.execute(
            text(
                "INSERT INTO analysis_stage_runs "
                "(id, tenant_id, analysis_run_id, stage_type, status, attempt_count, "
                " provider_name, model_name, model_version, model_revision, prompt_name, "
                " prompt_version, prompt_content_hash, input_schema_version, "
                " output_schema_version, execution_provider_name, execution_model_name, "
                " execution_model_version, latency_ms, started_at, completed_at, created_at, "
                " updated_at) VALUES "
                "(:id, :tenant_id, :run_id, 'TEXT_EXTRACTION', 'SUCCEEDED', 1, 'mock', "
                " 'mock', '1.0', 'rev', 'prompt', '1.0', :digest, '2.0', '2.0', 'mock', "
                " 'mock', '1.0', 1, :created_at, :created_at, :created_at, :created_at)"
            ),
            {
                "id": stage_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "digest": "c" * 64,
                "created_at": created_at,
            },
        )
        connection.execute(
            text(
                "INSERT INTO llm_extraction_results_v2 "
                "(id, tenant_id, analysis_run_id, stage_run_id, stage_type, schema_version, "
                " language, issue_types, claims, requested_actions, text_ambiguities, summary, "
                " system_missing_information, action_consistency, completeness_rule_version, "
                " created_at) VALUES "
                "(:id, :tenant_id, :run_id, :stage_id, 'TEXT_EXTRACTION', '2.0', 'ko', "
                " '[\"BREAKAGE\"]'::jsonb, CAST(:claims AS jsonb), "
                " CAST(:actions AS jsonb), '[]'::jsonb, "
                " :summary, '[]'::jsonb, 'MATCH', '1.0.0', :created_at)"
            ),
            {
                "id": uuid4(),
                "tenant_id": tenant_id,
                "run_id": run_id,
                "stage_id": stage_id,
                "claims": json.dumps([{"description": MARKER, "source_quote": MARKER}]),
                "actions": json.dumps([{"action": "REFUND", "source_quote": MARKER}]),
                "summary": f"summary {MARKER}",
                "created_at": created_at,
            },
        )

    command.upgrade(config, REVISION)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT payload.analysis_text_purged_at, result.claims, "
                "result.requested_actions, result.summary "
                "FROM case_sensitive_payloads AS payload "
                "JOIN analysis_runs AS run ON run.tenant_id = payload.tenant_id "
                " AND run.case_id = payload.case_id "
                "JOIN llm_extraction_results_v2 AS result ON result.tenant_id = run.tenant_id "
                " AND result.analysis_run_id = run.id "
                "WHERE payload.tenant_id = :tenant_id"
            ),
            {"tenant_id": tenant_id},
        ).one()
        assert row.analysis_text_purged_at == purged_at
        assert row.claims == [] and row.requested_actions == []
        assert row.summary == PURGED_CUSTOMER_MESSAGE

    with pytest.raises(DBAPIError, match="redacted prose cannot be restored"):
        command.downgrade(config, PREVIOUS)
