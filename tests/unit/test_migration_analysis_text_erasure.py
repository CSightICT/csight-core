"""Offline contracts for migration 0027 analysis-text erasure."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit
PREVIOUS = "20260830_0026_case_assignment_ownership"
REVISION = "20260830_0027_analysis_text_erasure"
CURRENT_HEAD = "20260831_0034_analysis_model_route_snapshot"


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_analysis_text_erasure_is_linear_head() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    revision = scripts.get_revision(REVISION)

    assert scripts.get_heads() == [CURRENT_HEAD]
    assert revision is not None
    assert revision.down_revision == PREVIOUS


def test_upgrade_redacts_derived_prose_and_installs_deferred_guards() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert "ADD COLUMN analysis_text_purged_at" in sql
    assert "UPDATE llm_extraction_results AS result" in sql
    assert "UPDATE llm_extraction_results_v2 AS result" in sql
    assert "UPDATE policy_retrieval_run_queries AS query" in sql
    assert "UPDATE grounded_explanation_results AS result" in sql
    assert "CREATE FUNCTION csight_assert_analysis_text_erasure" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_payload_analysis_text_erasure" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_llm_v2_analysis_text_erasure" in sql
    assert "analysis text erasure contract violation: derived prose remains" in sql
    assert "DROP TABLE" not in sql


def test_downgrade_refuses_to_claim_redacted_prose_can_be_restored() -> None:
    output = StringIO()
    command.downgrade(_config(output), f"{REVISION}:{PREVIOUS}", sql=True)
    sql = output.getvalue()

    assert "analysis text erasure downgrade blocked: redacted prose cannot be restored" in sql
    assert "DROP COLUMN analysis_text_purged_at" in sql
