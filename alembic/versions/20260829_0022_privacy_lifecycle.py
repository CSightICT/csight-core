"""Enforce fail-closed sensitive payload and Evidence lifecycle operations.

Revision ID: 20260829_0022_privacy_lifecycle
Revises: 20260829_0021_failure_recovery
Create Date: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260829_0022_privacy_lifecycle"
down_revision: str | None = "20260829_0021_failure_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TOMBSTONE = "[PURGED_BY_RETENTION]"


def upgrade() -> None:
    # Stop before installing the no-fallback read contract when the expand
    # migration was incomplete or dual writes have drifted. This preflight is
    # intentionally non-destructive and names no payload values.
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM cases AS c
                    LEFT JOIN case_sensitive_payloads AS p
                      ON p.tenant_id = c.tenant_id AND p.case_id = c.id
                    WHERE p.id IS NULL
                ) THEN
                    RAISE EXCEPTION
                      'privacy lifecycle preflight failed: missing sensitive payload rows';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM cases AS c
                    JOIN case_sensitive_payloads AS p
                      ON p.tenant_id = c.tenant_id AND p.case_id = c.id
                    WHERE p.purged_at IS NULL
                      AND c.customer_message IS DISTINCT FROM p.customer_message
                ) THEN
                    RAISE EXCEPTION
                      'privacy lifecycle preflight failed: dual-write parity mismatch';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM cases AS c
                    JOIN case_sensitive_payloads AS p
                      ON p.tenant_id = c.tenant_id AND p.case_id = c.id
                    WHERE p.purged_at IS NOT NULL
                      AND c.customer_message IS DISTINCT FROM '[PURGED_BY_RETENTION]'
                ) THEN
                    RAISE EXCEPTION
                      'privacy lifecycle preflight failed: legacy content remains after purge';
                END IF;
            END
            $$;
            """
        )
    )

    op.add_column(
        "case_sensitive_payloads",
        sa.Column("legacy_redacted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE case_sensitive_payloads
            SET legacy_redacted_at = purged_at
            WHERE purged_at IS NOT NULL
            """
        )
    )
    op.drop_constraint(
        op.f("ck_case_sensitive_payloads_purge_state_consistent"),
        "case_sensitive_payloads",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_case_sensitive_payloads_purge_state_consistent"),
        "case_sensitive_payloads",
        "(purged_at IS NULL AND customer_message IS NOT NULL "
        "AND length(btrim(customer_message)) > 0 AND legacy_redacted_at IS NULL) OR "
        "(purged_at IS NOT NULL AND customer_message IS NULL "
        "AND legacy_redacted_at = purged_at)",
    )

    op.add_column(
        "data_lifecycle_events",
        sa.Column("operation_key", sa.String(255), nullable=True),
    )
    op.drop_constraint(
        op.f("ck_data_lifecycle_events_event_type_allowed"),
        "data_lifecycle_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_data_lifecycle_events_event_type_allowed"),
        "data_lifecycle_events",
        "event_type IN ('SENSITIVE_PAYLOAD_CREATED', 'SENSITIVE_PAYLOAD_MIGRATED', "
        "'SENSITIVE_PAYLOAD_PURGED', 'EVIDENCE_RECONCILED', "
        "'EVIDENCE_PURGE_REQUESTED', 'EVIDENCE_PURGED')",
    )
    op.create_check_constraint(
        op.f("ck_data_lifecycle_events_operation_key_valid"),
        "data_lifecycle_events",
        "operation_key IS NULL OR "
        "(length(btrim(operation_key)) > 0 AND length(operation_key) <= 255)",
    )
    op.create_index(
        "uq_data_lifecycle_events_tenant_operation_key",
        "data_lifecycle_events",
        ["tenant_id", "operation_key"],
        unique=True,
        postgresql_where=sa.text("operation_key IS NOT NULL"),
    )

    # The migration/owner connection remains available for controlled test and
    # disaster-recovery maintenance. Runtime roles can only append/read these
    # records, so normal API/Worker paths cannot rewrite lifecycle history.
    op.execute(
        "REVOKE UPDATE, DELETE ON data_lifecycle_events FROM csight_api_role, csight_worker_role"
    )
    _create_deferred_contract_triggers()


def _create_deferred_contract_triggers() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION csight_assert_sensitive_payload_contract(
                target_tenant_id uuid,
                target_case_id uuid
            ) RETURNS void
            LANGUAGE plpgsql
            AS $$
            DECLARE
                legacy_message text;
                restricted_message text;
                payload_purged_at timestamptz;
                payload_legacy_redacted_at timestamptz;
                payload_found boolean;
            BEGIN
                SELECT c.customer_message,
                       p.customer_message,
                       p.purged_at,
                       p.legacy_redacted_at,
                       p.id IS NOT NULL
                  INTO legacy_message,
                       restricted_message,
                       payload_purged_at,
                       payload_legacy_redacted_at,
                       payload_found
                  FROM cases AS c
                  LEFT JOIN case_sensitive_payloads AS p
                    ON p.tenant_id = c.tenant_id AND p.case_id = c.id
                 WHERE c.tenant_id = target_tenant_id AND c.id = target_case_id;

                IF NOT FOUND THEN
                    RETURN;
                END IF;
                IF NOT payload_found THEN
                    RAISE EXCEPTION
                      'sensitive payload contract violation: payload row missing';
                END IF;
                IF payload_purged_at IS NULL THEN
                    IF restricted_message IS NULL
                       OR legacy_message IS DISTINCT FROM restricted_message THEN
                        RAISE EXCEPTION
                          'sensitive payload contract violation: dual-write mismatch';
                    END IF;
                ELSE
                    IF restricted_message IS NOT NULL
                       OR payload_legacy_redacted_at IS DISTINCT FROM payload_purged_at
                       OR legacy_message IS DISTINCT FROM '{_TOMBSTONE}' THEN
                        RAISE EXCEPTION
                          'sensitive payload contract violation: purge tombstone mismatch';
                    END IF;
                END IF;
            END
            $$;

            CREATE FUNCTION csight_check_sensitive_payload_from_case()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                PERFORM csight_assert_sensitive_payload_contract(NEW.tenant_id, NEW.id);
                RETURN NEW;
            END
            $$;

            CREATE FUNCTION csight_check_sensitive_payload_from_payload()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    PERFORM csight_assert_sensitive_payload_contract(
                        OLD.tenant_id,
                        OLD.case_id
                    );
                    RETURN OLD;
                END IF;
                PERFORM csight_assert_sensitive_payload_contract(
                    NEW.tenant_id,
                    NEW.case_id
                );
                RETURN NEW;
            END
            $$;

            CREATE CONSTRAINT TRIGGER trg_cases_sensitive_payload_contract
            AFTER INSERT OR UPDATE OF customer_message ON cases
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION csight_check_sensitive_payload_from_case();

            CREATE CONSTRAINT TRIGGER trg_sensitive_payload_contract
            AFTER INSERT OR UPDATE OR DELETE ON case_sensitive_payloads
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION csight_check_sensitive_payload_from_payload();
            """
        )
    )


def downgrade() -> None:
    # A completed purge intentionally cannot be reversed into raw customer prose.
    # Refuse a downgrade that would silently weaken its audit contract.
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM case_sensitive_payloads WHERE purged_at IS NOT NULL
                ) THEN
                    RAISE EXCEPTION
                      'privacy lifecycle downgrade blocked: purged payloads cannot be restored';
                END IF;
            END
            $$;
            """
        )
    )
    op.execute("DROP TRIGGER trg_sensitive_payload_contract ON case_sensitive_payloads")
    op.execute("DROP TRIGGER trg_cases_sensitive_payload_contract ON cases")
    op.execute("DROP FUNCTION csight_check_sensitive_payload_from_payload()")
    op.execute("DROP FUNCTION csight_check_sensitive_payload_from_case()")
    op.execute("DROP FUNCTION csight_assert_sensitive_payload_contract(uuid, uuid)")
    op.execute(
        "GRANT UPDATE, DELETE ON data_lifecycle_events TO csight_api_role, csight_worker_role"
    )

    op.drop_index(
        "uq_data_lifecycle_events_tenant_operation_key",
        table_name="data_lifecycle_events",
    )
    op.drop_constraint(
        op.f("ck_data_lifecycle_events_operation_key_valid"),
        "data_lifecycle_events",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_data_lifecycle_events_event_type_allowed"),
        "data_lifecycle_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_data_lifecycle_events_event_type_allowed"),
        "data_lifecycle_events",
        "event_type IN ('SENSITIVE_PAYLOAD_CREATED', 'SENSITIVE_PAYLOAD_MIGRATED', "
        "'SENSITIVE_PAYLOAD_PURGED', 'EVIDENCE_RECONCILED', 'EVIDENCE_PURGED')",
    )
    op.drop_column("data_lifecycle_events", "operation_key")

    op.drop_constraint(
        op.f("ck_case_sensitive_payloads_purge_state_consistent"),
        "case_sensitive_payloads",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_case_sensitive_payloads_purge_state_consistent"),
        "case_sensitive_payloads",
        "(purged_at IS NULL AND customer_message IS NOT NULL "
        "AND length(btrim(customer_message)) > 0) OR "
        "(purged_at IS NOT NULL AND customer_message IS NULL)",
    )
    op.drop_column("case_sensitive_payloads", "legacy_redacted_at")
