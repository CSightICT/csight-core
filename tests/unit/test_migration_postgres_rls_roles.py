"""Static contract for process roles and fail-closed PostgreSQL RLS."""

from io import StringIO
from pathlib import Path
from typing import cast

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Table

from app.adapters.persistence.model_registry import PERSISTENCE_MODELS

pytestmark = pytest.mark.unit

REVISION = "20260829_0020_postgres_rls_roles"
PREVIOUS = "20260829_0019_analysis_execution_modes"
HEAD = "20260831_0036_policy_query_search_events_v2"
MIGRATION = Path("alembic/versions/20260829_0020_postgres_rls_roles.py")
FAILURE_RECOVERY_MIGRATION = Path("alembic/versions/20260829_0021_failure_recovery.py")
CASE_ASSIGNMENT_MIGRATION = Path("alembic/versions/20260830_0026_case_assignment_ownership.py")
MODEL_ACTIVATION_MIGRATION = Path("alembic/versions/20260830_0028_signed_model_activation.py")
MODEL_ROUTING_MIGRATION = Path("alembic/versions/20260831_0033_model_route_plans.py")
FAILURE_RECOVERY_TABLES = frozenset(
    {
        "operational_failures",
        "operational_failure_recovery_runs",
        "operational_failure_recovery_events",
        "operational_failure_resolutions",
    }
)
CASE_ASSIGNMENT_TABLES = frozenset({"case_assignments", "case_assignment_actions"})
MODEL_ACTIVATION_TABLES = frozenset({"llm_release_manifests", "llm_model_activation_events"})
MODEL_ROUTING_TABLES = frozenset({"llm_model_route_plans"})


def test_rls_migration_is_linear_and_covers_every_tenant_model() -> None:
    config = Config(stdout=StringIO())
    config.set_main_option("script_location", "alembic")
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision(REVISION)

    assert revision is not None
    assert revision.down_revision == PREVIOUS
    assert scripts.get_heads() == [HEAD]

    source = MIGRATION.read_text(encoding="utf-8")
    failure_recovery_source = FAILURE_RECOVERY_MIGRATION.read_text(encoding="utf-8")
    case_assignment_source = CASE_ASSIGNMENT_MIGRATION.read_text(encoding="utf-8")
    model_activation_source = MODEL_ACTIVATION_MIGRATION.read_text(encoding="utf-8")
    model_routing_source = MODEL_ROUTING_MIGRATION.read_text(encoding="utf-8")
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "current_setting('app.tenant_id', true)" in source
    assert "csight_dispatcher_outbox_scope" in source
    assert "NOBYPASSRLS" in source
    assert "PASSWORD" not in source
    for model in PERSISTENCE_MODELS:
        table = cast(Table, model.__table__)
        if "tenant_id" in table.c:
            if table.name in FAILURE_RECOVERY_TABLES:
                migration_source = failure_recovery_source
            elif table.name in CASE_ASSIGNMENT_TABLES:
                migration_source = case_assignment_source
            elif table.name in MODEL_ACTIVATION_TABLES:
                migration_source = model_activation_source
            elif table.name in MODEL_ROUTING_TABLES:
                migration_source = model_routing_source
            else:
                migration_source = source
            assert f'"{table.name}"' in migration_source
