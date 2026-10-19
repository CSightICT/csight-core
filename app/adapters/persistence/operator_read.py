"""PostgreSQL read adapter for operator queues and workflow snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.platform.operator_read import (
    OperatorCaseItem,
    OperatorReviewItem,
    QueueCounts,
    QueueSort,
    QueueView,
    WorkflowComponent,
    WorkflowSnapshot,
    WorkflowStage,
)
from app.ports.operator_read import CaseQueueSlice, ReviewQueueSlice

_VIEW_PREDICATE = """
    (:view = 'all'
      OR (:view = 'my' AND is_my)
      OR (:view = 'unassigned' AND is_unassigned)
      OR (:view = 'urgent' AND is_urgent)
      OR (:view = 'waiting_evidence' AND is_waiting_evidence)
      OR (:view = 'complete' AND is_complete))
"""

_CASE_SEARCH_PREDICATE = """
    (CAST(:query_pattern AS text) IS NULL
      OR CAST(case_id AS text) ILIKE :query_pattern ESCAPE '!'
      OR order_ref ILIKE :query_pattern ESCAPE '!'
      OR product_ref ILIKE :query_pattern ESCAPE '!')
"""

_REVIEW_SEARCH_PREDICATE = """
    (CAST(:query_pattern AS text) IS NULL
      OR CAST(case_id AS text) ILIKE :query_pattern ESCAPE '!'
      OR CAST(review_task_id AS text) ILIKE :query_pattern ESCAPE '!'
      OR order_ref ILIKE :query_pattern ESCAPE '!'
      OR product_ref ILIKE :query_pattern ESCAPE '!')
"""


def _query_pattern(query: str | None) -> str | None:
    if query is None:
        return None
    escaped = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{escaped}%"


class SQLAlchemyOperatorReadRepository:
    """Execute each public queue or snapshot read as exactly one SQL statement."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def list_cases(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        can_view_all: bool,
        view: QueueView,
        sort: QueueSort,
        query: str | None,
        limit: int,
        after_created_at: datetime | None,
        after_id: str | None,
    ) -> CaseQueueSlice:
        direction = "DESC" if sort is QueueSort.NEWEST else "ASC"
        comparator = "<" if sort is QueueSort.NEWEST else ">"
        keyset = ""
        if after_created_at is not None and after_id is not None:
            keyset = (
                "AND (created_at, case_id) "
                f"{comparator} (:after_created_at, CAST(:after_id AS uuid))"
            )
        statement = text(
            f"""
            WITH task_ranked AS (
                SELECT t.*,
                       row_number() OVER (
                           PARTITION BY t.case_id
                           ORDER BY t.created_at DESC, t.id DESC
                       ) AS row_number
                  FROM human_review_tasks AS t
                 WHERE t.tenant_id = CAST(:tenant_id AS uuid)
            ),
            latest_task AS (
                SELECT * FROM task_ranked WHERE row_number = 1
            ),
            report_ranked AS (
                SELECT r.*,
                       row_number() OVER (
                           PARTITION BY r.case_id
                           ORDER BY r.resolution_version DESC, r.generated_at DESC, r.id DESC
                       ) AS row_number
                  FROM review_reports AS r
                 WHERE r.tenant_id = CAST(:tenant_id AS uuid)
            ),
            latest_report AS (
                SELECT * FROM report_ranked WHERE row_number = 1
            ),
            base AS (
                SELECT c.id AS case_id,
                       c.status AS case_status,
                       c.order_ref,
                       c.product_ref,
                       c.requested_action,
                       left(btrim(regexp_replace(sp.customer_message, '[[:space:]]+', ' ', 'g')),
                            160) AS inquiry_preview,
                       c.created_at,
                       c.updated_at,
                       t.id AS review_task_id,
                       t.status AS review_status,
                       t.priority AS review_priority,
                       c.current_assignee_id AS assignee_id,
                       c.assignment_version,
                       cr.status AS resolution_status,
                       rr.id AS report_id,
                       rr.generated_at AS report_generated_at,
                       (hd.id IS NULL
                           AND c.current_assignee_id = CAST(:actor_id AS uuid)) AS is_my,
                       (hd.id IS NULL AND c.current_assignee_id IS NULL) AS is_unassigned,
                       (t.priority IN ('HIGH', 'CRITICAL')
                           AND t.status IN ('PENDING', 'CLAIMED', 'ESCALATED')) AS is_urgent,
                       (t.status = 'WAITING_FOR_EVIDENCE') AS is_waiting_evidence,
                       (hd.id IS NOT NULL AND (
                           :can_view_all OR hd.decided_by = CAST(:actor_id AS uuid)
                       )) AS is_complete
                  FROM cases AS c
                  LEFT JOIN case_sensitive_payloads AS sp
                    ON sp.tenant_id = c.tenant_id AND sp.case_id = c.id
                   AND sp.purged_at IS NULL AND sp.expires_at > CURRENT_TIMESTAMP
                  LEFT JOIN latest_task AS t ON t.case_id = c.id
                  LEFT JOIN case_resolutions AS cr
                    ON cr.tenant_id = c.tenant_id AND cr.case_id = c.id
                  LEFT JOIN latest_report AS rr ON rr.case_id = c.id
                  LEFT JOIN human_review_decisions AS hd
                    ON hd.tenant_id = t.tenant_id AND hd.review_task_id = t.id
                 WHERE c.tenant_id = CAST(:tenant_id AS uuid)
            ),
            visible AS (
                SELECT * FROM base
                 WHERE :can_view_all
                    OR assignee_id = CAST(:actor_id AS uuid)
                    OR EXISTS (
                        SELECT 1 FROM human_review_decisions AS decision
                         WHERE decision.tenant_id = CAST(:tenant_id AS uuid)
                           AND decision.review_task_id = base.review_task_id
                           AND decision.decided_by = CAST(:actor_id AS uuid)
                    )
            ),
            counts AS (
                SELECT count(*)::integer AS count_all,
                       count(*) FILTER (WHERE is_my)::integer AS count_my,
                       count(*) FILTER (WHERE is_unassigned)::integer AS count_unassigned,
                       count(*) FILTER (WHERE is_urgent)::integer AS count_urgent,
                       count(*) FILTER (WHERE is_waiting_evidence)::integer
                           AS count_waiting_evidence,
                       count(*) FILTER (WHERE is_complete)::integer AS count_complete
                  FROM visible
                 WHERE {_CASE_SEARCH_PREDICATE}
            ),
            page AS (
                SELECT * FROM visible
                 WHERE {_CASE_SEARCH_PREDICATE}
                   AND {_VIEW_PREDICATE}
                   {keyset}
                 ORDER BY created_at {direction}, case_id {direction}
                 LIMIT :page_size
            )
            SELECT counts.*, page.*
              FROM counts
              LEFT JOIN page ON TRUE
             ORDER BY page.created_at {direction}, page.case_id {direction}
            """
        )
        parameters: dict[str, object] = {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "can_view_all": can_view_all,
            "view": view.value,
            "query_pattern": _query_pattern(query),
            "page_size": limit + 1,
        }
        if after_created_at is not None and after_id is not None:
            parameters.update(after_created_at=after_created_at, after_id=after_id)
        with self._factory() as session:
            rows = session.execute(statement, parameters).mappings().all()
        counts = _counts(rows[0] if rows else {})
        items = tuple(_case_item(row) for row in rows if row.get("case_id") is not None)
        return CaseQueueSlice(items=items[:limit], counts=counts, has_more=len(items) > limit)

    def list_reviews(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        can_view_all: bool,
        view: QueueView,
        sort: QueueSort,
        query: str | None,
        limit: int,
        after_created_at: datetime | None,
        after_id: str | None,
    ) -> ReviewQueueSlice:
        direction = "DESC" if sort is QueueSort.NEWEST else "ASC"
        comparator = "<" if sort is QueueSort.NEWEST else ">"
        keyset = ""
        if after_created_at is not None and after_id is not None:
            keyset = (
                "AND (created_at, review_task_id) "
                f"{comparator} (:after_created_at, CAST(:after_id AS uuid))"
            )
        statement = text(
            f"""
            WITH report_ranked AS (
                SELECT r.*,
                       row_number() OVER (
                           PARTITION BY r.case_id
                           ORDER BY r.resolution_version DESC, r.generated_at DESC, r.id DESC
                       ) AS row_number
                  FROM review_reports AS r
                 WHERE r.tenant_id = CAST(:tenant_id AS uuid)
            ),
            latest_report AS (
                SELECT * FROM report_ranked WHERE row_number = 1
            ),
            base AS (
                SELECT t.id AS review_task_id,
                       t.case_id,
                       c.status AS case_status,
                       c.order_ref,
                       c.product_ref,
                       c.requested_action,
                       left(btrim(regexp_replace(sp.customer_message, '[[:space:]]+', ' ', 'g')),
                            160) AS inquiry_preview,
                       t.task_type,
                       t.priority,
                       t.status,
                       t.current_assignee_id AS assignee_id,
                       t.version,
                       t.created_at,
                       t.updated_at,
                       cr.status AS resolution_status,
                       rr.id AS report_id,
                       rr.generated_at AS report_generated_at,
                       (t.status IN ('CLAIMED', 'WAITING_FOR_EVIDENCE')
                           AND t.current_assignee_id = CAST(:actor_id AS uuid)) AS is_my,
                       (t.status IN ('PENDING', 'ESCALATED')
                           AND t.current_assignee_id IS NULL) AS is_unassigned,
                       (t.priority IN ('HIGH', 'CRITICAL')
                           AND t.status IN ('PENDING', 'CLAIMED', 'ESCALATED')) AS is_urgent,
                       (t.status = 'WAITING_FOR_EVIDENCE') AS is_waiting_evidence,
                       (t.status = 'RESOLVED' AND (
                           :can_view_all OR hd.decided_by = CAST(:actor_id AS uuid)
                       )) AS is_complete
                  FROM human_review_tasks AS t
                  JOIN cases AS c
                    ON c.tenant_id = t.tenant_id AND c.id = t.case_id
                  LEFT JOIN case_sensitive_payloads AS sp
                    ON sp.tenant_id = c.tenant_id AND sp.case_id = c.id
                   AND sp.purged_at IS NULL AND sp.expires_at > CURRENT_TIMESTAMP
                  LEFT JOIN case_resolutions AS cr
                    ON cr.tenant_id = t.tenant_id AND cr.case_id = t.case_id
                  LEFT JOIN latest_report AS rr ON rr.case_id = t.case_id
                  LEFT JOIN human_review_decisions AS hd
                    ON hd.tenant_id = t.tenant_id AND hd.review_task_id = t.id
                 WHERE t.tenant_id = CAST(:tenant_id AS uuid)
            ),
            visible AS (
                SELECT * FROM base
                 WHERE :can_view_all
                    OR assignee_id = CAST(:actor_id AS uuid)
                    OR EXISTS (
                        SELECT 1 FROM human_review_decisions AS decision
                         WHERE decision.tenant_id = CAST(:tenant_id AS uuid)
                           AND decision.review_task_id = base.review_task_id
                           AND decision.decided_by = CAST(:actor_id AS uuid)
                    )
            ),
            counts AS (
                SELECT count(*)::integer AS count_all,
                       count(*) FILTER (WHERE is_my)::integer AS count_my,
                       count(*) FILTER (WHERE is_unassigned)::integer AS count_unassigned,
                       count(*) FILTER (WHERE is_urgent)::integer AS count_urgent,
                       count(*) FILTER (WHERE is_waiting_evidence)::integer
                           AS count_waiting_evidence,
                       count(*) FILTER (WHERE is_complete)::integer AS count_complete
                  FROM visible
                 WHERE {_REVIEW_SEARCH_PREDICATE}
            ),
            page AS (
                SELECT * FROM visible
                 WHERE {_REVIEW_SEARCH_PREDICATE}
                   AND {_VIEW_PREDICATE}
                   {keyset}
                 ORDER BY created_at {direction}, review_task_id {direction}
                 LIMIT :page_size
            )
            SELECT counts.*, page.*
              FROM counts
              LEFT JOIN page ON TRUE
             ORDER BY page.created_at {direction}, page.review_task_id {direction}
            """
        )
        parameters: dict[str, object] = {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "can_view_all": can_view_all,
            "view": view.value,
            "query_pattern": _query_pattern(query),
            "page_size": limit + 1,
        }
        if after_created_at is not None and after_id is not None:
            parameters.update(after_created_at=after_created_at, after_id=after_id)
        with self._factory() as session:
            rows = session.execute(statement, parameters).mappings().all()
        counts = _counts(rows[0] if rows else {})
        items = tuple(_review_item(row) for row in rows if row.get("review_task_id") is not None)
        return ReviewQueueSlice(items=items[:limit], counts=counts, has_more=len(items) > limit)

    def get_workflow_snapshot(self, *, tenant_id: str, case_id: str) -> WorkflowSnapshot | None:
        statement = text(
            """
            SELECT c.id AS case_id,
                   c.status AS case_status,
                   a.id AS analysis_id,
                   a.status AS analysis_status,
                   a.started_at AS analysis_started_at,
                   a.completed_at AS analysis_completed_at,
                   a.failure_code AS analysis_failure_code,
                   a.correlation_id AS analysis_correlation_id,
                   COALESCE(stage_data.stages, '[]'::jsonb) AS stages,
                   stage_data.retry_at,
                   stage_data.has_failed_stage,
                   pr.id AS retrieval_id,
                   pr.status AS retrieval_status,
                   pr.started_at AS retrieval_started_at,
                   pr.completed_at AS retrieval_completed_at,
                   pr.failure_code AS retrieval_failure_code,
                   pr.correlation_id AS retrieval_correlation_id,
                   ge.id AS grounding_id,
                   ge.status AS grounding_status,
                   ge.started_at AS grounding_started_at,
                   ge.completed_at AS grounding_completed_at,
                   ge.failure_code AS grounding_failure_code,
                   ge.correlation_id AS grounding_correlation_id,
                   pe.id AS evaluation_id,
                   pe.status AS evaluation_status,
                   pe.started_at AS evaluation_started_at,
                   pe.completed_at AS evaluation_completed_at,
                   pe.failure_code AS evaluation_failure_code,
                   pe.correlation_id AS evaluation_correlation_id,
                   ht.id AS review_id,
                   ht.status AS review_status,
                   ht.created_at AS review_started_at,
                   ht.resolved_at AS review_completed_at,
                   ht_pe.correlation_id AS review_correlation_id,
                   cr.id AS resolution_id,
                   cr.status AS resolution_status,
                   cr.created_at AS resolution_started_at,
                   CASE WHEN cr.status IN (
                       'ACTION_NOT_REQUIRED', 'MANUAL_FOLLOW_UP_REQUIRED',
                       'ACTION_NEEDS_INPUT', 'ACTION_DRY_RUN_VALIDATED',
                       'ACTION_DRY_RUN_FAILED'
                   ) THEN cr.updated_at END AS resolution_completed_at,
                   cr.failure_code AS resolution_failure_code,
                   cr.correlation_id AS resolution_correlation_id,
                   rr.id AS report_id,
                   CASE WHEN rr.id IS NOT NULL THEN 'GENERATED' END AS report_status,
                   rr.generated_at AS report_started_at,
                   rr.generated_at AS report_completed_at,
                   cr.correlation_id AS report_correlation_id,
                   (rr.id IS NOT NULL) AS terminal,
                   (a.status IN ('PARTIAL_SUCCESS', 'FAILED')
                     OR COALESCE(stage_data.has_failed_stage, FALSE)
                     OR pr.status = 'FAILED'
                     OR ge.status = 'FAILED'
                     OR pe.status = 'FAILED'
                     OR cr.status IN (
                         'MANUAL_FOLLOW_UP_REQUIRED', 'ACTION_NEEDS_INPUT',
                         'ACTION_DRY_RUN_FAILED'
                     )) AS degraded,
                   CASE
                     WHEN rr.id IS NOT NULL THEN 'REPORT'
                     WHEN cr.id IS NOT NULL THEN 'RESOLUTION'
                     WHEN ht.status = 'RESOLVED' THEN 'HUMAN_REVIEW'
                     WHEN pe.status = 'SUCCEEDED' THEN 'POLICY_EVALUATION'
                     WHEN ge.status = 'SUCCEEDED' THEN 'GROUNDED_EXPLANATION'
                     WHEN pr.status = 'SUCCEEDED' THEN 'POLICY_RETRIEVAL'
                     WHEN a.status IN ('SUCCEEDED', 'PARTIAL_SUCCESS') THEN 'ANALYSIS'
                     ELSE 'CASE_RECEIVED'
                   END AS last_good,
                   COALESCE(
                       cr.correlation_id, ht_pe.correlation_id, pe.correlation_id,
                       ge.correlation_id, pr.correlation_id, a.correlation_id
                   ) AS correlation_id
              FROM cases AS c
              LEFT JOIN LATERAL (
                  SELECT r.* FROM analysis_runs AS r
                   WHERE r.tenant_id = c.tenant_id AND r.case_id = c.id
                     AND r.pipeline_name = 'product_defect_text_extraction'
                   ORDER BY r.created_at DESC, r.id DESC LIMIT 1
              ) AS a ON TRUE
              LEFT JOIN LATERAL (
                  SELECT jsonb_agg(
                             jsonb_build_object(
                                 'stage_type', s.stage_type,
                                 'status', s.status,
                                 'attempt_count', s.attempt_count,
                                 'next_attempt_at', s.next_attempt_at,
                                 'failure_code', s.failure_code
                             ) ORDER BY s.created_at, s.id
                         ) AS stages,
                         min(s.next_attempt_at) FILTER (
                             WHERE s.status = 'RETRY_WAITING'
                         ) AS retry_at,
                         bool_or(s.status = 'FAILED') AS has_failed_stage
                    FROM analysis_stage_runs AS s
                   WHERE s.tenant_id = c.tenant_id AND s.analysis_run_id = a.id
              ) AS stage_data ON TRUE
              LEFT JOIN LATERAL (
                  SELECT r.* FROM policy_retrieval_runs AS r
                   WHERE r.tenant_id = c.tenant_id AND r.case_id = c.id
                   ORDER BY r.created_at DESC, r.id DESC LIMIT 1
              ) AS pr ON TRUE
              LEFT JOIN LATERAL (
                  SELECT r.* FROM grounded_explanation_runs AS r
                   WHERE r.tenant_id = c.tenant_id AND r.case_id = c.id
                   ORDER BY r.created_at DESC, r.id DESC LIMIT 1
              ) AS ge ON TRUE
              LEFT JOIN LATERAL (
                  SELECT r.* FROM policy_evaluation_runs AS r
                   WHERE r.tenant_id = c.tenant_id AND r.case_id = c.id
                   ORDER BY r.created_at DESC, r.id DESC LIMIT 1
              ) AS pe ON TRUE
              LEFT JOIN LATERAL (
                  SELECT t.* FROM human_review_tasks AS t
                   WHERE t.tenant_id = c.tenant_id AND t.case_id = c.id
                   ORDER BY t.created_at DESC, t.id DESC LIMIT 1
              ) AS ht ON TRUE
              LEFT JOIN policy_evaluation_runs AS ht_pe
                ON ht_pe.tenant_id = c.tenant_id
               AND ht_pe.id = ht.policy_evaluation_run_id
              LEFT JOIN case_resolutions AS cr
                ON cr.tenant_id = c.tenant_id AND cr.case_id = c.id
              LEFT JOIN LATERAL (
                  SELECT r.* FROM review_reports AS r
                   WHERE r.tenant_id = c.tenant_id AND r.case_id = c.id
                   ORDER BY r.resolution_version DESC, r.generated_at DESC, r.id DESC LIMIT 1
              ) AS rr ON TRUE
             WHERE c.tenant_id = CAST(:tenant_id AS uuid)
               AND c.id = CAST(:case_id AS uuid)
            """
        )
        with self._factory() as session:
            row = (
                session.execute(
                    statement,
                    {"tenant_id": tenant_id, "case_id": case_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        stages_value = row["stages"]
        stages = tuple(WorkflowStage.model_validate(value) for value in stages_value)
        return WorkflowSnapshot(
            case_id=str(row["case_id"]),
            case_status=str(row["case_status"]),
            terminal=bool(row["terminal"]),
            degraded=bool(row["degraded"]),
            retry_at=row["retry_at"],
            last_good=str(row["last_good"]),
            correlation_id=row["correlation_id"],
            analysis=_component(row, "analysis"),
            stages=stages,
            policy_retrieval=_component(row, "retrieval"),
            grounded_explanation=_component(row, "grounding"),
            policy_evaluation=_component(row, "evaluation"),
            review=_component(row, "review"),
            resolution=_component(row, "resolution"),
            report=_component(row, "report"),
        )


def _counts(row: Mapping[Any, Any]) -> QueueCounts:
    return QueueCounts(
        all=int(row.get("count_all") or 0),
        my=int(row.get("count_my") or 0),
        unassigned=int(row.get("count_unassigned") or 0),
        urgent=int(row.get("count_urgent") or 0),
        waiting_evidence=int(row.get("count_waiting_evidence") or 0),
        complete=int(row.get("count_complete") or 0),
    )


def _case_item(row: Mapping[Any, Any]) -> OperatorCaseItem:
    return OperatorCaseItem(
        case_id=str(row["case_id"]),
        case_status=str(row["case_status"]),
        order_ref=str(row["order_ref"]),
        product_ref=str(row["product_ref"]),
        requested_action=str(row["requested_action"]),
        inquiry_preview=row.get("inquiry_preview"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        review_task_id=_optional_uuid(row["review_task_id"]),
        review_status=row["review_status"],
        review_priority=row["review_priority"],
        assignee_id=_optional_uuid(row["assignee_id"]),
        assignment_version=int(row["assignment_version"]),
        resolution_status=row["resolution_status"],
        report_id=_optional_uuid(row["report_id"]),
        report_generated_at=row["report_generated_at"],
    )


def _review_item(row: Mapping[Any, Any]) -> OperatorReviewItem:
    return OperatorReviewItem(
        review_task_id=str(row["review_task_id"]),
        case_id=str(row["case_id"]),
        case_status=str(row["case_status"]),
        order_ref=str(row["order_ref"]),
        product_ref=str(row["product_ref"]),
        requested_action=str(row["requested_action"]),
        inquiry_preview=row.get("inquiry_preview"),
        task_type=str(row["task_type"]),
        priority=str(row["priority"]),
        status=str(row["status"]),
        assignee_id=_optional_uuid(row["assignee_id"]),
        version=int(row["version"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        resolution_status=row["resolution_status"],
        report_id=_optional_uuid(row["report_id"]),
        report_generated_at=row["report_generated_at"],
    )


def _component(row: Mapping[Any, Any], prefix: str) -> WorkflowComponent | None:
    identifier = row[f"{prefix}_id"]
    if identifier is None:
        return None
    return WorkflowComponent(
        run_id=str(identifier),
        status=str(row[f"{prefix}_status"]),
        started_at=row[f"{prefix}_started_at"],
        completed_at=row[f"{prefix}_completed_at"],
        failure_code=row.get(f"{prefix}_failure_code"),
        correlation_id=row.get(f"{prefix}_correlation_id"),
    )


def _optional_uuid(value: UUID | None) -> str | None:
    return None if value is None else str(value)


__all__ = ["SQLAlchemyOperatorReadRepository"]
