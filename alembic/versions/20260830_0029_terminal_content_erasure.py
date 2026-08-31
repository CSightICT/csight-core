"""Redact terminal customer-derived content with a deferred database contract.

Revision ID: 20260830_0029_terminal_content_erasure
Revises: 20260830_0028_signed_model_activation
Create Date: 2026-08-30
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa

from alembic import context, op

revision: str = "20260830_0029_terminal_content_erasure"
down_revision: str | None = "20260830_0028_signed_model_activation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TOMBSTONE = "[PURGED_BY_RETENTION]"
_POLICY_VERSION = "terminal-content-redaction/1.0.0"


def upgrade() -> None:
    op.add_column(
        "case_sensitive_payloads",
        sa.Column("terminal_content_purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    if context.is_offline_mode():
        op.execute("-- terminal content hash backfill executes only in online migration mode")
    else:
        _backfill_existing_purged_cases(op.get_bind())
    op.execute("SET CONSTRAINTS ALL IMMEDIATE")

    op.drop_constraint(
        op.f("ck_case_sensitive_payloads_purge_state_consistent"),
        "case_sensitive_payloads",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_case_sensitive_payloads_purge_state_consistent"),
        "case_sensitive_payloads",
        "(purged_at IS NULL AND customer_message IS NOT NULL "
        "AND length(btrim(customer_message)) > 0 AND legacy_redacted_at IS NULL "
        "AND analysis_text_purged_at IS NULL AND terminal_content_purged_at IS NULL) OR "
        "(purged_at IS NOT NULL AND customer_message IS NULL "
        "AND legacy_redacted_at = purged_at AND analysis_text_purged_at = purged_at "
        "AND terminal_content_purged_at = purged_at)",
    )
    _create_deferred_terminal_contract()


def _backfill_existing_purged_cases(connection: sa.Connection) -> None:
    cases = tuple(
        connection.execute(
            sa.text(
                "SELECT tenant_id, case_id, purged_at FROM case_sensitive_payloads "
                "WHERE purged_at IS NOT NULL ORDER BY tenant_id, case_id"
            )
        ).mappings()
    )
    for item in cases:
        tenant_id = item["tenant_id"]
        case_id = item["case_id"]
        purged_at = item["purged_at"]
        decision_hashes = _backfill_decisions(connection, tenant_id=tenant_id, case_id=case_id)
        connection.execute(
            sa.text(
                "UPDATE human_review_actions AS action SET rationale = CASE "
                "WHEN action.rationale IS NULL THEN NULL ELSE :tombstone END, "
                "action_payload = '{}'::jsonb FROM human_review_tasks AS task "
                "WHERE task.tenant_id = action.tenant_id AND task.id = action.review_task_id "
                "AND task.tenant_id = :tenant_id AND task.case_id = :case_id"
            ),
            {"tombstone": _TOMBSTONE, "tenant_id": tenant_id, "case_id": case_id},
        )
        _backfill_reports(
            connection,
            tenant_id=tenant_id,
            case_id=case_id,
            purged_at=purged_at,
            decision_hashes=decision_hashes,
        )
        _backfill_communications(connection, tenant_id=tenant_id, case_id=case_id)
        parameters = {"tombstone": _TOMBSTONE, "tenant_id": tenant_id, "case_id": case_id}
        connection.execute(
            sa.text(
                "UPDATE cases SET attributes = '{}'::jsonb WHERE tenant_id = :tenant_id "
                "AND id = :case_id"
            ),
            parameters,
        )
        connection.execute(
            sa.text(
                "UPDATE case_resolutions SET failure_message = :tombstone "
                "WHERE tenant_id = :tenant_id AND case_id = :case_id "
                "AND failure_message IS NOT NULL"
            ),
            parameters,
        )
        connection.execute(
            sa.text(
                "UPDATE case_sensitive_payloads SET terminal_content_purged_at = purged_at "
                "WHERE tenant_id = :tenant_id AND case_id = :case_id"
            ),
            parameters,
        )


def _backfill_decisions(
    connection: sa.Connection,
    *,
    tenant_id: Any,
    case_id: Any,
) -> dict[str, str]:
    rows = tuple(
        connection.execute(
            sa.text(
                "SELECT decision.* FROM human_review_decisions AS decision "
                "JOIN human_review_tasks AS task ON task.tenant_id = decision.tenant_id "
                "AND task.id = decision.review_task_id WHERE task.tenant_id = :tenant_id "
                "AND task.case_id = :case_id ORDER BY decision.id"
            ),
            {"tenant_id": tenant_id, "case_id": case_id},
        ).mappings()
    )
    hashes: dict[str, str] = {}
    for row in rows:
        basis_rows = tuple(
            connection.execute(
                sa.text(
                    "SELECT * FROM human_review_decision_basis WHERE tenant_id = :tenant_id "
                    "AND human_review_decision_id = :decision_id "
                    "ORDER BY basis_type, reference_id, id"
                ),
                {"tenant_id": tenant_id, "decision_id": row["id"]},
            ).mappings()
        )
        basis = [
            {
                "id": str(item["id"]),
                "tenant_id": str(item["tenant_id"]),
                "human_review_decision_id": str(item["human_review_decision_id"]),
                "type": item["basis_type"],
                "reference_id": item["reference_id"],
                "policy_rule_result_id": _optional_string(item["policy_rule_result_id"]),
                "policy_clause_row_id": _optional_string(item["policy_clause_row_id"]),
                "citation_item_id": _optional_string(item["citation_item_id"]),
                "case_evidence_id": _optional_string(item["case_evidence_id"]),
                "analysis_result_id": _optional_string(item["analysis_result_id"]),
            }
            for item in basis_rows
        ]
        payload = {
            "id": str(row["id"]),
            "tenant_id": str(row["tenant_id"]),
            "review_task_id": str(row["review_task_id"]),
            "decision_type": row["decision_type"],
            "reason_codes": sorted(str(value) for value in row["reason_codes"]),
            "rationale": _TOMBSTONE,
            "basis": basis,
            "outcome_relation": row["outcome_relation"],
            "outcome_relation_rule_version": row["outcome_relation_rule_version"],
            "decided_by": str(row["decided_by"]),
            "decided_at": _decision_time(row["decided_at"]),
            "decision_schema_version": row["decision_schema_version"],
        }
        content_hash = _hash(payload)
        connection.execute(
            sa.text(
                "UPDATE human_review_decisions SET rationale = :tombstone, "
                "content_hash = :content_hash WHERE tenant_id = :tenant_id AND id = :id"
            ),
            {
                "tombstone": _TOMBSTONE,
                "content_hash": content_hash,
                "tenant_id": tenant_id,
                "id": row["id"],
            },
        )
        hashes[str(row["id"])] = content_hash
    return hashes


def _backfill_reports(
    connection: sa.Connection,
    *,
    tenant_id: Any,
    case_id: Any,
    purged_at: datetime,
    decision_hashes: Mapping[str, str],
) -> None:
    reports = tuple(
        connection.execute(
            sa.text(
                "SELECT * FROM review_reports WHERE tenant_id = :tenant_id "
                "AND case_id = :case_id ORDER BY id"
            ),
            {"tenant_id": tenant_id, "case_id": case_id},
        ).mappings()
    )
    for row in reports:
        at = _iso(purged_at)
        case_snapshot = _allowlist(
            row["case_snapshot"],
            (
                "case_id",
                "status",
                "product_ref",
                "requested_action",
                "created_at",
                "source_integrity",
            ),
        )
        case_snapshot["privacy_redacted_at"] = at
        review_snapshot = dict(row["review_snapshot"])
        if "rationale" in review_snapshot:
            review_snapshot["rationale"] = _TOMBSTONE
        decision_id = review_snapshot.get("decision_id")
        if isinstance(decision_id, str) and decision_id in decision_hashes:
            review_snapshot["decision_hash"] = decision_hashes[decision_id]
        review_snapshot["privacy_redacted_at"] = at
        resolution_snapshot = dict(row["resolution_snapshot"])
        if "terminal_event_payload" in resolution_snapshot:
            resolution_snapshot["terminal_event_payload"] = {"privacy_redacted": True}
        resolution_snapshot["privacy_redacted_at"] = at
        data_scope = dict(row["data_scope"])
        data_scope.update(
            {
                "commerce_context_included": False,
                "direct_contact_values_included": False,
                "privacy_redacted": True,
                "privacy_redaction_policy_version": _POLICY_VERSION,
                "retained_transaction_fields": ["product_ref"],
            }
        )
        dry_run_snapshot = _redact_dry_run(row["dry_run_snapshot"], purged_at=purged_at)
        payload = {
            "schema_version": row["schema_version"],
            "report_id": str(row["id"]),
            "tenant_id": str(row["tenant_id"]),
            "case_id": str(row["case_id"]),
            "resolution_id": str(row["resolution_id"]),
            "resolution_version": row["resolution_version"],
            "terminal_event_id": str(row["terminal_event_id"]),
            "case_snapshot": case_snapshot,
            "analysis_snapshot": row["analysis_snapshot"],
            "policy_snapshot": row["policy_snapshot"],
            "review_snapshot": review_snapshot,
            "resolution_snapshot": resolution_snapshot,
            "dry_run_snapshot": dry_run_snapshot,
            "qualification_snapshot": row["qualification_snapshot"],
            "data_scope": data_scope,
            "generated_at": _iso(row["generated_at"]),
        }
        connection.execute(
            sa.text(
                "UPDATE review_reports SET case_snapshot = CAST(:case_snapshot AS jsonb), "
                "review_snapshot = CAST(:review_snapshot AS jsonb), "
                "resolution_snapshot = CAST(:resolution_snapshot AS jsonb), "
                "dry_run_snapshot = CAST(:dry_run_snapshot AS jsonb), "
                "data_scope = CAST(:data_scope AS jsonb), content_hash = :content_hash "
                "WHERE tenant_id = :tenant_id AND id = :id"
            ),
            {
                "case_snapshot": _json(case_snapshot),
                "review_snapshot": _json(review_snapshot),
                "resolution_snapshot": _json(resolution_snapshot),
                "dry_run_snapshot": _json(dry_run_snapshot),
                "data_scope": _json(data_scope),
                "content_hash": _hash(payload),
                "tenant_id": tenant_id,
                "id": row["id"],
            },
        )


def _backfill_communications(
    connection: sa.Connection,
    *,
    tenant_id: Any,
    case_id: Any,
) -> None:
    rows = tuple(
        connection.execute(
            sa.text(
                "SELECT * FROM customer_communication_simulations "
                "WHERE tenant_id = :tenant_id AND case_id = :case_id ORDER BY id"
            ),
            {"tenant_id": tenant_id, "case_id": case_id},
        ).mappings()
    )
    for row in rows:
        payload = {
            "schema_version": row["schema_version"],
            "communication_id": str(row["id"]),
            "tenant_id": str(row["tenant_id"]),
            "case_id": str(row["case_id"]),
            "review_report_id": str(row["review_report_id"]),
            "channel": row["channel"],
            "template_name": row["template_name"],
            "template_version": row["template_version"],
            "recipient_label": _TOMBSTONE,
            "subject": _TOMBSTONE,
            "body": _TOMBSTONE,
            "delivery_status": row["delivery_status"],
            "side_effects_performed": row["side_effects_performed"],
            "created_by": str(row["created_by"]),
            "created_at": _iso(row["created_at"]),
        }
        connection.execute(
            sa.text(
                "UPDATE customer_communication_simulations SET recipient_label = :tombstone, "
                "subject = :tombstone, body = :tombstone, content_hash = :content_hash "
                "WHERE tenant_id = :tenant_id AND id = :id"
            ),
            {
                "tombstone": _TOMBSTONE,
                "content_hash": _hash(payload),
                "tenant_id": tenant_id,
                "id": row["id"],
            },
        )


def _create_deferred_terminal_contract() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION csight_assert_terminal_content_erasure(
                target_tenant_id uuid,
                target_case_id uuid
            ) RETURNS void
            LANGUAGE plpgsql
            AS $$
            DECLARE payload_purged_at timestamptz; terminal_purged_at timestamptz;
            BEGIN
                SELECT purged_at, terminal_content_purged_at
                  INTO payload_purged_at, terminal_purged_at
                  FROM case_sensitive_payloads
                 WHERE tenant_id = target_tenant_id AND case_id = target_case_id;
                IF NOT FOUND OR payload_purged_at IS NULL THEN
                    IF terminal_purged_at IS NOT NULL THEN
                        RAISE EXCEPTION 'terminal erasure contract violation: active payload marked purged';
                    END IF;
                    RETURN;
                END IF;
                IF terminal_purged_at IS DISTINCT FROM payload_purged_at THEN
                    RAISE EXCEPTION 'terminal erasure contract violation: purge timestamp mismatch';
                END IF;
                IF EXISTS (
                    SELECT 1 FROM cases WHERE tenant_id = target_tenant_id
                     AND id = target_case_id AND attributes <> '{{}}'::jsonb
                ) OR EXISTS (
                    SELECT 1 FROM human_review_actions AS action
                    JOIN human_review_tasks AS task ON task.tenant_id = action.tenant_id
                     AND task.id = action.review_task_id
                    WHERE task.tenant_id = target_tenant_id AND task.case_id = target_case_id
                     AND ((action.rationale IS NOT NULL AND action.rationale <> '{_TOMBSTONE}')
                          OR action.action_payload <> '{{}}'::jsonb)
                ) OR EXISTS (
                    SELECT 1 FROM human_review_decisions AS decision
                    JOIN human_review_tasks AS task ON task.tenant_id = decision.tenant_id
                     AND task.id = decision.review_task_id
                    WHERE task.tenant_id = target_tenant_id AND task.case_id = target_case_id
                     AND decision.rationale <> '{_TOMBSTONE}'
                ) OR EXISTS (
                    SELECT 1 FROM review_reports WHERE tenant_id = target_tenant_id
                     AND case_id = target_case_id
                     AND (case_snapshot ? 'synthetic_commerce_context'
                          OR case_snapshot ? 'order_ref'
                          OR NOT (case_snapshot ? 'privacy_redacted_at')
                          OR (review_snapshot ? 'rationale'
                              AND review_snapshot->>'rationale' <> '{_TOMBSTONE}')
                          OR NOT (review_snapshot ? 'privacy_redacted_at')
                          OR NOT (resolution_snapshot ? 'privacy_redacted_at')
                          OR dry_run_snapshot->>'privacy_redacted' <> 'true'
                          OR data_scope->>'privacy_redacted' <> 'true'
                          OR data_scope->>'privacy_redaction_policy_version' <> '{_POLICY_VERSION}')
                ) OR EXISTS (
                    SELECT 1 FROM customer_communication_simulations
                    WHERE tenant_id = target_tenant_id AND case_id = target_case_id
                     AND (recipient_label <> '{_TOMBSTONE}' OR subject <> '{_TOMBSTONE}'
                          OR body <> '{_TOMBSTONE}')
                ) OR EXISTS (
                    SELECT 1 FROM case_resolutions WHERE tenant_id = target_tenant_id
                     AND case_id = target_case_id AND failure_message IS NOT NULL
                     AND failure_message <> '{_TOMBSTONE}'
                ) THEN
                    RAISE EXCEPTION
                      'terminal erasure contract violation: customer-derived terminal content remains';
                END IF;
            END
            $$;

            CREATE FUNCTION csight_check_terminal_erasure_from_case()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM csight_assert_terminal_content_erasure(NEW.tenant_id, NEW.id);
                RETURN NEW;
            END $$;

            CREATE FUNCTION csight_check_terminal_erasure_from_payload()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM csight_assert_terminal_content_erasure(NEW.tenant_id, NEW.case_id);
                RETURN NEW;
            END $$;

            CREATE FUNCTION csight_check_terminal_erasure_from_direct_case()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM csight_assert_terminal_content_erasure(NEW.tenant_id, NEW.case_id);
                RETURN NEW;
            END $$;

            CREATE FUNCTION csight_check_terminal_erasure_from_review()
            RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE target_case_id uuid;
            BEGIN
                SELECT case_id INTO target_case_id FROM human_review_tasks
                 WHERE tenant_id = NEW.tenant_id AND id = NEW.review_task_id;
                IF target_case_id IS NOT NULL THEN
                    PERFORM csight_assert_terminal_content_erasure(NEW.tenant_id, target_case_id);
                END IF;
                RETURN NEW;
            END $$;

            CREATE CONSTRAINT TRIGGER trg_payload_terminal_content_erasure
            AFTER INSERT OR UPDATE OF purged_at, terminal_content_purged_at
            ON case_sensitive_payloads DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_terminal_erasure_from_payload();
            CREATE CONSTRAINT TRIGGER trg_case_terminal_content_erasure
            AFTER INSERT OR UPDATE OF attributes ON cases DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_terminal_erasure_from_case();
            CREATE CONSTRAINT TRIGGER trg_action_terminal_content_erasure
            AFTER INSERT OR UPDATE OF rationale, action_payload ON human_review_actions
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            EXECUTE FUNCTION csight_check_terminal_erasure_from_review();
            CREATE CONSTRAINT TRIGGER trg_decision_terminal_content_erasure
            AFTER INSERT OR UPDATE OF rationale, content_hash ON human_review_decisions
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            EXECUTE FUNCTION csight_check_terminal_erasure_from_review();
            CREATE CONSTRAINT TRIGGER trg_report_terminal_content_erasure
            AFTER INSERT OR UPDATE ON review_reports DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_terminal_erasure_from_direct_case();
            CREATE CONSTRAINT TRIGGER trg_communication_terminal_content_erasure
            AFTER INSERT OR UPDATE ON customer_communication_simulations DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_terminal_erasure_from_direct_case();
            CREATE CONSTRAINT TRIGGER trg_resolution_terminal_content_erasure
            AFTER INSERT OR UPDATE OF failure_message ON case_resolutions DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_terminal_erasure_from_direct_case();
            """
        )
    )


def _redact_dry_run(value: Mapping[str, Any], *, purged_at: datetime) -> dict[str, Any]:
    redacted: dict[str, Any] = {
        "privacy_redacted": True,
        "privacy_redacted_at": _iso(purged_at),
    }
    intent = value.get("intent")
    result = value.get("result")
    redacted["intent"] = (
        _allowlist(
            intent,
            (
                "action_type",
                "amount",
                "currency",
                "intent_id",
                "intent_schema_version",
                "mapping_name",
                "mapping_version",
                "mode",
                "product_ref",
                "quantity",
            ),
        )
        if isinstance(intent, Mapping)
        else None
    )
    redacted["result"] = (
        _allowlist(
            result,
            (
                "failure_code",
                "mode",
                "outcome",
                "result_id",
                "result_schema_version",
                "side_effects_performed",
                "simulation_attempt_id",
            ),
        )
        if isinstance(result, Mapping)
        else None
    )
    return redacted


def _allowlist(value: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: value[key] for key in keys if key in value}


def _hash(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _json(value: object) -> str:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("terminal redaction timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decision_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("decision timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _optional_string(value: object | None) -> str | None:
    return None if value is None else str(value)


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$ BEGIN
                IF EXISTS (
                    SELECT 1 FROM case_sensitive_payloads
                    WHERE terminal_content_purged_at IS NOT NULL
                ) THEN
                    RAISE EXCEPTION
                      'terminal content erasure downgrade blocked: redacted content cannot be restored';
                END IF;
            END $$;
            """
        )
    )
    for table_name, trigger_name in (
        ("case_resolutions", "trg_resolution_terminal_content_erasure"),
        ("customer_communication_simulations", "trg_communication_terminal_content_erasure"),
        ("review_reports", "trg_report_terminal_content_erasure"),
        ("human_review_decisions", "trg_decision_terminal_content_erasure"),
        ("human_review_actions", "trg_action_terminal_content_erasure"),
        ("cases", "trg_case_terminal_content_erasure"),
        ("case_sensitive_payloads", "trg_payload_terminal_content_erasure"),
    ):
        op.execute(f"DROP TRIGGER {trigger_name} ON {table_name}")
    op.execute("DROP FUNCTION csight_check_terminal_erasure_from_review()")
    op.execute("DROP FUNCTION csight_check_terminal_erasure_from_direct_case()")
    op.execute("DROP FUNCTION csight_check_terminal_erasure_from_payload()")
    op.execute("DROP FUNCTION csight_check_terminal_erasure_from_case()")
    op.execute("DROP FUNCTION csight_assert_terminal_content_erasure(uuid, uuid)")
    op.drop_constraint(
        op.f("ck_case_sensitive_payloads_purge_state_consistent"),
        "case_sensitive_payloads",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_case_sensitive_payloads_purge_state_consistent"),
        "case_sensitive_payloads",
        "(purged_at IS NULL AND customer_message IS NOT NULL "
        "AND length(btrim(customer_message)) > 0 AND legacy_redacted_at IS NULL "
        "AND analysis_text_purged_at IS NULL) OR "
        "(purged_at IS NOT NULL AND customer_message IS NULL "
        "AND legacy_redacted_at = purged_at AND analysis_text_purged_at = purged_at)",
    )
    op.drop_column("case_sensitive_payloads", "terminal_content_purged_at")
