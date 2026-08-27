"""Add append-only human review workflow and human-only decisions.

Revision ID: 20260827_0011_human_review
Revises: 20260827_0010_policy_engine
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260827_0011_human_review"
down_revision: str | None = "20260827_0010_policy_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_policy_citation_pack_items_tenant_id",
        "policy_citation_pack_items",
        ["tenant_id", "id"],
    )
    op.create_table(
        "human_review_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("policy_evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_assignee_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("mapping_rule_name", sa.String(128), nullable=False),
        sa.Column("mapping_rule_version", sa.String(64), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name="fk_human_review_tasks_case",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_evaluation_run_id"],
            ["policy_evaluation_runs.tenant_id", "policy_evaluation_runs.id"],
            name="fk_human_review_tasks_policy_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "current_assignee_id"],
            ["users.tenant_id", "users.id"],
            name="fk_human_review_tasks_assignee",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "task_type IN ('STANDARD_REVIEW','EVIDENCE_REVIEW','MANAGER_REVIEW',"
            "'POLICY_EXCEPTION_REVIEW','SAFETY_REVIEW')",
            name=op.f("ck_human_review_tasks_type_allowed"),
        ),
        sa.CheckConstraint(
            "priority IN ('LOW','NORMAL','HIGH','CRITICAL')",
            name=op.f("ck_human_review_tasks_priority_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','CLAIMED','WAITING_FOR_EVIDENCE','ESCALATED','RESOLVED')",
            name=op.f("ck_human_review_tasks_status_allowed"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_human_review_tasks_version_positive")),
        sa.CheckConstraint(
            "(status IN ('CLAIMED','RESOLVED') AND current_assignee_id IS NOT NULL) OR "
            "(status NOT IN ('CLAIMED','RESOLVED') AND current_assignee_id IS NULL)",
            name=op.f("ck_human_review_tasks_assignee_status_consistent"),
        ),
        sa.CheckConstraint(
            "(status = 'RESOLVED' AND resolved_at IS NOT NULL) OR "
            "(status <> 'RESOLVED' AND resolved_at IS NULL)",
            name=op.f("ck_human_review_tasks_resolved_timestamp_consistent"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_human_review_tasks")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_human_review_tasks_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "policy_evaluation_run_id",
            "task_type",
            name="uq_human_review_tasks_policy_run_type",
        ),
    )
    op.create_index(
        "ix_human_review_tasks_queue",
        "human_review_tasks",
        ["tenant_id", "status", "priority", "created_at", "id"],
    )
    op.create_table(
        "human_review_packets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("policy_evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("rule_set_version", sa.String(64), nullable=False),
        sa.Column("rule_set_hash", sa.String(64), nullable=False),
        sa.Column("llm_extraction_result_v2_id", sa.Uuid(), nullable=False),
        sa.Column("completeness_result_id", sa.Uuid(), nullable=False),
        sa.Column("vision_result_ids", postgresql.JSONB(), nullable=False),
        sa.Column("alignment_result_id", sa.Uuid(), nullable=True),
        sa.Column("citation_pack_id", sa.Uuid(), nullable=True),
        sa.Column("grounding_result_id", sa.Uuid(), nullable=True),
        sa.Column("case_metadata_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("qualification_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("policy_effects", postgresql.JSONB(), nullable=False),
        sa.Column("policy_summary_status", sa.String(64), nullable=False),
        sa.Column("packet_schema_version", sa.String(32), nullable=False),
        sa.Column("packet_hash", sa.String(64), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_task_id"],
            ["human_review_tasks.tenant_id", "human_review_tasks.id"],
            name="fk_human_review_packets_task",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name="fk_human_review_packets_case",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_run_id"],
            ["analysis_runs.tenant_id", "analysis_runs.id"],
            name="fk_human_review_packets_analysis",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_evaluation_run_id"],
            ["policy_evaluation_runs.tenant_id", "policy_evaluation_runs.id"],
            name="fk_human_review_packets_policy_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "rule_set_id"],
            ["policy_rule_sets.tenant_id", "policy_rule_sets.id"],
            name="fk_human_review_packets_rule_set",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "llm_extraction_result_v2_id"],
            ["llm_extraction_results_v2.tenant_id", "llm_extraction_results_v2.id"],
            name="fk_human_review_packets_extraction",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "completeness_result_id"],
            ["llm_extraction_results_v2.tenant_id", "llm_extraction_results_v2.id"],
            name="fk_human_review_packets_completeness",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "citation_pack_id"],
            ["policy_citation_packs.tenant_id", "policy_citation_packs.id"],
            name="fk_human_review_packets_citation_pack",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(vision_result_ids) = 'array'",
            name=op.f("ck_human_review_packets_vision_ids_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(case_metadata_snapshot) = 'object'",
            name=op.f("ck_human_review_packets_case_snapshot_object"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(qualification_snapshot) = 'object'",
            name=op.f("ck_human_review_packets_qualification_snapshot_object"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(policy_effects) = 'array' AND jsonb_array_length(policy_effects) > 0",
            name=op.f("ck_human_review_packets_effects_nonempty"),
        ),
        sa.CheckConstraint(
            "rule_set_hash ~ '^[0-9a-f]{64}$' AND packet_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_human_review_packets_hashes_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_human_review_packets")),
        sa.UniqueConstraint("tenant_id", "review_task_id", name="uq_human_review_packets_task"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_human_review_packets_tenant_id"),
    )
    op.create_table(
        "human_review_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(32), nullable=True),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False),
        sa.Column("rationale", sa.String(2000), nullable=True),
        sa.Column("action_payload", postgresql.JSONB(), nullable=False),
        sa.Column("expected_task_version", sa.Integer(), nullable=False),
        sa.Column("resulting_task_version", sa.Integer(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_task_id"],
            ["human_review_tasks.tenant_id", "human_review_tasks.id"],
            name="fk_human_review_actions_task",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["users.tenant_id", "users.id"],
            name="fk_human_review_actions_actor",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "action_type IN ('CREATED','CLAIMED','RELEASED','EVIDENCE_REQUESTED','RESUMED',"
            "'ESCALATED','RESOLVED')",
            name=op.f("ck_human_review_actions_type_allowed"),
        ),
        sa.CheckConstraint(
            "to_status IN ('PENDING','CLAIMED','WAITING_FOR_EVIDENCE','ESCALATED','RESOLVED')",
            name=op.f("ck_human_review_actions_to_status_allowed"),
        ),
        sa.CheckConstraint(
            "from_status IS NULL OR from_status IN "
            "('PENDING','CLAIMED','WAITING_FOR_EVIDENCE','ESCALATED','RESOLVED')",
            name=op.f("ck_human_review_actions_from_status_allowed"),
        ),
        sa.CheckConstraint(
            "resulting_task_version = expected_task_version + 1",
            name=op.f("ck_human_review_actions_version_step"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reason_codes) = 'array'",
            name=op.f("ck_human_review_actions_reasons_array"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(action_payload) = 'object'",
            name=op.f("ck_human_review_actions_payload_object"),
        ),
        sa.CheckConstraint(
            "(action_type = 'CREATED' AND actor_id IS NULL AND actor_role IS NULL) OR "
            "(action_type <> 'CREATED' AND actor_id IS NOT NULL AND "
            "actor_role IN ('ADMIN','REVIEWER'))",
            name=op.f("ck_human_review_actions_human_actor_required"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_human_review_actions")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_human_review_actions_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "review_task_id",
            "resulting_task_version",
            name="uq_human_review_actions_task_version",
        ),
    )
    op.create_index(
        "ix_human_review_actions_task_created",
        "human_review_actions",
        ["tenant_id", "review_task_id", "created_at", "id"],
    )
    op.create_table(
        "human_review_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_by", sa.Uuid(), nullable=False),
        sa.Column("assignment_type", sa.String(32), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_task_id"],
            ["human_review_tasks.tenant_id", "human_review_tasks.id"],
            name="fk_human_review_assignments_task",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assignee_id"],
            ["users.tenant_id", "users.id"],
            name="fk_human_review_assignments_assignee",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assigned_by"],
            ["users.tenant_id", "users.id"],
            name="fk_human_review_assignments_assigner",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "assignment_type IN ('SELF_CLAIM','ADMIN_ASSIGNMENT','ESCALATION_CLAIM')",
            name=op.f("ck_human_review_assignments_type_allowed"),
        ),
        sa.CheckConstraint(
            "released_at IS NULL OR released_at >= assigned_at",
            name=op.f("ck_human_review_assignments_released_after_assigned"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_human_review_assignments")),
    )
    op.create_index(
        "uq_human_review_assignments_current",
        "human_review_assignments",
        ["tenant_id", "review_task_id"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.create_table(
        "human_review_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("decision_type", sa.String(64), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False),
        sa.Column("rationale", sa.String(2000), nullable=False),
        sa.Column("outcome_relation", sa.String(64), nullable=False),
        sa.Column("outcome_relation_rule_version", sa.String(64), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_schema_version", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "review_task_id"],
            ["human_review_tasks.tenant_id", "human_review_tasks.id"],
            name="fk_human_review_decisions_task",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "decided_by"],
            ["users.tenant_id", "users.id"],
            name="fk_human_review_decisions_user",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "decision_type IN ('APPROVE_REFUND','APPROVE_EXCHANGE','APPROVE_RESHIPMENT',"
            "'APPROVE_REPAIR','REJECT_REQUEST','PROVIDE_INFORMATION','NO_ACTION')",
            name=op.f("ck_human_review_decisions_type_allowed"),
        ),
        sa.CheckConstraint(
            "length(btrim(rationale)) BETWEEN 10 AND 2000",
            name=op.f("ck_human_review_decisions_rationale_length"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reason_codes) = 'array'",
            name=op.f("ck_human_review_decisions_reasons_array"),
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_human_review_decisions_hash_valid"),
        ),
        sa.CheckConstraint(
            "outcome_relation IN ('CONSISTENT_WITH_RECOMMENDATION',"
            "'DIFFERS_FROM_RECOMMENDATION','NO_COMPARABLE_RECOMMENDATION',"
            "'INDETERMINATE_POLICY')",
            name=op.f("ck_human_review_decisions_outcome_relation_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_human_review_decisions")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_human_review_decisions_tenant_id"),
        sa.UniqueConstraint("tenant_id", "review_task_id", name="uq_human_review_decisions_task"),
    )
    op.create_table(
        "human_review_decision_basis",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("human_review_decision_id", sa.Uuid(), nullable=False),
        sa.Column("basis_type", sa.String(32), nullable=False),
        sa.Column("reference_id", sa.String(320), nullable=False),
        sa.Column("policy_rule_result_id", sa.Uuid(), nullable=True),
        sa.Column("policy_clause_row_id", sa.Uuid(), nullable=True),
        sa.Column("citation_item_id", sa.Uuid(), nullable=True),
        sa.Column("case_evidence_id", sa.Uuid(), nullable=True),
        sa.Column("analysis_result_id", sa.Uuid(), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "human_review_decision_id"],
            ["human_review_decisions.tenant_id", "human_review_decisions.id"],
            name="fk_human_review_decision_basis_decision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_rule_result_id"],
            ["policy_rule_evaluation_results.tenant_id", "policy_rule_evaluation_results.id"],
            name="fk_human_review_decision_basis_rule_result",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_clause_row_id"],
            ["policy_clauses.tenant_id", "policy_clauses.id"],
            name="fk_human_review_decision_basis_clause",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "citation_item_id"],
            ["policy_citation_pack_items.tenant_id", "policy_citation_pack_items.id"],
            name="fk_human_review_decision_basis_citation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_evidence_id"],
            ["case_evidence.tenant_id", "case_evidence.id"],
            name="fk_human_review_decision_basis_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "analysis_result_id"],
            ["llm_extraction_results_v2.tenant_id", "llm_extraction_results_v2.id"],
            name="fk_human_review_decision_basis_analysis",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "basis_type IN ('POLICY_RULE_RESULT','POLICY_CITATION','CASE_EVIDENCE',"
            "'ANALYSIS_RESULT')",
            name=op.f("ck_human_review_decision_basis_type_allowed"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(policy_rule_result_id, citation_item_id, case_evidence_id,"
            "analysis_result_id) = 1",
            name=op.f("ck_human_review_decision_basis_one_typed_reference"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_human_review_decision_basis")),
        sa.UniqueConstraint(
            "tenant_id",
            "human_review_decision_id",
            "basis_type",
            "reference_id",
            name="uq_human_review_decision_basis_reference",
        ),
    )
    op.create_table(
        "human_review_request_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("policy_evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["cases.tenant_id", "cases.id"],
            name="fk_human_review_request_events_case",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "policy_evaluation_run_id"],
            ["policy_evaluation_runs.tenant_id", "policy_evaluation_runs.id"],
            name="fk_human_review_request_events_policy_run",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','PUBLISHED','FAILED')",
            name=op.f("ck_human_review_request_events_status_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_human_review_request_events")),
        sa.UniqueConstraint(
            "tenant_id", "policy_evaluation_run_id", name="uq_human_review_request_events_run"
        ),
    )


def downgrade() -> None:
    op.drop_table("human_review_request_events")
    op.drop_table("human_review_decision_basis")
    op.drop_table("human_review_decisions")
    op.drop_index("uq_human_review_assignments_current", table_name="human_review_assignments")
    op.drop_table("human_review_assignments")
    op.drop_index("ix_human_review_actions_task_created", table_name="human_review_actions")
    op.drop_table("human_review_actions")
    op.drop_table("human_review_packets")
    op.drop_index("ix_human_review_tasks_queue", table_name="human_review_tasks")
    op.drop_table("human_review_tasks")
    op.drop_constraint(
        "uq_policy_citation_pack_items_tenant_id",
        "policy_citation_pack_items",
        type_="unique",
    )
