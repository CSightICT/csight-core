"""Opt-in disposable PostgreSQL proof: Shadow -> policy -> human -> DRY_RUN."""

from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.adapters.persistence.models import AnalysisRunModel
from app.adapters.persistence.policy_engine import SQLAlchemyPolicyEngineRepository
from app.platform.analysis import ShadowAnalysisDownstreamForbiddenError
from tests.integration.test_human_review_persistence import (
    HumanReviewIntegrationContext,
)
from tests.integration.test_human_review_persistence import (
    human_review_database as _database_fixture,
)
from tests.integration.test_human_review_persistence import (
    test_review_event_task_packet_claim_resolve_and_tenant_isolation as _run_human_workflow,
)

pytestmark = pytest.mark.integration
human_review_database = _database_fixture


@pytest.mark.parametrize("human_review_database", [True], indirect=True)
def test_shadow_feedback_full_workflow_and_immutable_permission(
    human_review_database: HumanReviewIntegrationContext,
) -> None:
    context = human_review_database
    with context.factory() as session:
        analysis = session.scalars(select(AnalysisRunModel)).first()
        assert analysis is not None and analysis.execution_mode == "SHADOW"
        source: dict[str, Any] = dict(
            tenant_id=str(analysis.tenant_id),
            case_id=str(analysis.case_id),
            analysis_run_id=str(analysis.id),
            requested_by=str(analysis.requested_by),
            as_of_date=date(2026, 2, 1),
            correlation_id="feedback-test",
            idempotency_key=str(uuid4()),
            request_hash="d" * 64,
        )
    with pytest.raises(ShadowAnalysisDownstreamForbiddenError):
        SQLAlchemyPolicyEngineRepository(context.factory).create(**source)

    # Uses only synthetic fixtures/test principals in this disposable database.
    # Covers policy execution, review packet, tenant/role restrictions, explicit human resolve,
    # resolution, network-free simulated action, report and communication simulation.
    _run_human_workflow(context)
    with context.engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM policy_evaluation_runs WHERE shadow_feedback_allowed")
            )
            > 0
        )
    with pytest.raises(DBAPIError, match="immutable"), context.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE policy_evaluation_runs SET shadow_feedback_allowed=false "
                "WHERE shadow_feedback_allowed"
            )
        )
    with pytest.raises(DBAPIError, match="requires PRIMARY"), context.engine.begin() as connection:
        # Direct SQL remains blocked for an unmarked Shadow root, even after a marked run.
        connection.execute(
            text(
                "INSERT INTO policy_evaluation_runs (id, tenant_id, case_id, analysis_run_id) "
                "VALUES (:id, :tenant_id, :case_id, :analysis_run_id)"
            ),
            {**source, "id": uuid4()},
        )
    config = Config("alembic.ini")
    config.set_main_option(
        "sqlalchemy.url",
        context.engine.url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    with pytest.raises(DBAPIError, match="Feedback history exists"):
        command.downgrade(config, "20260831_0036_policy_query_search_events_v2")


@pytest.mark.parametrize("human_review_database", [False], indirect=True)
def test_feedback_migration_round_trip_without_feedback_history(
    human_review_database: HumanReviewIntegrationContext,
) -> None:
    context = human_review_database
    config = Config("alembic.ini")
    config.set_main_option(
        "sqlalchemy.url",
        context.engine.url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    command.downgrade(config, "20260831_0036_policy_query_search_events_v2")
    with context.engine.connect() as connection:
        source = connection.scalar(
            text(
                "SELECT pg_get_functiondef("
                "'csight_require_primary_analysis_lineage()'::regprocedure)"
            )
        )
        assert "shadow_feedback_allowed" not in source
        assert "IF analysis_mode IS DISTINCT FROM 'PRIMARY' THEN" in source
    command.upgrade(config, "head")
    command.check(config)
    with pytest.raises(DBAPIError, match="requires PRIMARY"), context.engine.begin() as connection:
        # A guessed/missing/cross-tenant lineage cannot use the feedback marker to enter workflow.
        connection.execute(
            text(
                "INSERT INTO policy_evaluation_runs "
                "(id, tenant_id, case_id, analysis_run_id, shadow_feedback_allowed) "
                "VALUES (:id, :tenant, :case, :analysis, true)"
            ),
            {"id": uuid4(), "tenant": uuid4(), "case": uuid4(), "analysis": uuid4()},
        )
