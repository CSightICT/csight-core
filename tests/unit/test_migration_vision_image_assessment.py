"""Offline contract tests for the image-level Vision assessment revision."""

from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

pytestmark = pytest.mark.unit
PREVIOUS = "20260827_0014_review_report_poc_metrics"
REVISION = "20260827_0015_vision_image_assessment"
HEAD = "20260831_0036_policy_query_search_events_v2"


def _config(output: StringIO) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"), stdout=output, output_buffer=output)
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
    )
    return config


def test_vision_image_assessment_revision_is_the_single_head() -> None:
    scripts = ScriptDirectory.from_config(_config(StringIO()))
    revision = scripts.get_revision(REVISION)

    assert scripts.get_heads() == [HEAD]
    assert revision is not None
    assert revision.down_revision == PREVIOUS


def test_upgrade_adds_only_non_localizing_assessment_contract() -> None:
    output = StringIO()
    command.upgrade(_config(output), f"{PREVIOUS}:{REVISION}", sql=True)
    sql = output.getvalue()

    assert "CREATE TABLE vision_image_assessments" in sql
    assert "HIGH_CONFIDENCE_DEFECT_CANDIDATE" in sql
    assert "BELOW_HIGH_CONFIDENCE_THRESHOLD" in sql
    assert "score >= threshold" in sql
    assert "fk_vision_image_assessments_tenant_result_vision_results" in sql
    assert "ON DELETE RESTRICT" in sql
    assert "normalized_xyxy" not in sql
    assert "canonical_label" not in sql
    assert "DROP TABLE vision_detections" not in sql


def test_downgrade_removes_only_image_assessment_table() -> None:
    output = StringIO()
    command.downgrade(_config(output), f"{REVISION}:{PREVIOUS}", sql=True)
    sql = output.getvalue()

    assert "DROP TABLE vision_image_assessments" in sql
    assert "DROP TABLE vision_analysis_results" not in sql
    assert "DROP TABLE vision_detections" not in sql
