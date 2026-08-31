"""Redact customer-derived analysis text with a deferred database contract.

Revision ID: 20260830_0027_analysis_text_erasure
Revises: 20260830_0026_case_assignment_ownership
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0027_analysis_text_erasure"
down_revision: str | None = "20260830_0026_case_assignment_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TOMBSTONE = "[PURGED_BY_RETENTION]"
_ZERO_GROUNDING_METRICS = """{
  "statement_count": 0,
  "cited_statement_count": 0,
  "citation_reference_count": 0,
  "unique_citation_count": 0,
  "citation_coverage_rate": 0.0,
  "citation_id_valid_rate": 0.0,
  "citation_allowlist_violation_count": 0,
  "unknown_citation_count": 0,
  "duplicate_citation_count": 0,
  "forbidden_decision_count": 0
}"""


def upgrade() -> None:
    op.add_column(
        "case_sensitive_payloads",
        sa.Column("analysis_text_purged_at", sa.DateTime(timezone=True), nullable=True),
    )

    # A previously completed raw-text purge is strengthened in place.  The
    # migration revision is the audit boundary; no customer content is copied
    # into a migration log or lifecycle event.
    _redact_existing_purged_cases()
    # Updating the payload schedules ADR-0108's deferred parity trigger.  Drain
    # that verified event before altering the same table's check constraint;
    # PostgreSQL deliberately refuses DDL while deferred events are pending.
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
        "AND analysis_text_purged_at IS NULL) OR "
        "(purged_at IS NOT NULL AND customer_message IS NULL "
        "AND legacy_redacted_at = purged_at AND analysis_text_purged_at = purged_at)",
    )
    _create_deferred_erasure_contract()


def _redact_existing_purged_cases() -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE llm_extraction_results AS result
               SET claims = '[]'::jsonb,
                   missing_information = '[]'::jsonb,
                   summary = '{_TOMBSTONE}'
              FROM analysis_runs AS run
              JOIN case_sensitive_payloads AS payload
                ON payload.tenant_id = run.tenant_id
               AND payload.case_id = run.case_id
             WHERE result.tenant_id = run.tenant_id
               AND result.analysis_run_id = run.id
               AND payload.purged_at IS NOT NULL;

            UPDATE llm_extraction_results_v2 AS result
               SET claims = '[]'::jsonb,
                   requested_actions = '[]'::jsonb,
                   text_ambiguities = '[]'::jsonb,
                   summary = '{_TOMBSTONE}',
                   system_missing_information = '[]'::jsonb
              FROM analysis_runs AS run
              JOIN case_sensitive_payloads AS payload
                ON payload.tenant_id = run.tenant_id
               AND payload.case_id = run.case_id
             WHERE result.tenant_id = run.tenant_id
               AND result.analysis_run_id = run.id
               AND payload.purged_at IS NOT NULL;

            UPDATE policy_retrieval_run_queries AS query
               SET query_text = '{_TOMBSTONE}'
              FROM policy_retrieval_runs AS run
              JOIN case_sensitive_payloads AS payload
                ON payload.tenant_id = run.tenant_id
               AND payload.case_id = run.case_id
             WHERE query.tenant_id = run.tenant_id
               AND query.retrieval_run_id = run.id
               AND query.query_source = 'GENERATED'
               AND payload.purged_at IS NOT NULL;

            UPDATE grounded_explanation_results AS result
               SET policy_statements = '[]'::jsonb,
                   unresolved_conditions = '[]'::jsonb,
                   validation_metrics = '{_ZERO_GROUNDING_METRICS}'::jsonb
              FROM grounded_explanation_runs AS run
              JOIN case_sensitive_payloads AS payload
                ON payload.tenant_id = run.tenant_id
               AND payload.case_id = run.case_id
             WHERE result.tenant_id = run.tenant_id
               AND result.grounded_explanation_run_id = run.id
               AND payload.purged_at IS NOT NULL;

            UPDATE analysis_runs AS run
               SET failure_message = '{_TOMBSTONE}'
              FROM case_sensitive_payloads AS payload
             WHERE run.tenant_id = payload.tenant_id
               AND run.case_id = payload.case_id
               AND payload.purged_at IS NOT NULL
               AND run.failure_message IS NOT NULL;

            UPDATE analysis_stage_runs AS stage
               SET failure_message = '{_TOMBSTONE}'
              FROM analysis_runs AS run
              JOIN case_sensitive_payloads AS payload
                ON payload.tenant_id = run.tenant_id
               AND payload.case_id = run.case_id
             WHERE stage.tenant_id = run.tenant_id
               AND stage.analysis_run_id = run.id
               AND payload.purged_at IS NOT NULL
               AND stage.failure_message IS NOT NULL;

            UPDATE analysis_stage_attempts AS attempt
               SET failure_message = '{_TOMBSTONE}'
              FROM analysis_runs AS run
              JOIN case_sensitive_payloads AS payload
                ON payload.tenant_id = run.tenant_id
               AND payload.case_id = run.case_id
             WHERE attempt.tenant_id = run.tenant_id
               AND attempt.analysis_run_id = run.id
               AND payload.purged_at IS NOT NULL
               AND attempt.failure_message IS NOT NULL;

            UPDATE policy_retrieval_runs AS run
               SET failure_message = '{_TOMBSTONE}'
              FROM case_sensitive_payloads AS payload
             WHERE run.tenant_id = payload.tenant_id
               AND run.case_id = payload.case_id
               AND payload.purged_at IS NOT NULL
               AND run.failure_message IS NOT NULL;

            UPDATE grounded_explanation_runs AS run
               SET failure_message = '{_TOMBSTONE}'
              FROM case_sensitive_payloads AS payload
             WHERE run.tenant_id = payload.tenant_id
               AND run.case_id = payload.case_id
               AND payload.purged_at IS NOT NULL
               AND run.failure_message IS NOT NULL;

            UPDATE case_sensitive_payloads
               SET analysis_text_purged_at = purged_at
             WHERE purged_at IS NOT NULL;
            """
        )
    )


def _create_deferred_erasure_contract() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION csight_assert_analysis_text_erasure(
                target_tenant_id uuid,
                target_case_id uuid
            ) RETURNS void
            LANGUAGE plpgsql
            AS $$
            DECLARE
                payload_purged_at timestamptz;
                analysis_purged_at timestamptz;
            BEGIN
                SELECT purged_at, analysis_text_purged_at
                  INTO payload_purged_at, analysis_purged_at
                  FROM case_sensitive_payloads
                 WHERE tenant_id = target_tenant_id AND case_id = target_case_id;

                IF NOT FOUND OR payload_purged_at IS NULL THEN
                    IF analysis_purged_at IS NOT NULL THEN
                        RAISE EXCEPTION
                          'analysis text erasure contract violation: active payload marked purged';
                    END IF;
                    RETURN;
                END IF;
                IF analysis_purged_at IS DISTINCT FROM payload_purged_at THEN
                    RAISE EXCEPTION
                      'analysis text erasure contract violation: purge timestamp mismatch';
                END IF;
                IF EXISTS (
                    SELECT 1
                      FROM llm_extraction_results AS result
                      JOIN analysis_runs AS run
                        ON run.tenant_id = result.tenant_id
                       AND run.id = result.analysis_run_id
                     WHERE run.tenant_id = target_tenant_id
                       AND run.case_id = target_case_id
                       AND (result.claims <> '[]'::jsonb
                            OR result.missing_information <> '[]'::jsonb
                            OR result.summary <> '{_TOMBSTONE}')
                ) OR EXISTS (
                    SELECT 1
                      FROM llm_extraction_results_v2 AS result
                      JOIN analysis_runs AS run
                        ON run.tenant_id = result.tenant_id
                       AND run.id = result.analysis_run_id
                     WHERE run.tenant_id = target_tenant_id
                       AND run.case_id = target_case_id
                       AND (result.claims <> '[]'::jsonb
                            OR result.requested_actions <> '[]'::jsonb
                            OR result.text_ambiguities <> '[]'::jsonb
                            OR result.system_missing_information <> '[]'::jsonb
                            OR result.summary <> '{_TOMBSTONE}')
                ) OR EXISTS (
                    SELECT 1
                      FROM policy_retrieval_run_queries AS query
                      JOIN policy_retrieval_runs AS run
                        ON run.tenant_id = query.tenant_id
                       AND run.id = query.retrieval_run_id
                     WHERE run.tenant_id = target_tenant_id
                       AND run.case_id = target_case_id
                       AND query.query_source = 'GENERATED'
                       AND query.query_text <> '{_TOMBSTONE}'
                ) OR EXISTS (
                    SELECT 1
                      FROM grounded_explanation_results AS result
                      JOIN grounded_explanation_runs AS run
                        ON run.tenant_id = result.tenant_id
                       AND run.id = result.grounded_explanation_run_id
                     WHERE run.tenant_id = target_tenant_id
                       AND run.case_id = target_case_id
                       AND (result.policy_statements <> '[]'::jsonb
                            OR result.unresolved_conditions <> '[]'::jsonb)
                ) OR EXISTS (
                    SELECT 1
                      FROM analysis_runs AS run
                     WHERE run.tenant_id = target_tenant_id
                       AND run.case_id = target_case_id
                       AND run.failure_message IS NOT NULL
                       AND run.failure_message <> '{_TOMBSTONE}'
                ) OR EXISTS (
                    SELECT 1
                      FROM analysis_stage_runs AS stage
                      JOIN analysis_runs AS run
                        ON run.tenant_id = stage.tenant_id
                       AND run.id = stage.analysis_run_id
                     WHERE run.tenant_id = target_tenant_id
                       AND run.case_id = target_case_id
                       AND stage.failure_message IS NOT NULL
                       AND stage.failure_message <> '{_TOMBSTONE}'
                ) OR EXISTS (
                    SELECT 1
                      FROM analysis_stage_attempts AS attempt
                      JOIN analysis_runs AS run
                        ON run.tenant_id = attempt.tenant_id
                       AND run.id = attempt.analysis_run_id
                     WHERE run.tenant_id = target_tenant_id
                       AND run.case_id = target_case_id
                       AND attempt.failure_message IS NOT NULL
                       AND attempt.failure_message <> '{_TOMBSTONE}'
                ) OR EXISTS (
                    SELECT 1
                      FROM policy_retrieval_runs AS run
                     WHERE run.tenant_id = target_tenant_id
                       AND run.case_id = target_case_id
                       AND run.failure_message IS NOT NULL
                       AND run.failure_message <> '{_TOMBSTONE}'
                ) OR EXISTS (
                    SELECT 1
                      FROM grounded_explanation_runs AS run
                     WHERE run.tenant_id = target_tenant_id
                       AND run.case_id = target_case_id
                       AND run.failure_message IS NOT NULL
                       AND run.failure_message <> '{_TOMBSTONE}'
                ) THEN
                    RAISE EXCEPTION
                      'analysis text erasure contract violation: derived prose remains';
                END IF;
            END
            $$;

            CREATE FUNCTION csight_check_analysis_erasure_from_payload()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                PERFORM csight_assert_analysis_text_erasure(NEW.tenant_id, NEW.case_id);
                RETURN NEW;
            END
            $$;

            CREATE FUNCTION csight_check_analysis_erasure_from_result()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE target_case_id uuid;
            BEGIN
                SELECT case_id INTO target_case_id
                  FROM analysis_runs
                 WHERE tenant_id = NEW.tenant_id AND id = NEW.analysis_run_id;
                IF target_case_id IS NOT NULL THEN
                    PERFORM csight_assert_analysis_text_erasure(NEW.tenant_id, target_case_id);
                END IF;
                RETURN NEW;
            END
            $$;

            CREATE FUNCTION csight_check_analysis_erasure_from_run()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                PERFORM csight_assert_analysis_text_erasure(NEW.tenant_id, NEW.case_id);
                RETURN NEW;
            END
            $$;

            CREATE FUNCTION csight_check_analysis_erasure_from_stage()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE target_case_id uuid;
            BEGIN
                SELECT case_id INTO target_case_id
                  FROM analysis_runs
                 WHERE tenant_id = NEW.tenant_id AND id = NEW.analysis_run_id;
                IF target_case_id IS NOT NULL THEN
                    PERFORM csight_assert_analysis_text_erasure(NEW.tenant_id, target_case_id);
                END IF;
                RETURN NEW;
            END
            $$;

            CREATE FUNCTION csight_check_analysis_erasure_from_query()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE target_case_id uuid;
            BEGIN
                SELECT case_id INTO target_case_id
                  FROM policy_retrieval_runs
                 WHERE tenant_id = NEW.tenant_id AND id = NEW.retrieval_run_id;
                IF target_case_id IS NOT NULL THEN
                    PERFORM csight_assert_analysis_text_erasure(NEW.tenant_id, target_case_id);
                END IF;
                RETURN NEW;
            END
            $$;

            CREATE FUNCTION csight_check_analysis_erasure_from_grounding()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE target_case_id uuid;
            BEGIN
                SELECT case_id INTO target_case_id
                  FROM grounded_explanation_runs
                 WHERE tenant_id = NEW.tenant_id AND id = NEW.grounded_explanation_run_id;
                IF target_case_id IS NOT NULL THEN
                    PERFORM csight_assert_analysis_text_erasure(NEW.tenant_id, target_case_id);
                END IF;
                RETURN NEW;
            END
            $$;

            CREATE CONSTRAINT TRIGGER trg_payload_analysis_text_erasure
            AFTER INSERT OR UPDATE OF purged_at, analysis_text_purged_at
            ON case_sensitive_payloads
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_analysis_erasure_from_payload();

            CREATE CONSTRAINT TRIGGER trg_llm_v1_analysis_text_erasure
            AFTER INSERT OR UPDATE ON llm_extraction_results
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_analysis_erasure_from_result();

            CREATE CONSTRAINT TRIGGER trg_analysis_run_text_erasure
            AFTER INSERT OR UPDATE OF failure_message ON analysis_runs
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_analysis_erasure_from_run();

            CREATE CONSTRAINT TRIGGER trg_analysis_stage_text_erasure
            AFTER INSERT OR UPDATE OF failure_message ON analysis_stage_runs
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_analysis_erasure_from_stage();

            CREATE CONSTRAINT TRIGGER trg_analysis_attempt_text_erasure
            AFTER INSERT OR UPDATE OF failure_message ON analysis_stage_attempts
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_analysis_erasure_from_stage();

            CREATE CONSTRAINT TRIGGER trg_llm_v2_analysis_text_erasure
            AFTER INSERT OR UPDATE ON llm_extraction_results_v2
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_analysis_erasure_from_result();

            CREATE CONSTRAINT TRIGGER trg_query_analysis_text_erasure
            AFTER INSERT OR UPDATE ON policy_retrieval_run_queries
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_analysis_erasure_from_query();

            CREATE CONSTRAINT TRIGGER trg_grounding_analysis_text_erasure
            AFTER INSERT OR UPDATE ON grounded_explanation_results
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_analysis_erasure_from_grounding();

            CREATE CONSTRAINT TRIGGER trg_retrieval_run_text_erasure
            AFTER INSERT OR UPDATE OF failure_message ON policy_retrieval_runs
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_analysis_erasure_from_run();

            CREATE CONSTRAINT TRIGGER trg_grounding_run_text_erasure
            AFTER INSERT OR UPDATE OF failure_message ON grounded_explanation_runs
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION csight_check_analysis_erasure_from_run();
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                      FROM case_sensitive_payloads
                     WHERE analysis_text_purged_at IS NOT NULL
                ) THEN
                    RAISE EXCEPTION
                      'analysis text erasure downgrade blocked: redacted prose cannot be restored';
                END IF;
            END
            $$;
            """
        )
    )
    op.execute("DROP TRIGGER trg_grounding_run_text_erasure ON grounded_explanation_runs")
    op.execute("DROP TRIGGER trg_retrieval_run_text_erasure ON policy_retrieval_runs")
    op.execute("DROP TRIGGER trg_grounding_analysis_text_erasure ON grounded_explanation_results")
    op.execute("DROP TRIGGER trg_query_analysis_text_erasure ON policy_retrieval_run_queries")
    op.execute("DROP TRIGGER trg_analysis_attempt_text_erasure ON analysis_stage_attempts")
    op.execute("DROP TRIGGER trg_analysis_stage_text_erasure ON analysis_stage_runs")
    op.execute("DROP TRIGGER trg_analysis_run_text_erasure ON analysis_runs")
    op.execute("DROP TRIGGER trg_llm_v2_analysis_text_erasure ON llm_extraction_results_v2")
    op.execute("DROP TRIGGER trg_llm_v1_analysis_text_erasure ON llm_extraction_results")
    op.execute("DROP TRIGGER trg_payload_analysis_text_erasure ON case_sensitive_payloads")
    op.execute("DROP FUNCTION csight_check_analysis_erasure_from_grounding()")
    op.execute("DROP FUNCTION csight_check_analysis_erasure_from_query()")
    op.execute("DROP FUNCTION csight_check_analysis_erasure_from_result()")
    op.execute("DROP FUNCTION csight_check_analysis_erasure_from_stage()")
    op.execute("DROP FUNCTION csight_check_analysis_erasure_from_run()")
    op.execute("DROP FUNCTION csight_check_analysis_erasure_from_payload()")
    op.execute("DROP FUNCTION csight_assert_analysis_text_erasure(uuid, uuid)")
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
    op.drop_column("case_sensitive_payloads", "analysis_text_purged_at")


__all__ = ["down_revision", "downgrade", "revision", "upgrade"]
