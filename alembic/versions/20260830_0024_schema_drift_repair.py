"""Reconcile service-pilot PostgreSQL schema metadata drift.

Revision ID: 20260830_0024_schema_drift_repair
Revises: 20260830_0023_operator_assignment_similarity
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0024_schema_drift_repair"
down_revision: str | None = "20260830_0023_operator_assignment_similarity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK_CONSTRAINT_RENAMES: tuple[tuple[str, str, str], ...] = (
    (
        "operational_failures",
        "ck_operational_failures_ck_operational_failures_code_safe",
        "ck_operational_failures_code_safe",
    ),
    (
        "operational_failures",
        "ck_operational_failures_ck_operational_failures_correla_b0bf",
        "ck_operational_failures_correlation_nonempty",
    ),
    (
        "operational_failures",
        "ck_operational_failures_ck_operational_failures_kind_allowed",
        "ck_operational_failures_kind_allowed",
    ),
    (
        "operational_failures",
        "ck_operational_failures_ck_operational_failures_pipelin_6981",
        "ck_operational_failures_pipeline_allowed",
    ),
    (
        "operational_failures",
        "ck_operational_failures_ck_operational_failures_replaya_731a",
        "ck_operational_failures_replayable_dispatch_only",
    ),
    (
        "operational_failures",
        "ck_operational_failures_ck_operational_failures_source_allowed",
        "ck_operational_failures_source_allowed",
    ),
    (
        "operational_failure_recovery_runs",
        "ck_operational_failure_recovery_runs_ck_failure_recover_2825",
        "ck_operational_failure_recovery_runs_hash_valid",
    ),
    (
        "operational_failure_recovery_runs",
        "ck_operational_failure_recovery_runs_ck_failure_recover_bb68",
        "ck_operational_failure_recovery_runs_key_nonempty",
    ),
    (
        "operational_failure_recovery_events",
        "ck_operational_failure_recovery_events_ck_failure_recov_223d",
        "ck_operational_failure_recovery_events_topic_allowed",
    ),
    (
        "operational_failure_recovery_events",
        "ck_operational_failure_recovery_events_ck_failure_recov_3f69",
        "ck_operational_failure_recovery_events_payload_allowlist",
    ),
    (
        "operational_failure_recovery_events",
        "ck_operational_failure_recovery_events_ck_failure_recov_a47b",
        "ck_operational_failure_recovery_events_payload_identifiers",
    ),
    (
        "operational_failure_recovery_events",
        "ck_operational_failure_recovery_events_ck_failure_recov_b16c",
        "ck_operational_failure_recovery_events_attempts_nonnegative",
    ),
    (
        "operational_failure_recovery_events",
        "ck_operational_failure_recovery_events_ck_failure_recov_bfe2",
        "ck_operational_failure_recovery_events_state_consistent",
    ),
    (
        "operational_failure_recovery_events",
        "ck_operational_failure_recovery_events_ck_failure_recov_f6ee",
        "ck_operational_failure_recovery_events_status_allowed",
    ),
    (
        "operational_failure_resolutions",
        "ck_operational_failure_resolutions_ck_failure_resolutio_4e08",
        "ck_operational_failure_resolutions_action_allowed",
    ),
    (
        "operational_failure_resolutions",
        "ck_operational_failure_resolutions_ck_failure_resolutio_8c1e",
        "ck_operational_failure_resolutions_reason_allowed",
    ),
    (
        "operational_failure_resolutions",
        "ck_operational_failure_resolutions_ck_failure_resolutio_dd58",
        "ck_operational_failure_resolutions_action_consistent",
    ),
    (
        "operational_failure_resolutions",
        "ck_operational_failure_resolutions_ck_failure_resolutio_f330",
        "ck_operational_failure_resolutions_hashes_valid",
    ),
)


def _rename_constraint(*, table_name: str, current_name: str, target_name: str) -> None:
    # All identifiers are migration-owned constants. Fail if neither form exists so a
    # partially divergent customer schema cannot be silently stamped as repaired.
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                      FROM pg_constraint
                     WHERE conrelid = '{table_name}'::regclass
                       AND conname = '{current_name}'
                ) AND EXISTS (
                    SELECT 1
                      FROM pg_constraint
                     WHERE conrelid = '{table_name}'::regclass
                       AND conname = '{target_name}'
                ) THEN
                    RAISE EXCEPTION
                        'schema drift repair found both % and % on {table_name}',
                        '{current_name}', '{target_name}';
                ELSIF EXISTS (
                    SELECT 1
                      FROM pg_constraint
                     WHERE conrelid = '{table_name}'::regclass
                       AND conname = '{current_name}'
                ) THEN
                    ALTER TABLE {table_name}
                        RENAME CONSTRAINT {current_name} TO {target_name};
                ELSIF NOT EXISTS (
                    SELECT 1
                      FROM pg_constraint
                     WHERE conrelid = '{table_name}'::regclass
                       AND conname = '{target_name}'
                ) THEN
                    RAISE EXCEPTION
                        'schema drift repair could not find % or % on {table_name}',
                        '{current_name}', '{target_name}';
                END IF;
            END
            $$
            """
        )
    )


def _ensure_evidence_idempotency_hash_constraint() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                      FROM pg_constraint
                     WHERE conrelid = 'case_evidence'::regclass
                       AND conname = 'uq_case_evidence_tenant_case_idempotency_sha256'
                ) THEN
                    ALTER TABLE case_evidence
                        ADD CONSTRAINT uq_case_evidence_tenant_case_idempotency_sha256
                        UNIQUE (tenant_id, case_id, idempotency_key, sha256);
                END IF;
            END
            $$
            """
        )
    )


def upgrade() -> None:
    for table_name, current_name, target_name in _CHECK_CONSTRAINT_RENAMES:
        _rename_constraint(
            table_name=table_name,
            current_name=current_name,
            target_name=target_name,
        )
    _ensure_evidence_idempotency_hash_constraint()


def downgrade() -> None:
    # The evidence constraint belongs to the intended 0017 schema and is retained.
    for table_name, previous_name, current_name in reversed(_CHECK_CONSTRAINT_RENAMES):
        _rename_constraint(
            table_name=table_name,
            current_name=current_name,
            target_name=previous_name,
        )
