"""Transactional reset with an archived copy; no model/policy/evidence deletion."""

import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.tenant_context import tenant_context
from app.ports.demo_reset import DemoResetConflict

# Child-first deletion order; these are only human-decision-derived records.
TABLES = (
    "case_learning_assets",
    "customer_communication_simulations",
    "review_reports",
    "external_action_simulation_results",
    "external_action_simulation_attempts",
    "external_action_simulation_request_events",
    "case_resolution_events",
    "case_resolution_request_events",
    "external_action_intents",
    "case_resolutions",
    "human_review_decision_basis",
    "human_review_decisions",
)


class SQLAlchemyDemoResetRepository:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def run(self, tenant_id: str, actor_id: str, expected: str | None) -> dict[str, Any]:
        with tenant_context(tenant_id), self.factory() as session, session.begin():
            session.execute(text("SET LOCAL lock_timeout = '3s'"))
            session.execute(text("SET LOCAL statement_timeout = '15s'"))
            # Prevent review/worker races while calculating and applying the reset.
            if expected is not None:
                names = sorted(
                    (
                        *TABLES,
                        "human_review_tasks",
                        "human_review_actions",
                        "human_review_assignments",
                        "cases",
                        "analysis_runs",
                        "policy_evaluation_runs",
                        "policy_retrieval_runs",
                        "grounded_explanation_runs",
                    )
                )
                session.execute(
                    text("LOCK TABLE " + ", ".join(names) + " IN SHARE ROW EXCLUSIVE MODE")
                )
            params: dict[str, Any] = {"tenant": tenant_id}
            tasks = list(
                session.execute(
                    text("""
                SELECT to_jsonb(t) AS row FROM human_review_tasks t
                JOIN cases c ON c.id=t.case_id AND c.tenant_id=t.tenant_id
                WHERE c.tenant_id=CAST(:tenant AS uuid) AND c.source_scope='SYNTHETIC_DEMO'
                  AND t.status <> 'PENDING' ORDER BY t.id
            """),
                    params,
                ).scalars()
            )
            case_ids = sorted({row["case_id"] for row in tasks})
            if len(case_ids) > 100:
                raise DemoResetConflict("한 번에 최대 100건까지 초기화할 수 있습니다.")
            params["cases"] = case_ids
            snapshot: dict[str, Any] = {"human_review_tasks": tasks}
            case_filter = "tenant_id=CAST(:tenant AS uuid) AND case_id=ANY(CAST(:cases AS uuid[]))"
            task_filter = (
                "tenant_id=CAST(:tenant AS uuid) AND review_task_id IN "
                "(SELECT id FROM human_review_tasks WHERE " + case_filter + ")"
            )
            decision_filter = (
                "tenant_id=CAST(:tenant AS uuid) AND human_review_decision_id IN "
                "(SELECT id FROM human_review_decisions WHERE " + task_filter + ")"
            )
            snapshot["human_review_tasks"] = list(
                session.execute(
                    text(
                        "SELECT to_jsonb(r) FROM human_review_tasks r WHERE "
                        + case_filter
                        + " ORDER BY id"
                    ),
                    params,
                ).scalars()
            )
            snapshot["human_review_assignments"] = list(
                session.execute(
                    text(
                        "SELECT to_jsonb(r) FROM human_review_assignments r WHERE "
                        + task_filter
                        + " ORDER BY id"
                    ),
                    params,
                ).scalars()
            )
            filters = {name: case_filter for name in TABLES}
            filters["human_review_decisions"] = task_filter
            filters["human_review_decision_basis"] = decision_filter
            for name in TABLES:
                snapshot[name] = list(
                    session.execute(
                        text(f"SELECT to_jsonb(r) FROM {name} r WHERE {filters[name]} ORDER BY id"),
                        params,
                    ).scalars()
                )
            # Unknown/active work must complete before any reset is offered/applied.
            for name in (
                "analysis_runs",
                "policy_evaluation_runs",
                "policy_retrieval_runs",
                "grounded_explanation_runs",
            ):
                if session.scalar(
                    text(
                        f"SELECT count(*) FROM {name} WHERE {case_filter} "
                        "AND status IN ('QUEUED','RUNNING','RETRY_WAITING')"
                    ),
                    params,
                ):
                    raise DemoResetConflict("분석 작업이 진행 중입니다. 완료된 뒤 초기화해 주세요.")
            for name in (
                "case_resolution_request_events",
                "external_action_simulation_request_events",
            ):
                if any(r["status"] in ("PENDING", "PROCESSING") for r in snapshot[name]):
                    raise DemoResetConflict(
                        "결정 후 처리가 진행 중입니다. 완료된 뒤 초기화해 주세요."
                    )
            canonical = json.dumps(
                snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            )
            fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
            result: dict[str, Any] = {
                "enabled": True,
                "count": len(case_ids),
                "fingerprint": fingerprint,
                "reset_id": None,
            }
            if expected is None:
                return result
            if expected != fingerprint:
                raise DemoResetConflict("문의 상태가 변경되었습니다. 대상을 다시 확인해 주세요.")
            if not case_ids:
                return result
            reset_id = str(uuid4())
            session.execute(
                text("""INSERT INTO demo_review_resets
                (id, tenant_id, actor_id, snapshot, created_at)
                VALUES (CAST(:id AS uuid), CAST(:tenant AS uuid), CAST(:actor AS uuid),
                        CAST(:snapshot AS jsonb), now())"""),
                {"id": reset_id, "tenant": tenant_id, "actor": actor_id, "snapshot": canonical},
            )
            for name in TABLES:
                session.execute(text(f"DELETE FROM {name} WHERE {filters[name]}"), params)
            # Keep immutable action/assignment history; close any open assignment.
            session.execute(
                text(
                    "UPDATE human_review_assignments SET released_at=now() WHERE "
                    + task_filter
                    + " AND released_at IS NULL"
                ),
                params,
            )
            session.execute(
                text(
                    """UPDATE human_review_tasks SET status='PENDING',
                current_assignee_id=NULL, resolved_at=NULL, version=version+1, updated_at=now()
                WHERE """
                    + case_filter
                ),
                params,
            )
            result["reset_id"] = reset_id
            return result
