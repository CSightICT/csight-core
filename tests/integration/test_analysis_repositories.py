"""Opt-in PostgreSQL tests for Sprint 2 Analysis persistence and fencing."""

import os
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command as alembic_command
from app.adapters.persistence.engine import clear_engine_cache, get_engine
from app.adapters.persistence.models import (
    AnalysisRequestIdempotencyRecordModel,
    AnalysisRunModel,
    AnalysisStageAttemptModel,
    AnalysisStageRunModel,
    CaseModel,
    CaseSensitivePayloadModel,
    DataLifecycleEventModel,
    LLMExtractionResultModel,
    OperationalFailureModel,
    OutboxEventModel,
    TenantModel,
    UserModel,
)
from app.adapters.persistence.unit_of_work import (
    SQLAlchemyAnalysisUnitOfWorkFactory,
    create_analysis_unit_of_work_factory,
)
from app.bootstrap.settings import Settings
from app.platform.analysis.enums import (
    AnalysisAttemptStatus,
    AnalysisPipeline,
    AnalysisRunStatus,
    AnalysisStageStatus,
    AnalysisStageType,
    AnalysisTrigger,
    DefectLocation,
    ExtractedRequestedAction,
    ExtractionIssueType,
    MissingInformation,
    OutboxStatus,
)
from app.platform.analysis.models import (
    AnalysisFailure,
    AnalysisRequestIdempotencyRecord,
    AnalysisRun,
    AnalysisStageAttempt,
    AnalysisStageRun,
    OutboxEvent,
    ProviderExecutionMetadata,
)
from app.platform.analysis.schemas import (
    LLMExtractionResultRecord,
    LLMTextClaim,
    LLMTextExtractionResult,
)
from app.platform.case import Case, RequestedAction

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 26, 3, 4, 5, tzinfo=UTC)
HASH = "a" * 64


@pytest.fixture(scope="module")
def analysis_engine() -> Generator[Engine, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test Analysis repositories")

    settings = Settings()
    database_url = settings.database_url_value
    if not database_url:
        pytest.fail("DATABASE_URL is required for Analysis repository integration tests")

    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    alembic_command.upgrade(config, "head")

    engine = get_engine(settings)
    try:
        yield engine
    finally:
        clear_engine_cache()


@dataclass(frozen=True, slots=True)
class AnalysisRepositoryContext:
    engine: Engine
    factory: SQLAlchemyAnalysisUnitOfWorkFactory
    tenant_a: str
    tenant_b: str
    user_a: str
    user_b: str


@pytest.fixture
def analysis_context(
    analysis_engine: Engine,
) -> Generator[AnalysisRepositoryContext, None, None]:
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    user_a = str(uuid4())
    user_b = str(uuid4())
    with Session(analysis_engine) as session:
        session.add_all(
            [
                TenantModel(id=UUID(tenant_a), slug=f"tenant-{tenant_a}", name="Tenant A"),
                TenantModel(id=UUID(tenant_b), slug=f"tenant-{tenant_b}", name="Tenant B"),
                UserModel(
                    id=UUID(user_a),
                    tenant_id=UUID(tenant_a),
                    email=f"reviewer-{user_a}@example.test",
                    password_hash="test-password-hash",
                    display_name="Reviewer A",
                ),
                UserModel(
                    id=UUID(user_b),
                    tenant_id=UUID(tenant_b),
                    email=f"reviewer-{user_b}@example.test",
                    password_hash="test-password-hash",
                    display_name="Reviewer B",
                ),
            ]
        )
        session.commit()

    context = AnalysisRepositoryContext(
        engine=analysis_engine,
        factory=create_analysis_unit_of_work_factory(analysis_engine),
        tenant_a=tenant_a,
        tenant_b=tenant_b,
        user_a=user_a,
        user_b=user_b,
    )
    try:
        yield context
    finally:
        tenant_ids = [UUID(tenant_a), UUID(tenant_b)]
        with analysis_engine.begin() as connection:
            # Operational failures are intentionally append-only.  The official
            # integration runner drops its disposable database after the suite,
            # so never weaken the production trigger merely to clean this fixture.
            retained_tenant_ids = set(
                connection.scalars(
                    select(OperationalFailureModel.tenant_id).where(
                        OperationalFailureModel.tenant_id.in_(tenant_ids)
                    )
                )
            )
            connection.execute(
                delete(OutboxEventModel).where(OutboxEventModel.tenant_id.in_(tenant_ids))
            )
            connection.execute(
                delete(AnalysisRequestIdempotencyRecordModel).where(
                    AnalysisRequestIdempotencyRecordModel.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(
                delete(LLMExtractionResultModel).where(
                    LLMExtractionResultModel.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(
                delete(AnalysisStageAttemptModel).where(
                    AnalysisStageAttemptModel.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(
                delete(AnalysisStageRunModel).where(AnalysisStageRunModel.tenant_id.in_(tenant_ids))
            )
            connection.execute(
                delete(AnalysisRunModel).where(AnalysisRunModel.tenant_id.in_(tenant_ids))
            )
            connection.execute(
                delete(DataLifecycleEventModel).where(
                    DataLifecycleEventModel.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(
                delete(CaseSensitivePayloadModel).where(
                    CaseSensitivePayloadModel.tenant_id.in_(tenant_ids)
                )
            )
            connection.execute(delete(CaseModel).where(CaseModel.tenant_id.in_(tenant_ids)))
            connection.execute(delete(UserModel).where(UserModel.tenant_id.in_(tenant_ids)))
            removable_tenant_ids = [
                tenant_id for tenant_id in tenant_ids if tenant_id not in retained_tenant_ids
            ]
            if removable_tenant_ids:
                connection.execute(
                    delete(TenantModel).where(TenantModel.id.in_(removable_tenant_ids))
                )


@dataclass(frozen=True, slots=True)
class AnalysisGraph:
    case: Case
    run: AnalysisRun
    stage: AnalysisStageRun
    idempotency: AnalysisRequestIdempotencyRecord
    outbox: OutboxEvent


def _case(*, tenant_id: str, user_id: str) -> Case:
    return Case.create(
        case_id=str(uuid4()),
        tenant_id=tenant_id,
        order_ref="ORD-ANALYSIS",
        product_ref="SKU-ANALYSIS",
        customer_message="The bottle arrived dented and leaking.",
        requested_action=RequestedAction.EXCHANGE,
        attributes={"source": "analysis-integration"},
        created_by=user_id,
        now=NOW,
    )


def _analysis_graph(*, tenant_id: str, user_id: str) -> AnalysisGraph:
    case = _case(tenant_id=tenant_id, user_id=user_id)
    run_id = str(uuid4())
    stage_id = str(uuid4())
    event_id = str(uuid4())
    correlation_id = f"corr-{uuid4()}"
    idempotency_key = f"analysis-{uuid4()}"
    run = AnalysisRun(
        id=run_id,
        tenant_id=tenant_id,
        case_id=case.id,
        pipeline=AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION,
        pipeline_version="1.0.0",
        trigger=AnalysisTrigger.USER_REQUEST,
        status=AnalysisRunStatus.QUEUED,
        requested_by=user_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        request_hash=HASH,
        requested_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    stage = AnalysisStageRun(
        id=stage_id,
        tenant_id=tenant_id,
        analysis_run_id=run_id,
        stage_type=AnalysisStageType.TEXT_EXTRACTION,
        status=AnalysisStageStatus.QUEUED,
        provider_name="mock",
        model_name="csight-mock-llm",
        model_version="0.1.0",
        model_revision="integration",
        prompt_name="product-defect-text-extraction",
        prompt_version="1.0.0",
        prompt_content_hash=HASH,
        input_schema_version="1.0",
        output_schema_version="1.0",
        created_at=NOW,
        updated_at=NOW,
    )
    idempotency = AnalysisRequestIdempotencyRecord(
        id=str(uuid4()),
        tenant_id=tenant_id,
        case_id=case.id,
        idempotency_key=idempotency_key,
        request_hash=HASH,
        analysis_run_id=run_id,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )
    outbox = OutboxEvent(
        id=event_id,
        tenant_id=tenant_id,
        aggregate_type="analysis_run",
        aggregate_id=run_id,
        event_type="analysis.requested.v1",
        event_version="1.0",
        payload={
            "event_id": event_id,
            "event_type": "analysis.requested.v1",
            "event_version": "1.0",
            "tenant_id": tenant_id,
            "case_id": case.id,
            "analysis_run_id": run_id,
            "stage_run_id": stage_id,
            "correlation_id": correlation_id,
            "occurred_at": NOW.isoformat(),
        },
        status=OutboxStatus.PENDING,
        available_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    return AnalysisGraph(
        case=case,
        run=run,
        stage=stage,
        idempotency=idempotency,
        outbox=outbox,
    )


def _persist_case(context: AnalysisRepositoryContext, case: Case) -> None:
    with context.factory() as unit_of_work:
        unit_of_work.cases.add(tenant_id=case.tenant_id, case=case)
        unit_of_work.commit()


def _persist_graph(context: AnalysisRepositoryContext, graph: AnalysisGraph) -> None:
    _persist_case(context, graph.case)
    with context.factory() as unit_of_work:
        claim = unit_of_work.request_idempotency.claim(
            tenant_id=graph.run.tenant_id,
            record=graph.idempotency,
        )
        assert claim.claimed is True
        unit_of_work.analysis_runs.add(tenant_id=graph.run.tenant_id, run=graph.run)
        unit_of_work.stage_runs.add(tenant_id=graph.run.tenant_id, stage_run=graph.stage)
        unit_of_work.outbox.add(tenant_id=graph.run.tenant_id, event=graph.outbox)
        unit_of_work.commit()


def test_atomic_graph_creation_replay_and_tenant_scope(
    analysis_context: AnalysisRepositoryContext,
) -> None:
    graph = _analysis_graph(
        tenant_id=analysis_context.tenant_a,
        user_id=analysis_context.user_a,
    )
    _persist_graph(analysis_context, graph)

    replay_record = graph.idempotency.model_copy(update={"id": str(uuid4())})
    with analysis_context.factory() as unit_of_work:
        replay = unit_of_work.request_idempotency.claim(
            tenant_id=analysis_context.tenant_a,
            record=replay_record,
        )
        assert replay.claimed is False
        assert replay.record == graph.idempotency
        assert (
            unit_of_work.analysis_runs.latest(
                tenant_id=analysis_context.tenant_a,
                case_id=graph.case.id,
            )
            == graph.run
        )
        assert (
            unit_of_work.analysis_runs.get(
                tenant_id=analysis_context.tenant_b,
                case_id=graph.case.id,
                analysis_run_id=graph.run.id,
            )
            is None
        )
        assert (
            unit_of_work.stage_runs.get(
                tenant_id=analysis_context.tenant_b,
                analysis_run_id=graph.run.id,
                stage_run_id=graph.stage.id,
            )
            is None
        )


def test_unclaimed_dispatch_failure_is_conditional_and_allows_zero_attempts(
    analysis_context: AnalysisRepositoryContext,
) -> None:
    graph = _analysis_graph(
        tenant_id=analysis_context.tenant_a,
        user_id=analysis_context.user_a,
    )
    _persist_graph(analysis_context, graph)
    failure = AnalysisFailure(
        code="OUTBOX_DISPATCH_FAILED",
        message="Dispatch retries were exhausted.",
        retryable=False,
    )
    failed_at = NOW + timedelta(minutes=5)

    with analysis_context.factory() as unit_of_work:
        stage = unit_of_work.stage_runs.transition(
            tenant_id=analysis_context.tenant_a,
            analysis_run_id=graph.run.id,
            stage_run_id=graph.stage.id,
            expected_status=AnalysisStageStatus.QUEUED,
            target_status=AnalysisStageStatus.FAILED,
            now=failed_at,
            failure=failure,
        )
        run = unit_of_work.analysis_runs.transition(
            tenant_id=analysis_context.tenant_a,
            analysis_run_id=graph.run.id,
            expected_status=AnalysisRunStatus.QUEUED,
            target_status=AnalysisRunStatus.FAILED,
            now=failed_at,
            failure=failure,
        )
        unit_of_work.commit()

    assert stage is not None
    assert stage.status is AnalysisStageStatus.FAILED
    assert stage.attempt_summary.attempt_count == 0
    assert stage.started_at == failed_at
    assert stage.completed_at == failed_at
    assert stage.failure == failure
    assert run is not None and run.status is AnalysisRunStatus.FAILED

    with analysis_context.factory() as unit_of_work:
        assert (
            unit_of_work.stage_runs.transition(
                tenant_id=analysis_context.tenant_a,
                analysis_run_id=graph.run.id,
                stage_run_id=graph.stage.id,
                expected_status=AnalysisStageStatus.QUEUED,
                target_status=AnalysisStageStatus.FAILED,
                now=failed_at,
                failure=failure,
            )
            is None
        )


def test_claim_fencing_attempt_history_and_append_only_result(
    analysis_context: AnalysisRepositoryContext,
) -> None:
    graph = _analysis_graph(
        tenant_id=analysis_context.tenant_a,
        user_id=analysis_context.user_a,
    )
    _persist_graph(analysis_context, graph)
    claim_token = str(uuid4())
    started_at = NOW + timedelta(seconds=1)
    completed_at = NOW + timedelta(seconds=2)
    metadata = ProviderExecutionMetadata(
        provider_name="mock",
        model_name="csight-mock-llm",
        model_version="0.1.0",
        model_revision="integration",
        provider_request_id="provider-request-1",
        input_token_count=24,
        output_token_count=12,
        latency_ms=8,
    )

    with analysis_context.factory() as unit_of_work:
        running_run = unit_of_work.analysis_runs.transition(
            tenant_id=analysis_context.tenant_a,
            analysis_run_id=graph.run.id,
            expected_status=AnalysisRunStatus.QUEUED,
            target_status=AnalysisRunStatus.RUNNING,
            now=started_at,
        )
        claimed = unit_of_work.stage_runs.claim_for_execution(
            tenant_id=analysis_context.tenant_a,
            analysis_run_id=graph.run.id,
            stage_run_id=graph.stage.id,
            claim_token=claim_token,
            now=started_at,
            claim_expires_at=started_at + timedelta(minutes=5),
        )
        duplicate_claim = unit_of_work.stage_runs.claim_for_execution(
            tenant_id=analysis_context.tenant_a,
            analysis_run_id=graph.run.id,
            stage_run_id=graph.stage.id,
            claim_token=str(uuid4()),
            now=started_at,
            claim_expires_at=started_at + timedelta(minutes=5),
        )
        unit_of_work.commit()

    assert running_run is not None
    assert claimed is not None
    assert claimed.claim_token == claim_token
    assert claimed.attempt_summary.attempt_count == 1
    assert duplicate_claim is None

    attempt = AnalysisStageAttempt(
        id=str(uuid4()),
        tenant_id=analysis_context.tenant_a,
        analysis_run_id=graph.run.id,
        stage_run_id=graph.stage.id,
        attempt_number=1,
        status=AnalysisAttemptStatus.RUNNING,
        claim_token=claim_token,
        provider_name=graph.stage.provider_name,
        model_name=graph.stage.model_name,
        model_version=graph.stage.model_version,
        model_revision=graph.stage.model_revision,
        prompt_name=graph.stage.prompt_name,
        prompt_version=graph.stage.prompt_version,
        prompt_content_hash=graph.stage.prompt_content_hash,
        input_schema_version=graph.stage.input_schema_version,
        output_schema_version=graph.stage.output_schema_version,
        started_at=started_at,
        created_at=started_at,
    )
    result = LLMExtractionResultRecord(
        id=str(uuid4()),
        tenant_id=analysis_context.tenant_a,
        analysis_run_id=graph.run.id,
        stage_run_id=graph.stage.id,
        result=LLMTextExtractionResult(
            language="en",
            issue_types=(ExtractionIssueType.DENT, ExtractionIssueType.LEAKAGE),
            claims=(
                LLMTextClaim(
                    type=ExtractionIssueType.DENT,
                    location=DefectLocation.SIDE,
                    description="The bottle is dented.",
                ),
            ),
            requested_action=ExtractedRequestedAction.EXCHANGE,
            missing_information=(MissingInformation.IMAGE_EVIDENCE,),
            summary="A dent and leakage were reported.",
        ),
        created_at=completed_at,
    )

    with analysis_context.factory() as unit_of_work:
        unit_of_work.stage_attempts.add(tenant_id=analysis_context.tenant_a, attempt=attempt)
        unit_of_work.flush()
        assert (
            unit_of_work.stage_attempts.finalize_if_claimed(
                tenant_id=analysis_context.tenant_a,
                stage_run_id=graph.stage.id,
                attempt_number=1,
                claim_token=str(uuid4()),
                target_status=AnalysisAttemptStatus.SUCCEEDED,
                completed_at=completed_at,
                provider_execution=metadata,
            )
            is None
        )
        finalized_attempt = unit_of_work.stage_attempts.finalize_if_claimed(
            tenant_id=analysis_context.tenant_a,
            stage_run_id=graph.stage.id,
            attempt_number=1,
            claim_token=claim_token,
            target_status=AnalysisAttemptStatus.SUCCEEDED,
            completed_at=completed_at,
            provider_execution=metadata,
        )
        assert (
            unit_of_work.stage_runs.transition_if_claimed(
                tenant_id=analysis_context.tenant_a,
                analysis_run_id=graph.run.id,
                stage_run_id=graph.stage.id,
                claim_token=str(uuid4()),
                target_status=AnalysisStageStatus.SUCCEEDED,
                now=completed_at,
                provider_execution=metadata,
            )
            is None
        )
        succeeded_stage = unit_of_work.stage_runs.transition_if_claimed(
            tenant_id=analysis_context.tenant_a,
            analysis_run_id=graph.run.id,
            stage_run_id=graph.stage.id,
            claim_token=claim_token,
            target_status=AnalysisStageStatus.SUCCEEDED,
            now=completed_at,
            provider_execution=metadata,
        )
        unit_of_work.extraction_results.add(
            tenant_id=analysis_context.tenant_a,
            result=result,
        )
        succeeded_run = unit_of_work.analysis_runs.transition(
            tenant_id=analysis_context.tenant_a,
            analysis_run_id=graph.run.id,
            expected_status=AnalysisRunStatus.RUNNING,
            target_status=AnalysisRunStatus.SUCCEEDED,
            now=completed_at,
        )
        unit_of_work.commit()

    assert finalized_attempt is not None
    assert finalized_attempt.status is AnalysisAttemptStatus.SUCCEEDED
    assert finalized_attempt.provider_execution == metadata
    assert succeeded_stage is not None
    assert succeeded_stage.status is AnalysisStageStatus.SUCCEEDED
    assert succeeded_stage.claim_token is None
    assert succeeded_run is not None and succeeded_run.status is AnalysisRunStatus.SUCCEEDED
    with analysis_context.factory() as unit_of_work:
        assert (
            unit_of_work.extraction_results.get_by_run(
                tenant_id=analysis_context.tenant_a,
                analysis_run_id=graph.run.id,
            )
            == result
        )
        assert unit_of_work.stage_attempts.list(
            tenant_id=analysis_context.tenant_a,
            stage_run_id=graph.stage.id,
        ) == (finalized_attempt,)

    duplicate_result = result.model_copy(update={"id": str(uuid4())})
    with pytest.raises(IntegrityError), analysis_context.factory() as unit_of_work:
        unit_of_work.extraction_results.add(
            tenant_id=analysis_context.tenant_a,
            result=duplicate_result,
        )
        unit_of_work.commit()


def test_outbox_skip_locked_claim_fencing_and_stale_recovery(
    analysis_context: AnalysisRepositoryContext,
) -> None:
    graph = _analysis_graph(
        tenant_id=analysis_context.tenant_a,
        user_id=analysis_context.user_a,
    )
    _persist_graph(analysis_context, graph)
    first_token = str(uuid4())

    first_uow = analysis_context.factory()
    second_uow = analysis_context.factory()
    try:
        first_claim = first_uow.outbox.claim_batch(
            now=NOW,
            stale_before=NOW - timedelta(minutes=5),
            claim_token=first_token,
            claimed_by="dispatcher-1",
            limit=10,
        )
        skipped_claim = second_uow.outbox.claim_batch(
            now=NOW,
            stale_before=NOW - timedelta(minutes=5),
            claim_token=str(uuid4()),
            claimed_by="dispatcher-2",
            limit=10,
        )
        assert first_claim == (
            graph.outbox.model_copy(
                update={
                    "status": OutboxStatus.PROCESSING,
                    "attempt_count": 1,
                    "claimed_at": NOW,
                    "claimed_by": "dispatcher-1",
                    "claim_token": first_token,
                    "updated_at": NOW,
                }
            ),
        )
        assert skipped_claim == ()
        first_uow.commit()
        second_uow.commit()
    finally:
        first_uow.rollback()
        second_uow.rollback()

    with analysis_context.factory() as unit_of_work:
        assert (
            unit_of_work.outbox.mark_published(
                tenant_id=analysis_context.tenant_b,
                event_id=graph.outbox.id,
                claim_token=first_token,
                published_at=NOW + timedelta(seconds=1),
            )
            is None
        )
        published = unit_of_work.outbox.mark_published(
            tenant_id=analysis_context.tenant_a,
            event_id=graph.outbox.id,
            claim_token=first_token,
            published_at=NOW + timedelta(seconds=1),
        )
        unit_of_work.commit()

    assert published is not None
    assert published.status is OutboxStatus.PUBLISHED
    assert published.claim_token is None

    stale_graph = _analysis_graph(
        tenant_id=analysis_context.tenant_a,
        user_id=analysis_context.user_a,
    )
    _persist_graph(analysis_context, stale_graph)
    stale_token = str(uuid4())
    with analysis_context.factory() as unit_of_work:
        assert (
            len(
                unit_of_work.outbox.claim_batch(
                    now=NOW,
                    stale_before=NOW - timedelta(minutes=5),
                    claim_token=stale_token,
                    claimed_by="dispatcher-stale",
                    limit=10,
                )
            )
            == 1
        )
        unit_of_work.commit()

    recovered_at = NOW + timedelta(minutes=10)
    with analysis_context.factory() as unit_of_work:
        recovered_count = unit_of_work.outbox.recover_stale(
            stale_before=NOW + timedelta(seconds=1),
            available_at=recovered_at,
        )
        unit_of_work.commit()
    assert recovered_count == 1

    final_token = str(uuid4())
    with analysis_context.factory() as unit_of_work:
        reclaimed = unit_of_work.outbox.claim_batch(
            now=recovered_at,
            stale_before=recovered_at - timedelta(minutes=5),
            claim_token=final_token,
            claimed_by="dispatcher-final",
            limit=10,
        )
        assert len(reclaimed) == 1
        assert reclaimed[0].id == stale_graph.outbox.id
        failed = unit_of_work.outbox.mark_failed(
            tenant_id=analysis_context.tenant_a,
            event_id=stale_graph.outbox.id,
            claim_token=final_token,
            last_error=" terminal broker failure ",
            now=recovered_at + timedelta(seconds=1),
        )
        unit_of_work.commit()

    assert failed is not None
    assert failed.status is OutboxStatus.FAILED
    assert failed.last_error == "terminal broker failure"
    assert failed.claim_token is None


def test_database_rejects_cross_tenant_stage_reference(
    analysis_context: AnalysisRepositoryContext,
) -> None:
    graph = _analysis_graph(
        tenant_id=analysis_context.tenant_a,
        user_id=analysis_context.user_a,
    )
    _persist_case(analysis_context, graph.case)
    with analysis_context.factory() as unit_of_work:
        unit_of_work.analysis_runs.add(tenant_id=analysis_context.tenant_a, run=graph.run)
        unit_of_work.commit()

    cross_tenant_stage = graph.stage.model_copy(
        update={"id": str(uuid4()), "tenant_id": analysis_context.tenant_b}
    )
    with pytest.raises(IntegrityError), analysis_context.factory() as unit_of_work:
        unit_of_work.stage_runs.add(
            tenant_id=analysis_context.tenant_b,
            stage_run=cross_tenant_stage,
        )
        unit_of_work.commit()
