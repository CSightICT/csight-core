"""Run only on the disposable clone provided by run_integration_tests.py."""

import hashlib
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text

from app.adapters.persistence.demo_reset import SQLAlchemyDemoResetRepository
from app.adapters.persistence.human_review import SQLAlchemyHumanReviewRepository
from app.adapters.persistence.session import create_session_factory
from app.bootstrap.settings import Settings
from app.platform.human_review import HumanDecisionRequest
from app.platform.tenant import Role
from app.ports.demo_reset import DemoResetConflict

pytestmark = pytest.mark.integration


def test_reset_archives_results_preserves_analysis_and_rejects_stale_preview():
    database = os.environ.get("CSIGHT_DISPOSABLE_TEST_DATABASE", "")
    if not database.startswith("csight_integration_"):
        pytest.skip("Requires explicit disposable clone")
    url = Settings().database_url_value
    assert url and database in url
    engine = create_engine(url)
    repo = SQLAlchemyDemoResetRepository(create_session_factory(engine))
    with engine.connect() as connection:
        row = connection.execute(
            text("""SELECT c.tenant_id, c.created_by FROM cases c
            JOIN human_review_tasks t ON t.case_id=c.id AND t.tenant_id=c.tenant_id
            WHERE c.source_scope='SYNTHETIC_DEMO' AND t.status <> 'PENDING' LIMIT 1""")
        ).first()
        assert row, "Clone requires at least one reviewed synthetic case"

        def preserved():
            return {
                table: hashlib.sha256(
                    str(
                        connection.execute(
                            text(f"SELECT to_jsonb(r) FROM {table} r ORDER BY id")
                        ).all()
                    ).encode()
                ).hexdigest()
                for table in (
                    "cases",
                    "case_evidence",
                    "analysis_runs",
                    "policy_evaluation_runs",
                    "human_review_packets",
                    "human_review_actions",
                )
            }

        before = preserved()
        tenant, actor = map(str, row)
        assert repo.run(str(uuid4()), actor, None)["count"] == 0
        preview = repo.run(tenant, actor, None)
        assert preview["count"] > 0
        with pytest.raises(DemoResetConflict):
            repo.run(tenant, actor, "0" * 64)

        def interrupt_delete(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("DELETE FROM case_learning_assets"):
                raise RuntimeError("injected reset interruption")

        event.listen(engine, "before_cursor_execute", interrupt_delete)
        try:
            with pytest.raises(RuntimeError, match="injected reset interruption"):
                repo.run(tenant, actor, preview["fingerprint"])
        finally:
            event.remove(engine, "before_cursor_execute", interrupt_delete)
        assert repo.run(tenant, actor, None) == preview
        assert connection.scalar(text("SELECT count(*) FROM demo_review_resets")) == 0
        done = repo.run(tenant, actor, preview["fingerprint"])
        assert done["reset_id"]
        assert repo.run(tenant, actor, None)["count"] == 0
        with pytest.raises(DemoResetConflict):
            repo.run(tenant, actor, preview["fingerprint"])
        connection.commit()
        assert preserved() == before
        archive = connection.scalar(
            text("SELECT snapshot FROM demo_review_resets WHERE id=CAST(:id AS uuid)"),
            {"id": done["reset_id"]},
        )
        assert archive["human_review_tasks"]
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM human_review_decisions "
                    "WHERE tenant_id=CAST(:tenant AS uuid)"
                ),
                {"tenant": tenant},
            )
            == 0
        )
        old = archive["human_review_decisions"][0]
        review_repo = SQLAlchemyHumanReviewRepository(create_session_factory(engine))
        detail = review_repo.get(tenant_id=tenant, task_id=old["review_task_id"])
        assert detail and detail.task.status.value == "PENDING"
        review_repo.claim(
            tenant_id=tenant,
            task_id=detail.task.id,
            actor_id=old["decided_by"],
            roles=frozenset({Role.ADMIN}),
            expected_version=detail.task.version,
        )
        task, decision = review_repo.resolve(
            tenant_id=tenant,
            task_id=detail.task.id,
            actor_id=old["decided_by"],
            roles=frozenset({Role.ADMIN}),
            expected_version=detail.task.version + 1,
            request=HumanDecisionRequest.model_validate(
                {
                    "decision": old["decision_type"],
                    "reason_codes": old["reason_codes"],
                    "rationale": old["rationale"],
                    "basis": [
                        {"type": b["basis_type"], "reference_id": b["reference_id"]}
                        for b in archive["human_review_decision_basis"]
                        if b["human_review_decision_id"] == old["id"]
                    ],
                }
            ),
        )
        assert task.status.value == "RESOLVED" and decision.id != old["id"]
    engine.dispose()
