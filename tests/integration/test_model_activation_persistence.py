"""Disposable PostgreSQL proof for signed release persistence and activation CAS."""

import base64
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from alembic import command
from app.adapters.llm.mock import MockLLMProvider
from app.adapters.persistence.model_activation import SQLAlchemyModelActivationRepository
from app.adapters.persistence.model_routing import SQLAlchemyModelRoutePlanRepository
from app.adapters.persistence.session import create_session_factory
from app.adapters.persistence.unit_of_work import create_analysis_unit_of_work_factory
from app.application.analysis import (
    StartTextAnalysis,
    StartTextAnalysisCommand,
)
from app.application.model_routing import ResolveActiveModelRoutePlan
from app.bootstrap.settings import Settings
from app.domains.product_defect_cs.prompts import (
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
    PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
)
from app.platform.analysis.enums import (
    TEXT_EXTRACTION_V2_PIPELINE_VERSION,
    AnalysisExecutionMode,
    AnalysisPipeline,
)
from app.platform.case import Case, RequestedAction
from app.platform.model_activation import (
    LLMReleaseManifest,
    ModelActivationConflictError,
    ModelActivationEvent,
    ModelReleaseTask,
    SignedLLMReleaseManifest,
)
from app.platform.model_routing import (
    ActiveModelRoutePlanRequiredError,
    ModelRouteActivationConflictError,
    ModelRoutePlan,
    ModelRoutePlanConflictError,
)
from app.platform.tenant import Principal, Role

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 30, 6, 0, tzinfo=UTC)


class _Clock:
    def now(self) -> datetime:
        return NOW


class _Ids:
    def new_id(self) -> str:
        return str(uuid4())


class _AcceptSignature:
    def verify(self, value: SignedLLMReleaseManifest) -> bool:
        del value
        return True


@pytest.fixture(scope="module")
def model_release_engine() -> Generator[Engine, None, None]:
    if os.getenv("RUN_CORE_INTEGRATION") != "1":
        pytest.skip("set RUN_CORE_INTEGRATION=1 to test signed model persistence")
    configured_url = Settings().database_url_value
    if not configured_url:
        pytest.fail("DATABASE_URL is required for signed model persistence tests")
    source_url = make_url(configured_url)
    database_name = f"csight_model_release_0028_{uuid4().hex[:16]}"
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
        command.check(config)
        temporary_engine = create_engine(temporary_url, poolclass=NullPool)
        yield temporary_engine
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        if created:
            with admin_engine.connect() as connection:
                quoted_name = connection.dialect.identifier_preparer.quote(database_name)
                connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {quoted_name} WITH (FORCE)")
        admin_engine.dispose()


def _signed_manifest(
    task: ModelReleaseTask = ModelReleaseTask.PRODUCT_DEFECT_TEXT_EXTRACTION_V2,
) -> SignedLLMReleaseManifest:
    digest = "sha256:" + "a" * 64
    manifest = LLMReleaseManifest(
        candidate_id="qwen38-27b-int4-vllm028",
        package_name="csight-qwen38-27b-int4",
        package_version="2026.08.30.1",
        task=task,
        artifact="Qwen/Qwen3.8-27B",
        artifact_revision="1" * 40,
        artifact_content_digest=digest,
        runtime_image="vllm/vllm-openai",
        runtime_image_digest=digest,
        dependency_lock_digest=digest,
        sbom_digest=digest,
        served_model_name="csight-qwen38-27b",
        model_version="Qwen3.8-27B-INT4",
        prompt_name="product_defect_text_extraction",
        prompt_version="2.0.0",
        prompt_content_hash="b" * 64,
        input_schema_version="2.0",
        output_schema_version="2.0",
        precision="awq-int4",
        max_context_tokens=8192,
        max_num_sequences=1,
        gpu_memory_utilization=0.9,
        kv_cache_dtype="auto",
        qualification_dataset_digest=digest,
        qualification_result_digest=digest,
        candidate_matrix_digest=digest,
        candidate_assessment_digest=digest,
        qualified_at=NOW,
    )
    return SignedLLMReleaseManifest(
        manifest=manifest,
        signing_key_id="release-key-1",
        signature_base64=base64.b64encode(b"s" * 64).decode(),
    )


def test_registration_activation_replay_cas_and_append_only(
    model_release_engine: Engine,
) -> None:
    tenant_id, user_id, release_id = (str(uuid4()) for _ in range(3))
    with model_release_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, 'Model Test')"),
            {"id": tenant_id, "slug": f"model-{tenant_id}"},
        )
        connection.execute(
            text(
                "INSERT INTO users (id, tenant_id, email, password_hash, display_name) "
                "VALUES (:id, :tenant, :email, 'hash', 'Admin')"
            ),
            {"id": user_id, "tenant": tenant_id, "email": f"{user_id}@example.test"},
        )

    session_factory = create_session_factory(model_release_engine)
    repository = SQLAlchemyModelActivationRepository(session_factory)
    release, replay = repository.register_release(
        tenant_id=tenant_id,
        release_id=release_id,
        value=_signed_manifest(),
        registered_by=user_id,
        registered_at=NOW,
    )
    replayed_release, replayed = repository.register_release(
        tenant_id=tenant_id,
        release_id=str(uuid4()),
        value=_signed_manifest(),
        registered_by=user_id,
        registered_at=NOW,
    )
    assert replay is False
    assert replayed is True
    assert replayed_release.id == release.id

    # Package versions are unique per task, allowing independently qualified LLM jobs.
    query_release, query_replay = repository.register_release(
        tenant_id=tenant_id,
        release_id=str(uuid4()),
        value=_signed_manifest(ModelReleaseTask.POLICY_QUERY_BUILDER_V1),
        registered_by=user_id,
        registered_at=NOW,
    )
    assert query_replay is False
    assert query_release.signed_manifest.manifest.task is ModelReleaseTask.POLICY_QUERY_BUILDER_V1

    first = ModelActivationEvent(
        id=str(uuid4()),
        tenant_id=tenant_id,
        task=release.signed_manifest.manifest.task,
        execution_mode=AnalysisExecutionMode.PRIMARY,
        model_release_id=release.id,
        activated_by=user_id,
        reason="Qualified target host activation.",
        idempotency_key="activate-1",
        request_hash="c" * 64,
        activated_at=NOW,
    )
    activated, activation_replay = repository.activate(
        event=first,
        expected_current_activation_id=None,
    )
    replayed_activation, replayed = repository.activate(
        event=first.model_copy(update={"id": str(uuid4())}),
        expected_current_activation_id=None,
    )
    assert activation_replay is False
    assert replayed is True
    assert replayed_activation.id == activated.id
    second = first.model_copy(
        update={
            "id": str(uuid4()),
            "previous_activation_id": activated.id,
            "idempotency_key": "activate-2",
            "request_hash": "e" * 64,
            # Equal timestamps prove current state follows the append chain, not wall-clock order.
            "activated_at": NOW,
        }
    )
    latest, latest_replay = repository.activate(
        event=second,
        expected_current_activation_id=activated.id,
    )
    assert latest_replay is False
    active = repository.get_active(
        tenant_id=tenant_id,
        task=first.task,
        execution_mode=first.execution_mode,
    )
    assert active is not None
    assert active.activation.id == latest.id
    historical_activation = repository.get_by_activation_id(
        tenant_id=tenant_id,
        activation_id=activated.id,
    )
    assert historical_activation is not None
    assert historical_activation.activation == activated

    route_repository = SQLAlchemyModelRoutePlanRepository(session_factory)
    analysis_unit_of_work_factory = create_analysis_unit_of_work_factory(model_release_engine)
    case = Case.create(
        case_id=str(uuid4()),
        tenant_id=tenant_id,
        order_ref="ORD-ROUTE-SNAPSHOT",
        product_ref="SKU-ROUTE-SNAPSHOT",
        customer_message="The item arrived damaged.",
        requested_action=RequestedAction.EXCHANGE,
        attributes={"source": "model-route-integration"},
        created_by=user_id,
        now=NOW,
    )
    with analysis_unit_of_work_factory() as unit_of_work:
        unit_of_work.cases.add(tenant_id=tenant_id, case=case)
        unit_of_work.commit()
    route_resolver = ResolveActiveModelRoutePlan(
        route_repository=route_repository,
        activation_repository=repository,
        signature_verifier=_AcceptSignature(),
    )
    start_analysis = StartTextAnalysis(
        uow_factory=analysis_unit_of_work_factory,
        provider=MockLLMProvider(),
        prompt=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT,
        prompt_v2=PRODUCT_DEFECT_TEXT_EXTRACTION_PROMPT_V2,
        clock=_Clock(),
        id_generator=_Ids(),
        model_route_resolver=route_resolver,
    )
    principal = Principal(
        user_id=user_id,
        tenant_id=tenant_id,
        email=f"{user_id}@example.test",
        display_name="Admin",
        roles=frozenset({Role.ADMIN}),
    )
    start_command = StartTextAnalysisCommand(
        pipeline=AnalysisPipeline.PRODUCT_DEFECT_TEXT_EXTRACTION,
        pipeline_version=TEXT_EXTRACTION_V2_PIPELINE_VERSION,
        execution_mode=AnalysisExecutionMode.PRIMARY,
        idempotency_key="analysis-route-retry",
        correlation_id="correlation-route-retry",
    )
    with pytest.raises(ActiveModelRoutePlanRequiredError):
        start_analysis.execute(principal=principal, case_id=case.id, command=start_command)
    with model_release_engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM analysis_request_idempotency_records "
                    "WHERE tenant_id=:tenant AND idempotency_key=:idempotency_key"
                ),
                {"tenant": tenant_id, "idempotency_key": start_command.idempotency_key},
            )
            == 0
        )

    first_route = ModelRoutePlan(
        id=str(uuid4()),
        tenant_id=tenant_id,
        task=first.task,
        execution_mode=first.execution_mode,
        model_activation_id=latest.id,
        deployment_id="onprem-4090-primary",
        activated_by=user_id,
        reason="Qualified fixed extraction route.",
        idempotency_key="route-1",
        request_hash="f" * 64,
        activated_at=NOW,
    )
    routed, route_replay = route_repository.activate(
        route_plan=first_route,
        expected_current_route_plan_id=None,
    )
    replayed_route, replayed = route_repository.activate(
        route_plan=first_route.model_copy(update={"id": str(uuid4())}),
        expected_current_route_plan_id=None,
    )
    assert route_replay is False
    assert replayed is True
    assert replayed_route.id == routed.id

    stale_route = first_route.model_copy(
        update={
            "id": str(uuid4()),
            "idempotency_key": "route-stale",
            "request_hash": "1" * 64,
        }
    )
    with pytest.raises(ModelRoutePlanConflictError):
        route_repository.activate(
            route_plan=stale_route,
            expected_current_route_plan_id=None,
        )

    third = second.model_copy(
        update={
            "id": str(uuid4()),
            "previous_activation_id": latest.id,
            "idempotency_key": "activate-3",
            "request_hash": "4" * 64,
        }
    )
    latest_activation, third_activation_replay = repository.activate(
        event=third,
        expected_current_activation_id=latest.id,
    )
    assert third_activation_replay is False
    with pytest.raises(ModelRouteActivationConflictError):
        start_analysis.execute(principal=principal, case_id=case.id, command=start_command)
    with model_release_engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM analysis_request_idempotency_records "
                    "WHERE tenant_id=:tenant AND idempotency_key=:idempotency_key"
                ),
                {"tenant": tenant_id, "idempotency_key": start_command.idempotency_key},
            )
            == 0
        )

    second_route = first_route.model_copy(
        update={
            "id": str(uuid4()),
            "previous_route_plan_id": routed.id,
            "model_activation_id": latest_activation.id,
            "deployment_id": "onprem-4090-canary",
            "idempotency_key": "route-2",
            "request_hash": "2" * 64,
        }
    )
    latest_route, latest_route_replay = route_repository.activate(
        route_plan=second_route,
        expected_current_route_plan_id=routed.id,
    )
    assert latest_route_replay is False
    assert (
        route_repository.get_active(
            tenant_id=tenant_id,
            task=first.task,
            execution_mode=first.execution_mode,
        )
        == latest_route
    )
    assert route_repository.get_by_id(tenant_id=tenant_id, route_plan_id=routed.id) == routed

    # The same key can now succeed because both earlier route failures rolled back
    # their tentative claims.  The successful stage snapshots the repaired route.
    started = start_analysis.execute(principal=principal, case_id=case.id, command=start_command)
    with analysis_unit_of_work_factory() as unit_of_work:
        persisted_stages = unit_of_work.stage_runs.list(
            tenant_id=tenant_id,
            analysis_run_id=started.run.id,
        )
    assert len(persisted_stages) == 1
    assert persisted_stages[0].model_route_plan_id == latest_route.id

    with model_release_engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL ROLE csight_worker_role")
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )
        assert connection.scalar(text("SELECT count(*) FROM llm_release_manifests")) == 2
        assert connection.scalar(text("SELECT count(*) FROM llm_model_route_plans")) == 2

    with (
        pytest.raises(DBAPIError, match="permission denied"),
        model_release_engine.begin() as connection,
    ):
        connection.exec_driver_sql("SET LOCAL ROLE csight_dispatcher_role")
        connection.execute(text("SELECT count(*) FROM llm_release_manifests"))

    stale = first.model_copy(
        update={
            "id": str(uuid4()),
            "idempotency_key": "activate-stale",
            "request_hash": "d" * 64,
            "previous_activation_id": None,
            "activated_at": NOW + timedelta(seconds=1),
        }
    )
    with pytest.raises(ModelActivationConflictError):
        repository.activate(event=stale, expected_current_activation_id=None)

    with (
        pytest.raises(DBAPIError, match="append-only"),
        model_release_engine.begin() as connection,
    ):
        connection.execute(
            text("UPDATE llm_release_manifests SET package_name='mutated' WHERE id=:id"),
            {"id": release.id},
        )

    with (
        pytest.raises(DBAPIError, match="append-only"),
        model_release_engine.begin() as connection,
    ):
        connection.execute(
            text("UPDATE llm_model_route_plans SET reason='mutated' WHERE id=:id"),
            {"id": latest_route.id},
        )
