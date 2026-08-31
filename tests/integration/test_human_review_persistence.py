"""PostgreSQL human-review workflow, concurrency, and immutability gates."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from alembic import command as alembic_command
from app.adapters.external_action import DeterministicDryRunExternalActionAdapter
from app.adapters.persistence import case_resolution as case_resolution_persistence
from app.adapters.persistence.case_assignment import SQLAlchemyCaseAssignmentRepository
from app.adapters.persistence.case_resolution import SQLAlchemyCaseResolutionRepository
from app.adapters.persistence.human_review import SQLAlchemyHumanReviewRepository
from app.adapters.persistence.models import (
    AnalysisRunModel,
    AnalysisStageRunModel,
    CaseAssignmentActionModel,
    CaseAssignmentModel,
    CaseModel,
    CaseResolutionModel,
    CaseResolutionRequestEventModel,
    CaseSensitivePayloadModel,
    CustomerCommunicationSimulationModel,
    DataLifecycleEventModel,
    ExternalActionIntentModel,
    ExternalActionSimulationAttemptModel,
    ExternalActionSimulationRequestEventModel,
    ExternalActionSimulationResultModel,
    HumanReviewActionModel,
    HumanReviewAssignmentModel,
    HumanReviewDecisionModel,
    HumanReviewPacketModel,
    HumanReviewRequestEventModel,
    HumanReviewTaskModel,
    LLMExtractionResultV2Model,
    PolicyEvaluationInputSnapshotModel,
    PolicyEvaluationOutboxEventModel,
    PolicyEvaluationRunModel,
    ReviewReportModel,
    RoleModel,
    TenantModel,
    UserModel,
    UserRoleModel,
)
from app.adapters.persistence.poc_reporting import SQLAlchemyPocReportingRepository
from app.adapters.persistence.policy_engine import SQLAlchemyPolicyEngineRepository
from app.adapters.persistence.policy_ingestion import ingest_validated_policy_corpus
from app.adapters.persistence.privacy_lifecycle import (
    create_privacy_lifecycle_unit_of_work_factory,
)
from app.adapters.persistence.session import create_session_factory, session_scope
from app.application.case_resolution import (
    CaseResolutionRequestedCommand,
    ExecuteExternalActionSimulation,
    ExternalActionSimulationRequestedCommand,
    ProcessCaseResolution,
)
from app.application.policy_engine import ExecutePolicyEvaluation, ExecutePolicyEvaluationCommand
from app.application.privacy_lifecycle import PurgeExpiredSensitivePayloads
from app.bootstrap.settings import Settings
from app.platform.async_reliability import AsyncEventIntegrityError
from app.platform.case_assignment import CaseAssignmentVersionConflictError
from app.platform.case_resolution import ResolutionStatus
from app.platform.errors import ForbiddenError
from app.platform.human_review import (
    AdditionalEvidenceReason,
    DecisionBasisReference,
    DecisionBasisType,
    DecisionReason,
    DuplicateHumanDecisionError,
    EscalationReason,
    HumanDecisionRequest,
    HumanDecisionType,
    InvalidDecisionBasisError,
    ReviewPacketIntegrityError,
    ReviewTaskAlreadyClaimedError,
    ReviewTaskNotFoundError,
)
from app.platform.policy_engine import PolicyEvaluationRun, PolicyRuleSet
from app.platform.tenant import Principal, Role
from app.ports.human_review import ReviewQueueQuery

pytestmark = pytest.mark.integration
TERMINAL_PRIVACY_MARKER = "개인정보삭제표식0029"


@dataclass(frozen=True, slots=True)
class HumanReviewIntegrationContext:
    engine: Engine
    factory: sessionmaker[Session]


@pytest.fixture(scope="module")
def human_review_database() -> Generator[HumanReviewIntegrationContext, None, None]:
    """Run this module against a disposable migrated PostgreSQL database."""

    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test human review persistence")
    settings = Settings()
    configured_url = settings.database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for human review persistence tests")
    source_url = make_url(configured_url)
    if not source_url.drivername.startswith("postgresql"):
        pytest.fail("human review persistence tests require PostgreSQL")

    database_name = f"csight_hr_it_{uuid4().hex[:20]}"
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

        project_root = Path(__file__).resolve().parents[2]
        config = Config(str(project_root / "alembic.ini"))
        migration_url = temporary_url.render_as_string(hide_password=False)
        config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))
        alembic_command.upgrade(config, "head")

        temporary_engine = create_engine(temporary_url, pool_pre_ping=True)
        factory = create_session_factory(temporary_engine)
        _seed_human_review_prerequisites(factory=factory, project_root=project_root)
        yield HumanReviewIntegrationContext(engine=temporary_engine, factory=factory)
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
                            text("SELECT count(*) FROM pg_database WHERE datname = :database_name"),
                            {"database_name": database_name},
                        )
                        if remaining != 0:
                            raise RuntimeError(
                                "temporary human review integration database was not removed"
                            )
            finally:
                admin_engine.dispose()


def _seed_human_review_prerequisites(*, factory: sessionmaker[Session], project_root: Path) -> None:
    with session_scope(factory) as session:
        ingest_validated_policy_corpus(
            session=session,
            corpus_root=project_root / "data/policy_corpus",
            allow_synthetic_tenant_creation=True,
        )
        tenants = {
            row.slug: row.id
            for row in session.scalars(
                select(TenantModel).where(
                    TenantModel.slug.in_(("csight-demo-brand", "csight-demo-retail"))
                )
            ).all()
        }
        assert tenants.keys() == {"csight-demo-brand", "csight-demo-retail"}
        admin_role_id = uuid4()
        session.add(RoleModel(id=admin_role_id, name=Role.ADMIN.value))
        for slug, tenant_id in tenants.items():
            user_id = uuid4()
            session.add(
                UserModel(
                    id=user_id,
                    tenant_id=tenant_id,
                    email=f"admin@{slug}.integration.test",
                    password_hash="integration-test-password-hash",
                    display_name=f"{slug} Integration Admin",
                )
            )
            session.add(UserRoleModel(tenant_id=tenant_id, user_id=user_id, role_id=admin_role_id))

    rule_sets_path = project_root / "data/policy_rules/normalized/policy_rule_sets_v1.jsonl"
    rule_sets = tuple(
        PolicyRuleSet.model_validate_json(line)
        for line in rule_sets_path.read_text(encoding="utf-8").splitlines()
        if line
    )
    SQLAlchemyPolicyEngineRepository(factory).ingest(rule_sets)

    now = datetime.now(UTC)
    with factory.begin() as session:
        tenant_id = session.scalar(
            select(TenantModel.id).where(TenantModel.slug == "csight-demo-brand")
        )
        admin = session.scalar(
            select(UserModel)
            .join(
                UserRoleModel,
                (UserRoleModel.tenant_id == UserModel.tenant_id)
                & (UserRoleModel.user_id == UserModel.id),
            )
            .join(RoleModel, RoleModel.id == UserRoleModel.role_id)
            .where(
                TenantModel.slug == "csight-demo-brand",
                RoleModel.name == Role.ADMIN.value,
            )
            .join(TenantModel, TenantModel.id == UserModel.tenant_id)
        )
        assert tenant_id is not None and admin is not None
        case_id, analysis_id, stage_id = uuid4(), uuid4(), uuid4()
        session.add(
            CaseModel(
                id=case_id,
                tenant_id=tenant_id,
                domain_type="product_defect_cs",
                status="RECEIVED",
                order_ref="HR-INTEGRATION-ORDER",
                product_ref="HR-INTEGRATION-PRODUCT",
                customer_message="합성 테스트: 용기가 파손되어 환불을 요청합니다.",
                requested_action="REFUND",
                attributes={
                    "days_since_purchase": 3,
                    "order_amount": 500_000,
                    "product_category": "GENERAL",
                    "external_action_input": {
                        "amount": "500000.0000",
                        "currency": "KRW",
                    },
                },
                created_by=admin.id,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        customer_message = "합성 테스트: 용기가 파손되어 환불을 요청합니다."
        session.add(
            CaseSensitivePayloadModel(
                id=uuid4(),
                tenant_id=tenant_id,
                case_id=case_id,
                schema_version="case_sensitive_payload/1.0.0",
                customer_message=customer_message,
                payload_sha256=hashlib.sha256(customer_message.encode("utf-8")).hexdigest(),
                retention_policy_version="integration/30d",
                expires_at=now + timedelta(days=30),
                purged_at=None,
                legacy_redacted_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            AnalysisRunModel(
                id=analysis_id,
                tenant_id=tenant_id,
                case_id=case_id,
                pipeline_name="product_defect_text_extraction",
                pipeline_version="2.0.0",
                trigger_type="USER_REQUEST",
                status="SUCCEEDED",
                requested_by=admin.id,
                correlation_id=f"hr-integration-{uuid4()}",
                idempotency_key=f"hr-integration-{uuid4()}",
                request_hash="a" * 64,
                requested_at=now,
                started_at=now,
                completed_at=now,
                failure_code=None,
                failure_message=None,
                failure_retryable=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            AnalysisStageRunModel(
                id=stage_id,
                tenant_id=tenant_id,
                analysis_run_id=analysis_id,
                stage_type="TEXT_EXTRACTION",
                status="SUCCEEDED",
                attempt_count=1,
                provider_name="mock",
                model_name="csight-mock-llm",
                model_version="0.1.0",
                model_revision="integration",
                prompt_name="product-defect-text-extraction",
                prompt_version="2.0.0",
                prompt_content_hash="b" * 64,
                input_schema_version="2.0",
                output_schema_version="2.0",
                execution_provider_name="mock",
                execution_model_name="csight-mock-llm",
                execution_model_version="0.1.0",
                execution_model_revision="integration",
                provider_request_id="human-review-integration",
                input_token_count=1,
                output_token_count=1,
                latency_ms=1,
                claim_token=None,
                lease_expires_at=None,
                next_attempt_at=None,
                last_attempt_started_at=now,
                last_attempt_completed_at=now,
                started_at=now,
                completed_at=now,
                failure_code=None,
                failure_message=None,
                failure_retryable=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            LLMExtractionResultV2Model(
                id=uuid4(),
                tenant_id=tenant_id,
                analysis_run_id=analysis_id,
                stage_run_id=stage_id,
                stage_type="TEXT_EXTRACTION",
                schema_version="2.0",
                language="ko",
                issue_types=["BREAKAGE"],
                claims=[
                    {
                        "type": "BREAKAGE",
                        "location": "UNKNOWN",
                        "description": "용기가 파손됨",
                        "source_quote": "용기가 파손되어",
                    }
                ],
                requested_actions=[{"action": "REFUND", "source_quote": "환불을 요청합니다"}],
                text_ambiguities=[],
                summary="용기 파손에 대한 환불 요청",
                system_missing_information=["IMAGE_EVIDENCE"],
                action_consistency="MATCH",
                completeness_rule_version="1.0.0",
                created_at=now,
            )
        )


def _mark_policy_event_published(
    factory: sessionmaker[Session], event_id: UUID
) -> PolicyEvaluationOutboxEventModel:
    with factory.begin() as session:
        event = session.get(PolicyEvaluationOutboxEventModel, event_id)
        assert event is not None
        event.status = "PUBLISHED"
        event.attempt_count = 1
        event.published_at = datetime.now(UTC)
        session.flush()
        return event


def _mark_review_event_published(
    factory: sessionmaker[Session], event_id: UUID
) -> HumanReviewRequestEventModel:
    with factory.begin() as session:
        event = session.get(HumanReviewRequestEventModel, event_id)
        assert event is not None
        event.status = "PUBLISHED"
        event.attempt_count = 1
        event.published_at = datetime.now(UTC)
        session.flush()
        return event


def _mark_review_event_processing(
    factory: sessionmaker[Session], event_id: UUID
) -> HumanReviewRequestEventModel:
    with factory.begin() as session:
        event = session.get(HumanReviewRequestEventModel, event_id)
        assert event is not None
        event.status = "PROCESSING"
        event.attempt_count = 1
        event.claimed_at = datetime.now(UTC)
        event.claim_token = uuid4()
        event.claimed_by = "integration-dispatcher"
        event.published_at = None
        session.flush()
        return event


def _mark_resolution_event_published(
    factory: sessionmaker[Session], event_id: UUID
) -> CaseResolutionRequestEventModel:
    with factory.begin() as session:
        event = session.get(CaseResolutionRequestEventModel, event_id)
        assert event is not None
        event.status = "PUBLISHED"
        event.attempt_count = 1
        event.published_at = datetime.now(UTC)
        session.flush()
        return event


def _mark_simulation_event_published(
    factory: sessionmaker[Session], event_id: UUID
) -> ExternalActionSimulationRequestEventModel:
    with factory.begin() as session:
        event = session.get(ExternalActionSimulationRequestEventModel, event_id)
        assert event is not None
        event.status = "PUBLISHED"
        event.attempt_count = 1
        event.published_at = datetime.now(UTC)
        session.flush()
        return event


def test_review_event_task_packet_claim_resolve_and_tenant_isolation(
    human_review_database: HumanReviewIntegrationContext,
) -> None:
    factory = human_review_database.factory
    with factory() as session:
        source = session.execute(
            select(
                AnalysisRunModel.tenant_id,
                AnalysisRunModel.case_id,
                AnalysisRunModel.id,
                AnalysisRunModel.requested_by,
            )
            .join(
                LLMExtractionResultV2Model,
                LLMExtractionResultV2Model.analysis_run_id == AnalysisRunModel.id,
            )
            .join(TenantModel, TenantModel.id == AnalysisRunModel.tenant_id)
            .where(
                AnalysisRunModel.status == "SUCCEEDED",
                TenantModel.slug == "csight-demo-brand",
            )
            .order_by(AnalysisRunModel.created_at.desc())
            .limit(1)
        ).one_or_none()
        other_tenant = session.scalar(
            select(TenantModel.id).where(TenantModel.slug == "csight-demo-retail")
        )
        admin = session.scalar(
            select(UserModel)
            .join(
                UserRoleModel,
                (UserRoleModel.tenant_id == UserModel.tenant_id)
                & (UserRoleModel.user_id == UserModel.id),
            )
            .join(RoleModel, RoleModel.id == UserRoleModel.role_id)
            .join(TenantModel, TenantModel.id == UserModel.tenant_id)
            .where(RoleModel.name == "ADMIN", TenantModel.slug == "csight-demo-brand")
            .limit(1)
        )
    if source is None or other_tenant is None or admin is None:
        pytest.skip("seeded analysis, tenants, and admin are required")
    tenant_id, case_id, analysis_id, requested_by = map(str, source)
    assert admin.tenant_id == UUID(tenant_id)
    with factory.begin() as session:
        case_row = session.get(CaseModel, UUID(case_id))
        assert case_row is not None
        case_row.attributes = {
            **case_row.attributes,
            "synthetic_commerce_context": {
                "schema_version": "synthetic_commerce_context/1.0.0",
                "data_classification": "SYNTHETIC_DEMO_ONLY",
                "customer": {
                    "customer_id": "CUST-DEMO-100002",
                    "display_name": TERMINAL_PRIVACY_MARKER,
                    "phone_masked": "010-****-4821",
                    "membership_tier": "GOLD",
                },
                "order": {
                    "sales_channel": "CSight 마켓",
                    "seller_name": "CSight 리빙",
                    "ordered_at": "2026-08-25T01:14:00Z",
                    "product_display_name": "화이트랩 바디 로션 300",
                    "sku": "CS-DEMO-FLP-002",
                    "quantity": 1,
                    "unit_price": "18900",
                    "merchandise_amount": "18900",
                    "shipping_fee": "0",
                    "discount_amount": "0",
                    "paid_amount": "18900",
                    "currency": "KRW",
                    "payment_method_masked": "신용카드 **** 1042",
                    "payment_status": "PAID",
                },
                "delivery": {
                    "shipping_address_ref": "DEMO-V2-ADDR-002",
                    "recipient": TERMINAL_PRIVACY_MARKER,
                    "phone_masked": "010-****-4821",
                    "postal_code": "06236",
                    "address_line1": "서울특별시 데모구 시연로 41",
                    "address_line2": "가상아파트 203동 804호",
                    "carrier": "CSight 로지스",
                    "tracking_number_masked": "CSL-****-0202",
                    "delivered_at": "2026-08-27T05:22:00Z",
                },
                "disclaimer": "FICTIONAL_IDENTITIES_CONTACTS_ADDRESSES_AND_TRANSACTIONS",
            },
        }

    policy_repository = SQLAlchemyPolicyEngineRepository(factory)
    policy_run, _ = policy_repository.create(
        tenant_id=tenant_id,
        case_id=case_id,
        analysis_run_id=analysis_id,
        as_of_date=date(2026, 2, 1),
        requested_by=requested_by,
        correlation_id=f"review-corr-{uuid4()}",
        idempotency_key=f"review-policy-{uuid4()}",
        request_hash="f" * 64,
    )
    with factory() as session:
        policy_event = session.scalar(
            select(PolicyEvaluationOutboxEventModel).where(
                PolicyEvaluationOutboxEventModel.policy_evaluation_run_id == UUID(policy_run.id)
            )
        )
    assert policy_event is not None
    policy_event = _mark_policy_event_published(factory, policy_event.id)
    disposition = ExecutePolicyEvaluation(policy_repository).execute(
        ExecutePolicyEvaluationCommand(
            event_id=str(policy_event.id),
            tenant_id=tenant_id,
            case_id=case_id,
            policy_evaluation_run_id=policy_run.id,
            correlation_id=policy_run.correlation_id,
        )
    )
    assert disposition == "SUCCEEDED"

    review_repository = SQLAlchemyHumanReviewRepository(factory)
    with factory() as session:
        review_event = session.scalar(
            select(HumanReviewRequestEventModel).where(
                HumanReviewRequestEventModel.policy_evaluation_run_id == UUID(policy_run.id)
            )
        )
    assert review_event is not None
    # Covers broker-confirm-before-DB-mark crash ordering: a consumer may see
    # PROCESSING while the dispatcher's publish-confirm transaction has not run.
    review_event = _mark_review_event_processing(factory, review_event.id)
    task, replayed = review_repository.create_from_policy_evaluation(
        event_id=str(review_event.id),
        tenant_id=tenant_id,
        case_id=case_id,
        policy_evaluation_run_id=policy_run.id,
        correlation_id=policy_run.correlation_id,
    )
    replay, was_replayed = review_repository.create_from_policy_evaluation(
        event_id=str(review_event.id),
        tenant_id=tenant_id,
        case_id=case_id,
        policy_evaluation_run_id=policy_run.id,
        correlation_id=policy_run.correlation_id,
    )
    assert replayed is False and was_replayed is True and replay.id == task.id
    detail = review_repository.get(tenant_id=tenant_id, task_id=task.id)
    assert detail is not None
    initial_hash = detail.packet.packet_hash

    def claim(_index: int) -> str:
        try:
            review_repository.claim(
                tenant_id=tenant_id,
                task_id=task.id,
                actor_id=str(admin.id),
                roles=frozenset({Role.ADMIN}),
                expected_version=1,
            )
        except ReviewTaskAlreadyClaimedError:
            return "CONFLICT"
        return "SUCCESS"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(claim, range(2)))
    assert outcomes == ["CONFLICT", "SUCCESS"]
    claimed = review_repository.get(tenant_id=tenant_id, task_id=task.id)
    assert claimed is not None and claimed.task.version == 2

    with pytest.raises(ForbiddenError):
        review_repository.resolve(
            tenant_id=tenant_id,
            task_id=task.id,
            actor_id=str(admin.id),
            roles=frozenset({Role.REVIEWER}),
            expected_version=2,
            request=_decision(str(claimed.rule_results[0]["id"])),
        )
    with pytest.raises(InvalidDecisionBasisError):
        review_repository.resolve(
            tenant_id=tenant_id,
            task_id=task.id,
            actor_id=str(admin.id),
            roles=frozenset({Role.ADMIN}),
            expected_version=2,
            request=_decision(str(uuid4())),
        )

    with factory.begin() as session:
        packet_row = session.scalar(
            select(HumanReviewPacketModel).where(
                HumanReviewPacketModel.review_task_id == UUID(task.id)
            )
        )
        assert packet_row is not None
        original_case_snapshot = dict(packet_row.case_metadata_snapshot)
        packet_row.case_metadata_snapshot = {
            **original_case_snapshot,
            "tampered": True,
        }
    with pytest.raises(ReviewPacketIntegrityError):
        review_repository.resolve(
            tenant_id=tenant_id,
            task_id=task.id,
            actor_id=str(admin.id),
            roles=frozenset({Role.ADMIN}),
            expected_version=2,
            request=_decision(str(claimed.rule_results[0]["id"])),
        )
    with factory.begin() as session:
        packet_row = session.scalar(
            select(HumanReviewPacketModel).where(
                HumanReviewPacketModel.review_task_id == UUID(task.id)
            )
        )
        assert packet_row is not None
        packet_row.case_metadata_snapshot = original_case_snapshot

    resolved, decision = review_repository.resolve(
        tenant_id=tenant_id,
        task_id=task.id,
        actor_id=str(admin.id),
        roles=frozenset({Role.ADMIN}),
        expected_version=2,
        request=_decision(str(claimed.rule_results[0]["id"])),
    )
    assert resolved.status.value == "RESOLVED" and resolved.version == 3
    assert resolved.current_assignee_id is None
    assert decision.decided_by == str(admin.id)
    assert task.id not in {
        item.id
        for item in review_repository.list(
            tenant_id=tenant_id,
            actor_id=str(admin.id),
            query=ReviewQueueQuery(assigned_to_me=True),
        )
    }

    # Decision + initial Resolution/Event/request are committed atomically by Resolve.
    with factory() as session:
        resolution = session.scalar(
            select(CaseResolutionModel).where(CaseResolutionModel.case_id == UUID(case_id))
        )
        resolution_event = session.scalar(
            select(CaseResolutionRequestEventModel).where(
                CaseResolutionRequestEventModel.human_decision_id == UUID(decision.id)
            )
        )
        case_status = session.scalar(select(CaseModel.status).where(CaseModel.id == UUID(case_id)))
    assert resolution is not None and resolution.status == "DECISION_RECORDED"
    assert resolution_event is not None and resolution_event.status == "PENDING"
    assert case_status == "RECEIVED"

    resolution_event = _mark_resolution_event_published(factory, resolution_event.id)
    resolution_repository = SQLAlchemyCaseResolutionRepository(factory)
    assert (
        ProcessCaseResolution(resolution_repository).execute(
            CaseResolutionRequestedCommand(
                event_id=str(resolution_event.id),
                tenant_id=tenant_id,
                case_id=case_id,
                resolution_id=str(resolution.id),
                correlation_id=resolution_event.correlation_id,
            )
        )
        == "ACTION_READY"
    )
    with factory() as session:
        simulation_event = session.scalar(
            select(ExternalActionSimulationRequestEventModel)
            .join(
                ExternalActionIntentModel,
                ExternalActionIntentModel.id
                == ExternalActionSimulationRequestEventModel.external_action_intent_id,
            )
            .where(ExternalActionIntentModel.resolution_id == resolution.id)
        )
    assert simulation_event is not None
    simulation_event = _mark_simulation_event_published(factory, simulation_event.id)
    simulation_command = ExternalActionSimulationRequestedCommand(
        event_id=str(simulation_event.id),
        tenant_id=tenant_id,
        case_id=case_id,
        external_action_intent_id=str(simulation_event.external_action_intent_id),
        correlation_id=simulation_event.correlation_id,
    )
    simulation_use_case = ExecuteExternalActionSimulation(
        resolution_repository,
        DeterministicDryRunExternalActionAdapter(),
    )
    assert simulation_use_case.execute(simulation_command) == "ACTION_DRY_RUN_VALIDATED"
    assert simulation_use_case.execute(simulation_command) == "NOOP"
    resolution_id = resolution.id
    with factory() as session:
        persisted_resolution = session.get(CaseResolutionModel, resolution_id)
        intent_count = session.scalar(
            select(func.count(ExternalActionIntentModel.id)).where(
                ExternalActionIntentModel.resolution_id == resolution_id
            )
        )
        attempt_count = session.scalar(
            select(func.count(ExternalActionSimulationAttemptModel.id)).where(
                ExternalActionSimulationAttemptModel.resolution_id == resolution_id
            )
        )
        result = session.scalar(
            select(ExternalActionSimulationResultModel).where(
                ExternalActionSimulationResultModel.resolution_id == resolution_id
            )
        )
        case_status = session.scalar(select(CaseModel.status).where(CaseModel.id == UUID(case_id)))
        assert persisted_resolution is not None
        assert persisted_resolution.status == "ACTION_DRY_RUN_VALIDATED"
        assert persisted_resolution.version == 4
        assert intent_count == 1 and attempt_count == 1
        assert result is not None and result.side_effects_performed is False
        assert case_status == "RECEIVED"

    reporting_repository = SQLAlchemyPocReportingRepository(factory)
    report = reporting_repository.get_review_report(tenant_id=tenant_id, case_id=case_id)
    assert report is not None
    assert report.resolution_version == 4
    assert report.resolution_snapshot["status"] == "ACTION_DRY_RUN_VALIDATED"
    commerce_snapshot = report.case_snapshot["synthetic_commerce_context"]
    assert isinstance(commerce_snapshot, dict)
    assert commerce_snapshot["data_classification"] == "SYNTHETIC_DEMO_ONLY"
    assert report.data_scope["direct_contact_values_included"] is False
    report_result = report.dry_run_snapshot["result"]
    assert isinstance(report_result, dict)
    assert report_result["side_effects_performed"] is False
    assert (
        reporting_repository.get_review_report(tenant_id=str(other_tenant), case_id=case_id) is None
    )
    with factory() as session:
        assert (
            session.scalar(
                select(func.count(ReviewReportModel.id)).where(
                    ReviewReportModel.resolution_id == resolution_id
                )
            )
            == 1
        )

    summary = reporting_repository.get_poc_summary(tenant_id=tenant_id)
    # This workflow is explicitly synthetic.  It must exercise the full human-review and
    # DRY_RUN persistence path without contaminating customer-pilot metrics, whose immutable
    # source boundary admits only PILOT_LIVE cases.
    assert summary.eligible_case_count == 0
    assert summary.excluded_case_count == 1
    for metric in (
        summary.review_time,
        summary.recommendation_difference_rate,
        summary.additional_evidence_request_rate,
        summary.action_input_missing_rate,
        summary.dry_run_success_rate,
        summary.analysis_failure_rate,
        summary.analysis_partial_success_rate,
    ):
        assert metric.denominator == 0
        assert metric.sample_count == 0
        assert metric.numerator == 0
        assert metric.value is None
    empty_summary = reporting_repository.get_poc_summary(tenant_id=str(other_tenant))
    assert empty_summary.review_time.denominator == 0
    assert empty_summary.review_time.value is None

    with factory.begin() as session:
        report_row = session.scalar(
            select(ReviewReportModel).where(ReviewReportModel.resolution_id == resolution_id)
        )
        assert report_row is not None
        original_report_snapshot = dict(report_row.case_snapshot)
        report_row.case_snapshot = {**original_report_snapshot, "tampered": True}
    with pytest.raises(ValidationError, match="content hash mismatch"):
        reporting_repository.get_review_report(tenant_id=tenant_id, case_id=case_id)
    with factory.begin() as session:
        report_row = session.scalar(
            select(ReviewReportModel).where(ReviewReportModel.resolution_id == resolution_id)
        )
        assert report_row is not None
        report_row.case_snapshot = original_report_snapshot

    with factory.begin() as session:
        decision_row = session.scalar(
            select(HumanReviewDecisionModel).where(
                HumanReviewDecisionModel.review_task_id == UUID(task.id)
            )
        )
        assert decision_row is not None
        original_rationale = decision_row.rationale
        decision_row.rationale = "변조된 결정 근거입니다."
    with pytest.raises(ReviewPacketIntegrityError):
        review_repository.get(tenant_id=tenant_id, task_id=task.id)
    with pytest.raises(ReviewPacketIntegrityError):
        review_repository.resolve(
            tenant_id=tenant_id,
            task_id=task.id,
            actor_id=str(admin.id),
            roles=frozenset({Role.ADMIN}),
            expected_version=resolved.version,
            request=_decision(str(claimed.rule_results[0]["id"])),
        )
    with factory.begin() as session:
        decision_row = session.scalar(
            select(HumanReviewDecisionModel).where(
                HumanReviewDecisionModel.review_task_id == UUID(task.id)
            )
        )
        assert decision_row is not None
        persisted_resolution = session.scalar(
            select(CaseResolutionModel)
            .where(CaseResolutionModel.id == resolution_id)
            .with_for_update()
        )
        assert persisted_resolution is not None
        transition = case_resolution_persistence._transition_resolution  # pyright: ignore[reportPrivateUsage]
        transition(
            session,
            resolution=persisted_resolution,
            to_status=ResolutionStatus.MANUAL_FOLLOW_UP_REQUIRED,
            now=datetime.now(UTC),
            human_decision_id=decision_row.id,
            payload={"failure_code": "CASE_RESOLUTION_INTEGRITY_FAILED"},
            failure_code="CASE_RESOLUTION_INTEGRITY_FAILED",
            failure_message="Source integrity failed while recording terminal failure.",
        )
        decision_row.rationale = original_rationale

    degraded = reporting_repository.get_review_report(tenant_id=tenant_id, case_id=case_id)
    assert degraded is not None
    assert degraded.resolution_version == 5
    assert degraded.resolution_snapshot["status"] == "MANUAL_FOLLOW_UP_REQUIRED"
    assert degraded.data_scope["report_generation"] == ("DEGRADED_INTEGRITY_FAILURE_SNAPSHOT")
    assert degraded.data_scope["source_content_included"] is False
    with factory() as session:
        persisted_resolution = session.get(CaseResolutionModel, resolution_id)
        report_count = session.scalar(
            select(func.count(ReviewReportModel.id)).where(
                ReviewReportModel.resolution_id == resolution_id
            )
        )
        assert persisted_resolution is not None
        assert persisted_resolution.status == "MANUAL_FOLLOW_UP_REQUIRED"
        assert report_count == 2

    with pytest.raises(DuplicateHumanDecisionError):
        review_repository.resolve(
            tenant_id=tenant_id,
            task_id=task.id,
            actor_id=str(admin.id),
            roles=frozenset({Role.ADMIN}),
            expected_version=resolved.version,
            request=_decision(str(claimed.rule_results[0]["id"])),
        )

    assert review_repository.get(tenant_id=str(other_tenant), task_id=task.id) is None
    with pytest.raises(ReviewTaskNotFoundError):
        review_repository.claim(
            tenant_id=str(other_tenant),
            task_id=task.id,
            actor_id=str(admin.id),
            roles=frozenset({Role.ADMIN}),
            expected_version=3,
        )

    final = review_repository.get(tenant_id=tenant_id, task_id=task.id)
    assert final is not None and final.packet.packet_hash == initial_hash
    with factory() as session:
        counts = (
            session.scalar(
                select(func.count(HumanReviewTaskModel.id)).where(
                    HumanReviewTaskModel.id == UUID(task.id)
                )
            ),
            session.scalar(
                select(func.count(HumanReviewPacketModel.id)).where(
                    HumanReviewPacketModel.review_task_id == UUID(task.id)
                )
            ),
            session.scalar(
                select(func.count(HumanReviewActionModel.id)).where(
                    HumanReviewActionModel.review_task_id == UUID(task.id),
                    HumanReviewActionModel.action_type == "CREATED",
                )
            ),
            session.scalar(
                select(func.count(HumanReviewActionModel.id)).where(
                    HumanReviewActionModel.review_task_id == UUID(task.id),
                    HumanReviewActionModel.action_type == "CLAIMED",
                )
            ),
            session.scalar(
                select(func.count(HumanReviewDecisionModel.id)).where(
                    HumanReviewDecisionModel.review_task_id == UUID(task.id)
                )
            ),
            session.scalar(
                select(func.count(HumanReviewRequestEventModel.id)).where(
                    HumanReviewRequestEventModel.policy_evaluation_run_id == UUID(policy_run.id)
                )
            ),
            session.scalar(
                select(HumanReviewRequestEventModel.status).where(
                    HumanReviewRequestEventModel.id == review_event.id
                )
            ),
        )
    assert counts == (1, 1, 1, 1, 1, 1, "CONSUMED")


def test_release_evidence_resume_escalation_and_assignment_history(
    human_review_database: HumanReviewIntegrationContext,
) -> None:
    factory = human_review_database.factory
    with factory() as session:
        source = session.execute(
            select(
                AnalysisRunModel.tenant_id,
                AnalysisRunModel.case_id,
                AnalysisRunModel.id,
                AnalysisRunModel.requested_by,
            )
            .join(
                LLMExtractionResultV2Model,
                LLMExtractionResultV2Model.analysis_run_id == AnalysisRunModel.id,
            )
            .join(TenantModel, TenantModel.id == AnalysisRunModel.tenant_id)
            .where(
                AnalysisRunModel.status == "SUCCEEDED",
                TenantModel.slug == "csight-demo-brand",
            )
            .order_by(AnalysisRunModel.created_at.desc())
            .limit(1)
        ).one_or_none()
        admin = session.scalar(
            select(UserModel)
            .join(
                UserRoleModel,
                (UserRoleModel.tenant_id == UserModel.tenant_id)
                & (UserRoleModel.user_id == UserModel.id),
            )
            .join(RoleModel, RoleModel.id == UserRoleModel.role_id)
            .join(TenantModel, TenantModel.id == UserModel.tenant_id)
            .where(RoleModel.name == "ADMIN", TenantModel.slug == "csight-demo-brand")
            .limit(1)
        )
    if source is None or admin is None:
        pytest.skip("seeded analysis and admin are required")
    tenant_id, case_id, analysis_id, requested_by = map(str, source)
    policy_repository = SQLAlchemyPolicyEngineRepository(factory)
    policy_run, _ = policy_repository.create(
        tenant_id=tenant_id,
        case_id=case_id,
        analysis_run_id=analysis_id,
        as_of_date=date(2026, 2, 1),
        requested_by=requested_by,
        correlation_id=f"review-transitions-{uuid4()}",
        idempotency_key=f"review-transitions-{uuid4()}",
        request_hash="d" * 64,
    )
    with factory() as session:
        policy_event = session.scalar(
            select(PolicyEvaluationOutboxEventModel).where(
                PolicyEvaluationOutboxEventModel.policy_evaluation_run_id == UUID(policy_run.id)
            )
        )
    assert policy_event is not None
    policy_event = _mark_policy_event_published(factory, policy_event.id)
    assert (
        ExecutePolicyEvaluation(policy_repository).execute(
            ExecutePolicyEvaluationCommand(
                event_id=str(policy_event.id),
                tenant_id=tenant_id,
                case_id=case_id,
                policy_evaluation_run_id=policy_run.id,
                correlation_id=policy_run.correlation_id,
            )
        )
        == "SUCCEEDED"
    )
    repository = SQLAlchemyHumanReviewRepository(factory)
    with factory() as session:
        review_event = session.scalar(
            select(HumanReviewRequestEventModel).where(
                HumanReviewRequestEventModel.policy_evaluation_run_id == UUID(policy_run.id)
            )
        )
    assert review_event is not None
    review_event = _mark_review_event_published(factory, review_event.id)
    task, _ = repository.create_from_policy_evaluation(
        event_id=str(review_event.id),
        tenant_id=tenant_id,
        case_id=case_id,
        policy_evaluation_run_id=policy_run.id,
        correlation_id=policy_run.correlation_id,
    )
    with factory() as session:
        assert (
            session.scalar(
                select(HumanReviewRequestEventModel.status).where(
                    HumanReviewRequestEventModel.id == review_event.id
                )
            )
            == "CONSUMED"
        )
    actor = str(admin.id)
    claimed = repository.claim(
        tenant_id=tenant_id,
        task_id=task.id,
        actor_id=actor,
        roles=frozenset({Role.ADMIN}),
        expected_version=1,
    )
    released = repository.release(
        tenant_id=tenant_id,
        task_id=task.id,
        actor_id=actor,
        roles=frozenset({Role.ADMIN}),
        expected_version=claimed.version,
        reason_code="SHIFT_CHANGE",
        rationale=None,
    )
    claimed = repository.claim(
        tenant_id=tenant_id,
        task_id=task.id,
        actor_id=actor,
        roles=frozenset({Role.ADMIN}),
        expected_version=released.version,
    )
    waiting = repository.request_additional_evidence(
        tenant_id=tenant_id,
        task_id=task.id,
        actor_id=actor,
        roles=frozenset({Role.ADMIN}),
        expected_version=claimed.version,
        reason_codes=(AdditionalEvidenceReason.DEFECT_AREA_NOT_VISIBLE,),
        instructions="결함 부위가 보이도록 이미지를 다시 촬영해 주세요.",
        rationale=None,
    )
    assert waiting.status.value == "WAITING_FOR_EVIDENCE"
    assert waiting.current_assignee_id == actor
    resumed = repository.resume(
        tenant_id=tenant_id,
        task_id=task.id,
        actor_id=actor,
        roles=frozenset({Role.ADMIN}),
        expected_version=waiting.version,
        rationale="관리자가 추가 제출 경로를 확인하고 검토를 재개합니다.",
    )
    assert resumed.status.value == "CLAIMED"
    assert resumed.current_assignee_id == actor
    escalated = repository.escalate(
        tenant_id=tenant_id,
        task_id=task.id,
        actor_id=actor,
        roles=frozenset({Role.ADMIN}),
        expected_version=resumed.version,
        reason_codes=(EscalationReason.CONFLICTING_POLICY,),
        rationale="복수 정책 조건이 상충하여 관리자 재검토가 필요합니다.",
    )
    claimed = repository.claim(
        tenant_id=tenant_id,
        task_id=task.id,
        actor_id=actor,
        roles=frozenset({Role.ADMIN}),
        expected_version=escalated.version,
    )
    detail = repository.get(tenant_id=tenant_id, task_id=task.id)
    assert detail is not None
    resolved, _ = repository.resolve(
        tenant_id=tenant_id,
        task_id=task.id,
        actor_id=actor,
        roles=frozenset({Role.ADMIN}),
        expected_version=claimed.version,
        request=_decision(str(detail.rule_results[0]["id"])),
    )
    assert resolved.version == 9 and resolved.status.value == "RESOLVED"
    final = repository.get(tenant_id=tenant_id, task_id=task.id)
    assert final is not None
    assert [item.action_type.value for item in final.actions] == [
        "CREATED",
        "CLAIMED",
        "RELEASED",
        "CLAIMED",
        "EVIDENCE_REQUESTED",
        "RESUMED",
        "ESCALATED",
        "CLAIMED",
        "RESOLVED",
    ]
    with factory() as session:
        assignments = session.scalars(
            select(HumanReviewAssignmentModel).where(
                HumanReviewAssignmentModel.review_task_id == UUID(task.id)
            )
        ).all()
    assert len(assignments) == 3
    assert all(item.released_at is not None for item in assignments)


def test_policy_worker_integrity_failure_and_stale_terminal_fencing(
    human_review_database: HumanReviewIntegrationContext,
) -> None:
    factory = human_review_database.factory
    with factory() as session:
        source = session.execute(
            select(
                AnalysisRunModel.tenant_id,
                AnalysisRunModel.case_id,
                AnalysisRunModel.id,
                AnalysisRunModel.requested_by,
            )
            .join(
                LLMExtractionResultV2Model,
                LLMExtractionResultV2Model.analysis_run_id == AnalysisRunModel.id,
            )
            .join(TenantModel, TenantModel.id == AnalysisRunModel.tenant_id)
            .where(
                AnalysisRunModel.status == "SUCCEEDED",
                TenantModel.slug == "csight-demo-brand",
            )
            .order_by(AnalysisRunModel.created_at.desc())
            .limit(1)
        ).one_or_none()
    if source is None:
        pytest.skip("seeded analysis is required")
    tenant_id, case_id, analysis_id, requested_by = map(str, source)
    repository = SQLAlchemyPolicyEngineRepository(factory)

    def create_run(label: str) -> tuple[PolicyEvaluationRun, PolicyEvaluationOutboxEventModel]:
        run, _ = repository.create(
            tenant_id=tenant_id,
            case_id=case_id,
            analysis_run_id=analysis_id,
            as_of_date=date(2026, 2, 1),
            requested_by=requested_by,
            correlation_id=f"{label}-{uuid4()}",
            idempotency_key=f"{label}-{uuid4()}",
            request_hash="e" * 64,
        )
        with factory() as session:
            event = session.scalar(
                select(PolicyEvaluationOutboxEventModel).where(
                    PolicyEvaluationOutboxEventModel.policy_evaluation_run_id == UUID(run.id)
                )
            )
        assert event is not None
        return run, _mark_policy_event_published(factory, event.id)

    mismatched_run, mismatched_event = create_run("mismatch")
    with pytest.raises(AsyncEventIntegrityError) as mismatch:
        repository.claim(
            event_id=str(mismatched_event.id),
            tenant_id=tenant_id,
            case_id=str(uuid4()),
            run_id=mismatched_run.id,
            correlation_id=mismatched_run.correlation_id,
        )
    assert mismatch.value.code == "ASYNC_EVENT_PAYLOAD_MISMATCH"
    with factory() as session:
        persisted_run = session.get(PolicyEvaluationRunModel, UUID(mismatched_run.id))
        persisted_event = session.get(PolicyEvaluationOutboxEventModel, mismatched_event.id)
        assert persisted_run is not None and persisted_run.status == "FAILED"
        assert persisted_event is not None and persisted_event.status == "FAILED"
        assert persisted_event.failure_code == "ASYNC_EVENT_PAYLOAD_MISMATCH"

    leased_run, leased_event = create_run("leased")
    execution = repository.claim(
        event_id=str(leased_event.id),
        tenant_id=tenant_id,
        case_id=case_id,
        run_id=leased_run.id,
        correlation_id=leased_run.correlation_id,
    )
    assert execution is not None
    repository.record_consumer_failure(
        event_id=str(leased_event.id),
        code="POLICY_EVALUATION_WORKER_RETRIES_EXHAUSTED",
        message="A stale delivery exhausted retries.",
    )
    with factory() as session:
        persisted_run = session.get(PolicyEvaluationRunModel, UUID(leased_run.id))
        persisted_event = session.get(PolicyEvaluationOutboxEventModel, leased_event.id)
        assert persisted_run is not None and persisted_run.status == "RUNNING"
        assert persisted_run.claim_token == UUID(execution.claim_token)
        assert persisted_event is not None and persisted_event.status == "PUBLISHED"
        assert persisted_event.consumer_last_error is not None
        assert "newer execution lease" in persisted_event.consumer_last_error

    poison_run, poison_event = create_run("poison")
    repository.record_consumer_failure(
        event_id=str(poison_event.id),
        code="POLICY_EVALUATION_QUEUE_PAYLOAD_INVALID",
        message="Policy evaluation queue payload failed UUID validation.",
    )
    with factory() as session:
        persisted_run = session.get(PolicyEvaluationRunModel, UUID(poison_run.id))
        persisted_event = session.get(PolicyEvaluationOutboxEventModel, poison_event.id)
        assert persisted_run is not None and persisted_run.status == "FAILED"
        assert persisted_event is not None and persisted_event.status == "FAILED"
        assert persisted_event.failure_code == "POLICY_EVALUATION_QUEUE_PAYLOAD_INVALID"

    human_mismatch_run, human_mismatch_policy_event = create_run("human-mismatch")
    assert (
        ExecutePolicyEvaluation(repository).execute(
            ExecutePolicyEvaluationCommand(
                event_id=str(human_mismatch_policy_event.id),
                tenant_id=tenant_id,
                case_id=case_id,
                policy_evaluation_run_id=human_mismatch_run.id,
                correlation_id=human_mismatch_run.correlation_id,
            )
        )
        == "SUCCEEDED"
    )
    with factory() as session:
        human_event = session.scalar(
            select(HumanReviewRequestEventModel).where(
                HumanReviewRequestEventModel.policy_evaluation_run_id == UUID(human_mismatch_run.id)
            )
        )
    assert human_event is not None
    human_event = _mark_review_event_published(factory, human_event.id)
    review_repository = SQLAlchemyHumanReviewRepository(factory)
    with pytest.raises(AsyncEventIntegrityError) as human_mismatch:
        review_repository.create_from_policy_evaluation(
            event_id=str(human_event.id),
            tenant_id=tenant_id,
            case_id=str(uuid4()),
            policy_evaluation_run_id=human_mismatch_run.id,
            correlation_id=human_mismatch_run.correlation_id,
        )
    assert human_mismatch.value.code == "ASYNC_EVENT_PAYLOAD_MISMATCH"
    with factory() as session:
        persisted_event = session.get(HumanReviewRequestEventModel, human_event.id)
        task_count = session.scalar(
            select(func.count(HumanReviewTaskModel.id)).where(
                HumanReviewTaskModel.policy_evaluation_run_id == UUID(human_mismatch_run.id)
            )
        )
        assert persisted_event is not None and persisted_event.status == "FAILED"
        assert persisted_event.failure_code == "ASYNC_EVENT_PAYLOAD_MISMATCH"
        assert task_count == 0

    snapshot_run, snapshot_policy_event = create_run("snapshot-tamper")
    assert (
        ExecutePolicyEvaluation(repository).execute(
            ExecutePolicyEvaluationCommand(
                event_id=str(snapshot_policy_event.id),
                tenant_id=tenant_id,
                case_id=case_id,
                policy_evaluation_run_id=snapshot_run.id,
                correlation_id=snapshot_run.correlation_id,
            )
        )
        == "SUCCEEDED"
    )
    with factory.begin() as session:
        snapshot = session.scalar(
            select(PolicyEvaluationInputSnapshotModel).where(
                PolicyEvaluationInputSnapshotModel.policy_evaluation_run_id == UUID(snapshot_run.id)
            )
        )
        human_event = session.scalar(
            select(HumanReviewRequestEventModel).where(
                HumanReviewRequestEventModel.policy_evaluation_run_id == UUID(snapshot_run.id)
            )
        )
        assert snapshot is not None and human_event is not None
        snapshot.input_values = {**snapshot.input_values, "tampered": True}
        human_event_id = human_event.id
    human_event = _mark_review_event_published(factory, human_event_id)
    with pytest.raises(ReviewPacketIntegrityError):
        review_repository.create_from_policy_evaluation(
            event_id=str(human_event.id),
            tenant_id=tenant_id,
            case_id=case_id,
            policy_evaluation_run_id=snapshot_run.id,
            correlation_id=snapshot_run.correlation_id,
        )
    with factory() as session:
        persisted_event = session.get(HumanReviewRequestEventModel, human_event.id)
        task_count = session.scalar(
            select(func.count(HumanReviewTaskModel.id)).where(
                HumanReviewTaskModel.policy_evaluation_run_id == UUID(snapshot_run.id)
            )
        )
        assert persisted_event is not None and persisted_event.status == "FAILED"
        assert persisted_event.failure_code == "HUMAN_REVIEW_SOURCE_INTEGRITY_FAILED"
        assert task_count == 0


@dataclass(frozen=True, slots=True)
class _ResolutionSource:
    tenant_id: str
    case_id: str
    analysis_id: str
    actor_id: str


@dataclass(frozen=True, slots=True)
class _ResolvedDecision:
    resolution_id: UUID
    decision_id: str
    request_event_id: UUID
    correlation_id: str


def _create_resolution_source(
    factory: sessionmaker[Session],
    *,
    label: str,
    external_action_input: dict[str, object],
) -> _ResolutionSource:
    now = datetime.now(UTC)
    customer_message = "합성 테스트: 제품 파손으로 환불 검토를 요청합니다."
    with factory.begin() as session:
        tenant_id = session.scalar(
            select(TenantModel.id).where(TenantModel.slug == "csight-demo-brand")
        )
        admin = session.scalar(
            select(UserModel)
            .join(
                UserRoleModel,
                (UserRoleModel.tenant_id == UserModel.tenant_id)
                & (UserRoleModel.user_id == UserModel.id),
            )
            .join(RoleModel, RoleModel.id == UserRoleModel.role_id)
            .where(
                UserModel.tenant_id == tenant_id,
                RoleModel.name == Role.ADMIN.value,
            )
            .limit(1)
        )
        assert tenant_id is not None and admin is not None
        case_id, analysis_id, stage_id = uuid4(), uuid4(), uuid4()
        session.add(
            CaseModel(
                id=case_id,
                tenant_id=tenant_id,
                domain_type="product_defect_cs",
                status="RECEIVED",
                order_ref=f"RESOLUTION-{label}-ORDER",
                product_ref=f"RESOLUTION-{label}-PRODUCT",
                customer_message=customer_message,
                requested_action="REFUND",
                attributes={
                    "days_since_purchase": 3,
                    "order_amount": 500_000,
                    "product_category": "GENERAL",
                    "external_action_input": external_action_input,
                },
                created_by=admin.id,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            CaseSensitivePayloadModel(
                id=uuid4(),
                tenant_id=tenant_id,
                case_id=case_id,
                schema_version="case_sensitive_payload/1.0.0",
                customer_message=customer_message,
                payload_sha256=hashlib.sha256(customer_message.encode("utf-8")).hexdigest(),
                retention_policy_version="integration/30d",
                expires_at=now + timedelta(days=30),
                purged_at=None,
                legacy_redacted_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            AnalysisRunModel(
                id=analysis_id,
                tenant_id=tenant_id,
                case_id=case_id,
                pipeline_name="product_defect_text_extraction",
                pipeline_version="2.0.0",
                trigger_type="USER_REQUEST",
                status="SUCCEEDED",
                requested_by=admin.id,
                correlation_id=f"resolution-{label}-{uuid4()}",
                idempotency_key=f"resolution-{label}-{uuid4()}",
                request_hash="c" * 64,
                requested_at=now,
                started_at=now,
                completed_at=now,
                failure_code=None,
                failure_message=None,
                failure_retryable=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            AnalysisStageRunModel(
                id=stage_id,
                tenant_id=tenant_id,
                analysis_run_id=analysis_id,
                stage_type="TEXT_EXTRACTION",
                status="SUCCEEDED",
                attempt_count=1,
                provider_name="mock",
                model_name="csight-mock-llm",
                model_version="0.1.0",
                model_revision="integration",
                prompt_name="product-defect-text-extraction",
                prompt_version="2.0.0",
                prompt_content_hash="b" * 64,
                input_schema_version="2.0",
                output_schema_version="2.0",
                execution_provider_name="mock",
                execution_model_name="csight-mock-llm",
                execution_model_version="0.1.0",
                execution_model_revision="integration",
                provider_request_id=f"resolution-{label}",
                input_token_count=1,
                output_token_count=1,
                latency_ms=1,
                claim_token=None,
                lease_expires_at=None,
                next_attempt_at=None,
                last_attempt_started_at=now,
                last_attempt_completed_at=now,
                started_at=now,
                completed_at=now,
                failure_code=None,
                failure_message=None,
                failure_retryable=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            LLMExtractionResultV2Model(
                id=uuid4(),
                tenant_id=tenant_id,
                analysis_run_id=analysis_id,
                stage_run_id=stage_id,
                stage_type="TEXT_EXTRACTION",
                schema_version="2.0",
                language="ko",
                issue_types=["BREAKAGE"],
                claims=[
                    {
                        "type": "BREAKAGE",
                        "location": "UNKNOWN",
                        "description": "제품이 파손됨",
                        "source_quote": "제품 파손으로",
                    }
                ],
                requested_actions=[{"action": "REFUND", "source_quote": "환불 검토를 요청합니다"}],
                text_ambiguities=[],
                summary="제품 파손에 대한 환불 요청",
                system_missing_information=["IMAGE_EVIDENCE"],
                action_consistency="MATCH",
                completeness_rule_version="1.0.0",
                created_at=now,
            )
        )
    return _ResolutionSource(
        tenant_id=str(tenant_id),
        case_id=str(case_id),
        analysis_id=str(analysis_id),
        actor_id=str(admin.id),
    )


def _create_resolved_decision(
    factory: sessionmaker[Session],
    *,
    source: _ResolutionSource,
    decision_type: HumanDecisionType,
    label: str,
) -> _ResolvedDecision:
    policy_repository = SQLAlchemyPolicyEngineRepository(factory)
    policy_run, _ = policy_repository.create(
        tenant_id=source.tenant_id,
        case_id=source.case_id,
        analysis_run_id=source.analysis_id,
        as_of_date=date(2026, 2, 1),
        requested_by=source.actor_id,
        correlation_id=f"resolution-policy-{label}-{uuid4()}",
        idempotency_key=f"resolution-policy-{label}-{uuid4()}",
        request_hash="d" * 64,
    )
    with factory() as session:
        policy_event = session.scalar(
            select(PolicyEvaluationOutboxEventModel).where(
                PolicyEvaluationOutboxEventModel.policy_evaluation_run_id == UUID(policy_run.id)
            )
        )
    assert policy_event is not None
    policy_event = _mark_policy_event_published(factory, policy_event.id)
    assert (
        ExecutePolicyEvaluation(policy_repository).execute(
            ExecutePolicyEvaluationCommand(
                event_id=str(policy_event.id),
                tenant_id=source.tenant_id,
                case_id=source.case_id,
                policy_evaluation_run_id=policy_run.id,
                correlation_id=policy_run.correlation_id,
            )
        )
        == "SUCCEEDED"
    )

    review_repository = SQLAlchemyHumanReviewRepository(factory)
    with factory() as session:
        review_event = session.scalar(
            select(HumanReviewRequestEventModel).where(
                HumanReviewRequestEventModel.policy_evaluation_run_id == UUID(policy_run.id)
            )
        )
    assert review_event is not None
    review_event = _mark_review_event_published(factory, review_event.id)
    task, _ = review_repository.create_from_policy_evaluation(
        event_id=str(review_event.id),
        tenant_id=source.tenant_id,
        case_id=source.case_id,
        policy_evaluation_run_id=policy_run.id,
        correlation_id=policy_run.correlation_id,
    )
    claimed = review_repository.claim(
        tenant_id=source.tenant_id,
        task_id=task.id,
        actor_id=source.actor_id,
        roles=frozenset({Role.ADMIN}),
        expected_version=1,
    )
    detail = review_repository.get(tenant_id=source.tenant_id, task_id=task.id)
    assert detail is not None
    correlation_id = f"resolution-resolve-{label}-{uuid4()}"
    _, decision = review_repository.resolve(
        tenant_id=source.tenant_id,
        task_id=task.id,
        actor_id=source.actor_id,
        roles=frozenset({Role.ADMIN}),
        expected_version=claimed.version,
        correlation_id=correlation_id,
        request=HumanDecisionRequest(
            decision=decision_type,
            reason_codes=(DecisionReason.POLICY_CONDITION_MET,),
            rationale="정책 평가와 동결된 근거를 검토하여 이 처리 결정을 기록합니다.",
            basis=(
                DecisionBasisReference(
                    type=DecisionBasisType.POLICY_RULE_RESULT,
                    reference_id=str(detail.rule_results[0]["id"]),
                ),
            ),
        ),
    )
    with factory() as session:
        resolution = session.scalar(
            select(CaseResolutionModel).where(
                CaseResolutionModel.tenant_id == UUID(source.tenant_id),
                CaseResolutionModel.case_id == UUID(source.case_id),
            )
        )
        request_event = session.scalar(
            select(CaseResolutionRequestEventModel).where(
                CaseResolutionRequestEventModel.tenant_id == UUID(source.tenant_id),
                CaseResolutionRequestEventModel.human_decision_id == UUID(decision.id),
            )
        )
    assert resolution is not None and request_event is not None
    return _ResolvedDecision(
        resolution_id=resolution.id,
        decision_id=decision.id,
        request_event_id=request_event.id,
        correlation_id=correlation_id,
    )


def _process_resolution_request(
    factory: sessionmaker[Session],
    *,
    source: _ResolutionSource,
    resolved: _ResolvedDecision,
) -> str:
    event = _mark_resolution_event_published(factory, resolved.request_event_id)
    return ProcessCaseResolution(SQLAlchemyCaseResolutionRepository(factory)).execute(
        CaseResolutionRequestedCommand(
            event_id=str(event.id),
            tenant_id=source.tenant_id,
            case_id=source.case_id,
            resolution_id=str(resolved.resolution_id),
            correlation_id=event.correlation_id,
        )
    )


def test_resolution_missing_input_and_conflicting_decision_fail_closed_without_duplicates(
    human_review_database: HumanReviewIntegrationContext,
) -> None:
    factory = human_review_database.factory
    missing_source = _create_resolution_source(
        factory,
        label="missing-input",
        external_action_input={"currency": "KRW"},
    )
    missing_decision = _create_resolved_decision(
        factory,
        source=missing_source,
        decision_type=HumanDecisionType.APPROVE_REFUND,
        label="missing-input",
    )
    assert (
        _process_resolution_request(
            factory,
            source=missing_source,
            resolved=missing_decision,
        )
        == "ACTION_NEEDS_INPUT"
    )
    with factory() as session:
        missing_resolution = session.get(CaseResolutionModel, missing_decision.resolution_id)
        intent_count = session.scalar(
            select(func.count(ExternalActionIntentModel.id)).where(
                ExternalActionIntentModel.resolution_id == missing_decision.resolution_id
            )
        )
        command_count = session.scalar(
            select(func.count(ExternalActionSimulationRequestEventModel.id)).where(
                ExternalActionSimulationRequestEventModel.case_id == UUID(missing_source.case_id)
            )
        )
        attempt_count = session.scalar(
            select(func.count(ExternalActionSimulationAttemptModel.id)).where(
                ExternalActionSimulationAttemptModel.resolution_id == missing_decision.resolution_id
            )
        )
        result_count = session.scalar(
            select(func.count(ExternalActionSimulationResultModel.id)).where(
                ExternalActionSimulationResultModel.resolution_id == missing_decision.resolution_id
            )
        )
    assert missing_resolution is not None
    assert missing_resolution.status == "ACTION_NEEDS_INPUT"
    assert missing_resolution.missing_fields == ["amount"]
    assert (intent_count, command_count, attempt_count, result_count) == (0, 0, 0, 0)

    conflict_source = _create_resolution_source(
        factory,
        label="conflict",
        external_action_input={"amount": "15000.0000", "currency": "KRW"},
    )
    original = _create_resolved_decision(
        factory,
        source=conflict_source,
        decision_type=HumanDecisionType.APPROVE_REFUND,
        label="conflict-original",
    )
    assert (
        _process_resolution_request(factory, source=conflict_source, resolved=original)
        == "ACTION_READY"
    )
    conflicting = _create_resolved_decision(
        factory,
        source=conflict_source,
        decision_type=HumanDecisionType.APPROVE_REPAIR,
        label="conflict-second",
    )
    assert (
        _process_resolution_request(
            factory,
            source=conflict_source,
            resolved=conflicting,
        )
        == "MANUAL_FOLLOW_UP_REQUIRED"
    )
    with factory() as session:
        conflict_resolution = session.get(CaseResolutionModel, original.resolution_id)
        intents = session.scalars(
            select(ExternalActionIntentModel).where(
                ExternalActionIntentModel.resolution_id == original.resolution_id
            )
        ).all()
        attempts = session.scalars(
            select(ExternalActionSimulationAttemptModel).where(
                ExternalActionSimulationAttemptModel.resolution_id == original.resolution_id
            )
        ).all()
        results = session.scalars(
            select(ExternalActionSimulationResultModel).where(
                ExternalActionSimulationResultModel.resolution_id == original.resolution_id
            )
        ).all()
    assert conflict_resolution is not None
    assert conflict_resolution.status == "MANUAL_FOLLOW_UP_REQUIRED"
    assert str(conflict_resolution.source_human_decision_id) == original.decision_id
    assert [str(item.human_decision_id) for item in intents] == [original.decision_id]
    assert attempts == [] and results == []


def test_case_reassignment_updates_open_review_owner_and_rls(
    human_review_database: HumanReviewIntegrationContext,
) -> None:
    """A reassignment atomically moves the Case, review task, audit, and DB visibility."""

    factory = human_review_database.factory
    source = _create_resolution_source(
        factory,
        label=f"assignment-{uuid4().hex[:8]}",
        external_action_input={"amount": "15000.0000", "currency": "KRW"},
    )
    policy_repository = SQLAlchemyPolicyEngineRepository(factory)
    policy_run, _ = policy_repository.create(
        tenant_id=source.tenant_id,
        case_id=source.case_id,
        analysis_run_id=source.analysis_id,
        as_of_date=date(2026, 2, 1),
        requested_by=source.actor_id,
        correlation_id=f"assignment-policy-{uuid4()}",
        idempotency_key=f"assignment-policy-{uuid4()}",
        request_hash="e" * 64,
    )
    with factory() as session:
        policy_event = session.scalar(
            select(PolicyEvaluationOutboxEventModel).where(
                PolicyEvaluationOutboxEventModel.policy_evaluation_run_id == UUID(policy_run.id)
            )
        )
    assert policy_event is not None
    policy_event = _mark_policy_event_published(factory, policy_event.id)
    assert (
        ExecutePolicyEvaluation(policy_repository).execute(
            ExecutePolicyEvaluationCommand(
                event_id=str(policy_event.id),
                tenant_id=source.tenant_id,
                case_id=source.case_id,
                policy_evaluation_run_id=policy_run.id,
                correlation_id=policy_run.correlation_id,
            )
        )
        == "SUCCEEDED"
    )
    review_repository = SQLAlchemyHumanReviewRepository(factory)
    with factory() as session:
        review_event = session.scalar(
            select(HumanReviewRequestEventModel).where(
                HumanReviewRequestEventModel.policy_evaluation_run_id == UUID(policy_run.id)
            )
        )
    assert review_event is not None
    review_event = _mark_review_event_processing(factory, review_event.id)
    task, replayed = review_repository.create_from_policy_evaluation(
        event_id=str(review_event.id),
        tenant_id=source.tenant_id,
        case_id=source.case_id,
        policy_evaluation_run_id=policy_run.id,
        correlation_id=policy_run.correlation_id,
    )
    assert replayed is False and task.status.value == "PENDING"

    reviewer_role_id = uuid4()
    reviewer_id = uuid4()
    with factory.begin() as session:
        session.add(RoleModel(id=reviewer_role_id, name=Role.REVIEWER.value))
        session.add(
            UserModel(
                id=reviewer_id,
                tenant_id=UUID(source.tenant_id),
                email=f"reviewer-{reviewer_id.hex}@integration.test",
                password_hash="integration-test-password-hash",
                display_name="Assignment Reviewer",
            )
        )
        session.flush()
        session.add(
            UserRoleModel(
                tenant_id=UUID(source.tenant_id),
                user_id=reviewer_id,
                role_id=reviewer_role_id,
            )
        )

    assignments = SQLAlchemyCaseAssignmentRepository(factory)
    first = assignments.assign(
        tenant_id=source.tenant_id,
        case_id=source.case_id,
        assignee_id=source.actor_id,
        assigned_by=source.actor_id,
        expected_version=0,
        rationale="관리자가 최초 담당자를 배정합니다",
    )
    second = assignments.assign(
        tenant_id=source.tenant_id,
        case_id=source.case_id,
        assignee_id=str(reviewer_id),
        assigned_by=source.actor_id,
        expected_version=first.version,
        rationale="업무 분배를 위해 담당자를 변경합니다",
    )
    assert second.version == 2 and second.current_assignee_id == str(reviewer_id)
    assert assignments.can_access(
        tenant_id=source.tenant_id,
        case_id=source.case_id,
        actor_id=str(reviewer_id),
    )
    assert not assignments.can_access(
        tenant_id=source.tenant_id,
        case_id=source.case_id,
        actor_id=source.actor_id,
    )
    with pytest.raises(CaseAssignmentVersionConflictError):
        assignments.assign(
            tenant_id=source.tenant_id,
            case_id=source.case_id,
            assignee_id=source.actor_id,
            assigned_by=source.actor_id,
            expected_version=0,
            rationale="오래된 화면에서 잘못 재배정합니다",
        )

    with factory() as session:
        persisted_task = session.get(HumanReviewTaskModel, UUID(task.id))
        active_case_assignments = session.scalar(
            select(func.count(CaseAssignmentModel.id)).where(
                CaseAssignmentModel.case_id == UUID(source.case_id),
                CaseAssignmentModel.released_at.is_(None),
            )
        )
        action_count = session.scalar(
            select(func.count(CaseAssignmentActionModel.id)).where(
                CaseAssignmentActionModel.case_id == UUID(source.case_id)
            )
        )
    assert persisted_task is not None
    assert persisted_task.status == "CLAIMED"
    assert persisted_task.current_assignee_id == reviewer_id
    assert persisted_task.version == 3
    assert (active_case_assignments, action_count) == (1, 2)

    with pytest.raises(SQLAlchemyError), factory.begin() as session:
        session.execute(
            update(CaseAssignmentActionModel)
            .where(CaseAssignmentActionModel.case_id == UUID(source.case_id))
            .values(rationale="감사 기록 변경 시도")
        )

    engine = factory.kw["bind"]
    assert isinstance(engine, Engine)
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE csight_api_role"))
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": source.tenant_id},
        )
        connection.execute(
            text("SELECT set_config('app.actor_id', :actor_id, true)"),
            {"actor_id": source.actor_id},
        )
        connection.execute(text("SELECT set_config('app.case_access_all', 'false', true)"))
        assert (
            connection.scalar(
                text("SELECT count(*) FROM cases WHERE id = :case_id"),
                {"case_id": source.case_id},
            )
            == 0
        )
        connection.execute(
            text("SELECT set_config('app.actor_id', :actor_id, true)"),
            {"actor_id": str(reviewer_id)},
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM cases WHERE id = :case_id"),
                {"case_id": source.case_id},
            )
            == 1
        )
        connection.execute(text("SELECT set_config('app.case_access_all', 'true', true)"))
        assert (
            connection.scalar(
                text("SELECT count(*) FROM cases WHERE id = :case_id"),
                {"case_id": source.case_id},
            )
            == 1
        )


def test_terminal_privacy_purge_redacts_human_text_reports_and_communications(
    human_review_database: HumanReviewIntegrationContext,
) -> None:
    engine = human_review_database.engine
    factory = human_review_database.factory
    with factory() as session:
        source = session.execute(
            select(
                ReviewReportModel.tenant_id,
                ReviewReportModel.case_id,
                CaseModel.created_by,
            )
            .join(
                CaseModel,
                (CaseModel.tenant_id == ReviewReportModel.tenant_id)
                & (CaseModel.id == ReviewReportModel.case_id),
            )
            .where(ReviewReportModel.case_snapshot.op("?")("synthetic_commerce_context"))
            .order_by(ReviewReportModel.generated_at)
            .limit(1)
        ).one_or_none()
    assert source is not None
    tenant_id, case_id, admin_id = source

    reporting = SQLAlchemyPocReportingRepository(factory)
    communication = reporting.create_customer_communication(
        tenant_id=str(tenant_id),
        case_id=str(case_id),
        created_by=str(admin_id),
    )
    assert communication.side_effects_performed is False

    with factory.begin() as session:
        payload = session.scalar(
            select(CaseSensitivePayloadModel)
            .where(
                CaseSensitivePayloadModel.tenant_id == tenant_id,
                CaseSensitivePayloadModel.case_id == case_id,
            )
            .with_for_update()
        )
        assert payload is not None
        now = max(datetime.now(UTC), payload.created_at + timedelta(seconds=2))
        payload.expires_at = now - timedelta(seconds=1)

    class Clock:
        def now(self) -> datetime:
            return now

    class IDs:
        def new_id(self) -> str:
            return str(uuid4())

    purge = PurgeExpiredSensitivePayloads(
        uow_factory=create_privacy_lifecycle_unit_of_work_factory(engine),
        clock=Clock(),
        id_generator=IDs(),
    ).execute(
        principal=Principal(
            user_id=str(admin_id),
            tenant_id=str(tenant_id),
            email="terminal-privacy-admin@example.test",
            display_name="Terminal Privacy Admin",
            roles=frozenset({Role.ADMIN}),
        ),
        execute=True,
    )
    assert purge.applied_count == 1 and purge.blocked_count == 0

    with factory() as session:
        payload = session.scalar(
            select(CaseSensitivePayloadModel).where(
                CaseSensitivePayloadModel.tenant_id == tenant_id,
                CaseSensitivePayloadModel.case_id == case_id,
            )
        )
        case = session.get(CaseModel, case_id)
        actions = tuple(
            session.scalars(
                select(HumanReviewActionModel)
                .join(
                    HumanReviewTaskModel,
                    (HumanReviewTaskModel.tenant_id == HumanReviewActionModel.tenant_id)
                    & (HumanReviewTaskModel.id == HumanReviewActionModel.review_task_id),
                )
                .where(
                    HumanReviewTaskModel.tenant_id == tenant_id,
                    HumanReviewTaskModel.case_id == case_id,
                )
            )
        )
        decisions = tuple(
            session.scalars(
                select(HumanReviewDecisionModel)
                .join(
                    HumanReviewTaskModel,
                    (HumanReviewTaskModel.tenant_id == HumanReviewDecisionModel.tenant_id)
                    & (HumanReviewTaskModel.id == HumanReviewDecisionModel.review_task_id),
                )
                .where(
                    HumanReviewTaskModel.tenant_id == tenant_id,
                    HumanReviewTaskModel.case_id == case_id,
                )
            )
        )
        reports = tuple(
            session.scalars(
                select(ReviewReportModel).where(
                    ReviewReportModel.tenant_id == tenant_id,
                    ReviewReportModel.case_id == case_id,
                )
            )
        )
        communications = tuple(
            session.scalars(
                select(CustomerCommunicationSimulationModel).where(
                    CustomerCommunicationSimulationModel.tenant_id == tenant_id,
                    CustomerCommunicationSimulationModel.case_id == case_id,
                )
            )
        )
        event = session.scalar(
            select(DataLifecycleEventModel).where(
                DataLifecycleEventModel.tenant_id == tenant_id,
                DataLifecycleEventModel.case_id == case_id,
                DataLifecycleEventModel.event_type == "SENSITIVE_PAYLOAD_PURGED",
            )
        )
        assert payload is not None and case is not None and event is not None
        assert payload.terminal_content_purged_at == payload.purged_at
        assert case.attributes == {}
        assert actions and all(item.action_payload == {} for item in actions)
        assert all(item.rationale in {None, "[PURGED_BY_RETENTION]"} for item in actions)
        assert decisions and all(item.rationale == "[PURGED_BY_RETENTION]" for item in decisions)
        assert reports and all(
            item.data_scope["privacy_redaction_policy_version"]
            == "terminal-content-redaction/1.0.0"
            for item in reports
        )
        assert all("synthetic_commerce_context" not in item.case_snapshot for item in reports)
        assert communications and all(
            item.recipient_label == item.subject == item.body == "[PURGED_BY_RETENTION]"
            for item in communications
        )
        assert event.details["terminal_content_redacted"] is True
        assert event.details["terminal_redaction_receipt_sha256"]

        marker_count = session.scalar(
            text(
                """
                SELECT count(*) FROM (
                    SELECT attributes::text AS value FROM cases
                     WHERE tenant_id = :tenant_id AND id = :case_id
                    UNION ALL SELECT action.rationale FROM human_review_actions AS action
                     JOIN human_review_tasks AS task ON task.tenant_id = action.tenant_id
                      AND task.id = action.review_task_id
                     WHERE task.tenant_id = :tenant_id AND task.case_id = :case_id
                    UNION ALL SELECT action.action_payload::text FROM human_review_actions AS action
                     JOIN human_review_tasks AS task ON task.tenant_id = action.tenant_id
                      AND task.id = action.review_task_id
                     WHERE task.tenant_id = :tenant_id AND task.case_id = :case_id
                    UNION ALL SELECT report.case_snapshot::text FROM review_reports AS report
                     WHERE tenant_id = :tenant_id AND case_id = :case_id
                    UNION ALL SELECT report.review_snapshot::text FROM review_reports AS report
                     WHERE tenant_id = :tenant_id AND case_id = :case_id
                    UNION ALL SELECT communication.body
                     FROM customer_communication_simulations AS communication
                     WHERE tenant_id = :tenant_id AND case_id = :case_id
                ) AS values_to_scan WHERE value LIKE :marker
                """
            ),
            {
                "tenant_id": tenant_id,
                "case_id": case_id,
                "marker": f"%{TERMINAL_PRIVACY_MARKER}%",
            },
        )
        assert marker_count == 0

    assert reporting.get_review_report(tenant_id=str(tenant_id), case_id=str(case_id)) is not None
    assert reporting.list_customer_communications(tenant_id=str(tenant_id), case_id=str(case_id))

    with engine.begin() as connection:
        transaction = connection.begin_nested()
        try:
            with pytest.raises(DBAPIError, match="customer-derived terminal content remains"):
                connection.execute(
                    update(CaseModel)
                    .where(CaseModel.tenant_id == tenant_id, CaseModel.id == case_id)
                    .values(attributes={"restored": TERMINAL_PRIVACY_MARKER})
                )
                connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        finally:
            if transaction.is_active:
                transaction.rollback()


def _decision(rule_result_id: str) -> HumanDecisionRequest:
    return HumanDecisionRequest(
        decision=HumanDecisionType.APPROVE_REFUND,
        reason_codes=(DecisionReason.POLICY_CONDITION_MET,),
        rationale="정책 평가 결과와 동결된 검토 근거를 확인하여 환불을 승인합니다.",
        basis=(
            DecisionBasisReference(
                type=DecisionBasisType.POLICY_RULE_RESULT,
                reference_id=rule_result_id,
            ),
        ),
    )
