"""Preserve review ownership while waiting for evidence.

Revision ID: 20260830_0025_waiting_owner_and_similarity_contract
Revises: 20260830_0024_schema_drift_repair
Create Date: 2026-08-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260830_0025_waiting_owner_and_similarity_contract"
down_revision: str | None = "20260830_0024_schema_drift_repair"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TASK_CHECK = "ck_human_review_tasks_assignee_status_consistent"
_ASSIGNMENT_TYPE_CHECK = "ck_human_review_assignments_type_allowed"


def upgrade() -> None:
    op.drop_constraint(op.f(_TASK_CHECK), "human_review_tasks", type_="check")
    op.drop_constraint(
        op.f(_ASSIGNMENT_TYPE_CHECK),
        "human_review_assignments",
        type_="check",
    )
    op.create_check_constraint(
        op.f(_ASSIGNMENT_TYPE_CHECK),
        "human_review_assignments",
        "assignment_type IN "
        "('SELF_CLAIM','ADMIN_ASSIGNMENT','ESCALATION_CLAIM','WAITING_OWNER_RECOVERY')",
    )

    # Earlier releases closed the assignment interval and cleared the task
    # projection on EVIDENCE_REQUESTED. Recover the most recent known owner as a
    # new, explicit interval rather than rewriting the historical release time.
    op.execute(
        """
        WITH latest_assignment AS (
            SELECT DISTINCT ON (tenant_id, review_task_id)
                   tenant_id,
                   review_task_id,
                   assignee_id,
                   assigned_by
              FROM human_review_assignments
             ORDER BY tenant_id, review_task_id, assigned_at DESC, id DESC
        )
        UPDATE human_review_tasks AS task
           SET current_assignee_id = latest.assignee_id,
               updated_at = now()
          FROM latest_assignment AS latest
         WHERE task.tenant_id = latest.tenant_id
           AND task.id = latest.review_task_id
           AND task.status = 'WAITING_FOR_EVIDENCE'
           AND task.current_assignee_id IS NULL
        """
    )
    op.execute(
        """
        WITH latest_assignment AS (
            SELECT DISTINCT ON (tenant_id, review_task_id)
                   tenant_id,
                   review_task_id,
                   assignee_id,
                   assigned_by
              FROM human_review_assignments
             ORDER BY tenant_id, review_task_id, assigned_at DESC, id DESC
        )
        INSERT INTO human_review_assignments (
            id,
            tenant_id,
            review_task_id,
            assignee_id,
            assigned_by,
            assignment_type,
            assigned_at,
            released_at,
            created_at
        )
        SELECT gen_random_uuid(),
               task.tenant_id,
               task.id,
               task.current_assignee_id,
               latest.assigned_by,
               'WAITING_OWNER_RECOVERY',
               now(),
               NULL,
               now()
          FROM human_review_tasks AS task
          JOIN latest_assignment AS latest
            ON latest.tenant_id = task.tenant_id
           AND latest.review_task_id = task.id
         WHERE task.status = 'WAITING_FOR_EVIDENCE'
           AND task.current_assignee_id IS NOT NULL
           AND NOT EXISTS (
               SELECT 1
                 FROM human_review_assignments AS active
                WHERE active.tenant_id = task.tenant_id
                  AND active.review_task_id = task.id
                  AND active.released_at IS NULL
           )
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM human_review_tasks
                 WHERE status = 'WAITING_FOR_EVIDENCE'
                   AND current_assignee_id IS NULL
            ) THEN
                RAISE EXCEPTION 'waiting review task has no recoverable assignee';
            END IF;
        END;
        $$
        """
    )
    op.create_check_constraint(
        op.f(_TASK_CHECK),
        "human_review_tasks",
        "(status IN ('CLAIMED','WAITING_FOR_EVIDENCE') "
        "AND current_assignee_id IS NOT NULL) OR "
        "(status NOT IN ('CLAIMED','WAITING_FOR_EVIDENCE') "
        "AND current_assignee_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f(_TASK_CHECK), "human_review_tasks", type_="check")
    op.drop_constraint(
        op.f(_ASSIGNMENT_TYPE_CHECK),
        "human_review_assignments",
        type_="check",
    )
    op.execute(
        """
        UPDATE human_review_tasks
           SET current_assignee_id = NULL,
               updated_at = now()
         WHERE status = 'WAITING_FOR_EVIDENCE'
        """
    )
    op.execute(
        """
        DELETE FROM human_review_assignments
         WHERE assignment_type = 'WAITING_OWNER_RECOVERY'
        """
    )
    op.create_check_constraint(
        op.f(_ASSIGNMENT_TYPE_CHECK),
        "human_review_assignments",
        "assignment_type IN ('SELF_CLAIM','ADMIN_ASSIGNMENT','ESCALATION_CLAIM')",
    )
    op.create_check_constraint(
        op.f(_TASK_CHECK),
        "human_review_tasks",
        "(status = 'CLAIMED' AND current_assignee_id IS NOT NULL) OR "
        "(status <> 'CLAIMED' AND current_assignee_id IS NULL)",
    )
