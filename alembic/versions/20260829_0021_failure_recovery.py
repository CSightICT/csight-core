"""Add durable operational failure recovery and database dead letters.

Revision ID: 20260829_0021_failure_recovery
Revises: 20260829_0020_postgres_rls_roles
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260829_0021_failure_recovery"
down_revision: str | None = "20260829_0020_postgres_rls_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_EXPRESSION = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_IMMUTABLE_TABLES = (
    "operational_failures",
    "operational_failure_recovery_runs",
    "operational_failure_resolutions",
)
_SOURCE_OUTBOXES: tuple[tuple[str, str, str, str], ...] = (
    (
        "policy_retrieval_outbox_events",
        "policy_retrieval",
        "retrieval_run_id",
        "POLICY_RETRIEVAL_OUTBOX_FAILED",
    ),
    (
        "grounded_explanation_outbox_events",
        "grounded_explanation",
        "grounded_explanation_run_id",
        "GROUNDED_EXPLANATION_OUTBOX_FAILED",
    ),
    (
        "policy_evaluation_outbox_events",
        "policy_evaluation",
        "policy_evaluation_run_id",
        "POLICY_EVALUATION_OUTBOX_FAILED",
    ),
    (
        "human_review_request_events",
        "human_review",
        "policy_evaluation_run_id",
        "HUMAN_REVIEW_OUTBOX_FAILED",
    ),
    (
        "case_resolution_request_events",
        "case_resolution",
        "resolution_id",
        "CASE_RESOLUTION_OUTBOX_FAILED",
    ),
    (
        "external_action_simulation_request_events",
        "action_simulation",
        "external_action_intent_id",
        "EXTERNAL_ACTION_SIMULATION_OUTBOX_FAILED",
    ),
)


def _create_tables() -> None:
    op.create_table(
        "operational_failures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline", sa.String(32), nullable=False),
        sa.Column("failure_kind", sa.String(32), nullable=False),
        sa.Column("source_table", sa.String(64), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=True),
        sa.Column("source_stage_id", sa.Uuid(), nullable=True),
        sa.Column("failure_code", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("replayable", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_operational_failures_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "pipeline IN ('analysis','policy_retrieval','grounded_explanation',"
            "'policy_evaluation','human_review','case_resolution','action_simulation',"
            "'failure_recovery')",
            name=op.f("ck_operational_failures_pipeline_allowed"),
        ),
        sa.CheckConstraint(
            "failure_kind IN ('DISPATCH','CONSUMER')",
            name=op.f("ck_operational_failures_kind_allowed"),
        ),
        sa.CheckConstraint(
            "source_table IN ('outbox_events','policy_retrieval_outbox_events',"
            "'grounded_explanation_outbox_events','policy_evaluation_outbox_events',"
            "'human_review_request_events','case_resolution_request_events',"
            "'external_action_simulation_request_events',"
            "'operational_failure_recovery_events')",
            name=op.f("ck_operational_failures_source_allowed"),
        ),
        sa.CheckConstraint(
            "failure_code ~ '^[A-Z][A-Z0-9_]{1,127}$'",
            name=op.f("ck_operational_failures_code_safe"),
        ),
        sa.CheckConstraint(
            "length(btrim(correlation_id)) BETWEEN 1 AND 128",
            name=op.f("ck_operational_failures_correlation_nonempty"),
        ),
        sa.CheckConstraint(
            "NOT replayable OR failure_kind = 'DISPATCH'",
            name=op.f("ck_operational_failures_replayable_dispatch_only"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_operational_failures"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_operational_failures_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_table",
            "source_event_id",
            "failure_kind",
            "failure_code",
            "occurred_at",
            name="uq_operational_failures_occurrence",
        ),
    )
    op.create_index(
        "ix_operational_failures_tenant_occurred",
        "operational_failures",
        ["tenant_id", "occurred_at", "id"],
    )
    op.create_table(
        "operational_failure_recovery_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("failure_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "failure_id"],
            ["operational_failures.tenant_id", "operational_failures.id"],
            name="fk_failure_recovery_runs_failure",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by"],
            ["users.tenant_id", "users.id"],
            name="fk_failure_recovery_runs_user",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) BETWEEN 1 AND 255",
            name=op.f("ck_operational_failure_recovery_runs_key_nonempty"),
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_operational_failure_recovery_runs_hash_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_operational_failure_recovery_runs"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_failure_recovery_runs_tenant_id"),
        sa.UniqueConstraint("tenant_id", "failure_id", name="uq_failure_recovery_runs_failure"),
    )

    op.create_table(
        "operational_failure_recovery_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("failure_id", sa.Uuid(), nullable=False),
        sa.Column("recovery_run_id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("claimed_by", sa.String(255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(1000), nullable=True),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "failure_id"],
            ["operational_failures.tenant_id", "operational_failures.id"],
            name="fk_failure_recovery_events_failure",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "recovery_run_id"],
            [
                "operational_failure_recovery_runs.tenant_id",
                "operational_failure_recovery_runs.id",
            ],
            name="fk_failure_recovery_events_run",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "topic IN ('analysis.requested.v1','policy_retrieval.requested.v1',"
            "'grounded_explanation.requested.v1','policy_evaluation.requested.v1',"
            "'human_review.requested.v1','case_resolution.requested.v1',"
            "'external_action.simulation_requested.v1')",
            name=op.f("ck_operational_failure_recovery_events_topic_allowed"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND "
            "payload ?& ARRAY['event_id','tenant_id','case_id','correlation_id']",
            name=op.f("ck_operational_failure_recovery_events_payload_identifiers"),
        ),
        sa.CheckConstraint(
            "(payload - ARRAY['event_id','tenant_id','case_id','correlation_id',"
            "'analysis_run_id','stage_run_id','retrieval_run_id',"
            "'grounded_explanation_run_id','policy_evaluation_run_id','resolution_id',"
            "'external_action_intent_id']) = '{}'::jsonb",
            name=op.f("ck_operational_failure_recovery_events_payload_allowlist"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','PUBLISHED','FAILED')",
            name=op.f("ck_operational_failure_recovery_events_status_allowed"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_operational_failure_recovery_events_attempts_nonnegative"),
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND claimed_at IS NULL AND claim_token IS NULL "
            "AND claimed_by IS NULL AND published_at IS NULL AND failed_at IS NULL) OR "
            "(status = 'PROCESSING' AND claimed_at IS NOT NULL AND claim_token IS NOT NULL "
            "AND claimed_by IS NOT NULL AND published_at IS NULL AND failed_at IS NULL "
            "AND attempt_count > 0) OR "
            "(status = 'PUBLISHED' AND claimed_at IS NULL AND claim_token IS NULL "
            "AND claimed_by IS NULL AND published_at IS NOT NULL AND failed_at IS NULL "
            "AND attempt_count > 0) OR "
            "(status = 'FAILED' AND claimed_at IS NULL AND claim_token IS NULL "
            "AND claimed_by IS NULL AND published_at IS NULL AND failed_at IS NOT NULL "
            "AND failure_code IS NOT NULL AND last_error IS NOT NULL AND attempt_count > 0)",
            name=op.f("ck_operational_failure_recovery_events_state_consistent"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_operational_failure_recovery_events"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_failure_recovery_events_tenant_id"),
        sa.UniqueConstraint("tenant_id", "recovery_run_id", name="uq_failure_recovery_events_run"),
    )
    op.create_index(
        "ix_failure_recovery_events_pending",
        "operational_failure_recovery_events",
        ["available_at", "created_at", "id"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "ix_failure_recovery_events_processing",
        "operational_failure_recovery_events",
        ["claimed_at", "id"],
        postgresql_where=sa.text("status = 'PROCESSING'"),
    )

    op.create_table(
        "operational_failure_resolutions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("failure_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("recovery_run_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "failure_id"],
            ["operational_failures.tenant_id", "operational_failures.id"],
            name="fk_failure_resolutions_failure",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["users.tenant_id", "users.id"],
            name="fk_failure_resolutions_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "recovery_run_id"],
            [
                "operational_failure_recovery_runs.tenant_id",
                "operational_failure_recovery_runs.id",
            ],
            name="fk_failure_resolutions_recovery_run",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "action IN ('REPLAYED','CANCELLED')",
            name=op.f("ck_operational_failure_resolutions_action_allowed"),
        ),
        sa.CheckConstraint(
            "reason_code IN ('OPERATOR_REPLAY','OPERATOR_CANCELLED')",
            name=op.f("ck_operational_failure_resolutions_reason_allowed"),
        ),
        sa.CheckConstraint(
            "(action = 'REPLAYED' AND recovery_run_id IS NOT NULL "
            "AND reason_code = 'OPERATOR_REPLAY') OR "
            "(action = 'CANCELLED' AND recovery_run_id IS NULL "
            "AND reason_code = 'OPERATOR_CANCELLED')",
            name=op.f("ck_operational_failure_resolutions_action_consistent"),
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$' AND content_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_operational_failure_resolutions_hashes_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_operational_failure_resolutions"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_failure_resolutions_tenant_id"),
        sa.UniqueConstraint("tenant_id", "failure_id", name="uq_failure_resolutions_failure"),
        sa.UniqueConstraint(
            "tenant_id",
            "action",
            "idempotency_key",
            name="uq_failure_resolutions_idempotency",
        ),
    )


def _create_failure_capture_function() -> None:
    op.execute(
        r"""
        CREATE FUNCTION public.csight_capture_outbox_failure()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            failure_pipeline text;
            failure_kind text;
            failure_source_run uuid;
            failure_source_stage uuid;
            failure_correlation_id text;
            safe_failure_code text;
            dispatch_code text;
            occurred_at timestamptz;
            uuid_pattern constant text :=
                '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$';
        BEGIN
            IF NEW.status <> 'FAILED' THEN
                RETURN NEW;
            END IF;
            IF TG_OP = 'UPDATE' AND OLD.status = 'FAILED' THEN
                RETURN NEW;
            END IF;

            IF TG_TABLE_NAME = 'outbox_events' THEN
                failure_pipeline := 'analysis';
                dispatch_code := 'OUTBOX_DISPATCH_FAILED';
                safe_failure_code := CASE
                    WHEN NEW.last_error = 'Message publication failed permanently.'
                        THEN dispatch_code
                    ELSE 'ANALYSIS_QUEUE_EVENT_FAILED'
                END;
                failure_source_run := NEW.aggregate_id;
                failure_correlation_id := NEW.payload->>'correlation_id';
                IF lower(COALESCE(NEW.payload->>'stage_run_id', '')) ~ uuid_pattern THEN
                    failure_source_stage := (NEW.payload->>'stage_run_id')::uuid;
                END IF;
                occurred_at := NEW.updated_at;
            ELSIF TG_TABLE_NAME = 'policy_retrieval_outbox_events' THEN
                failure_pipeline := 'policy_retrieval';
                dispatch_code := 'POLICY_RETRIEVAL_OUTBOX_FAILED';
                safe_failure_code := COALESCE(NEW.failure_code, 'POLICY_RETRIEVAL_EVENT_FAILED');
                failure_source_run := NEW.retrieval_run_id;
                failure_correlation_id := NEW.correlation_id;
                occurred_at := COALESCE(NEW.failed_at, NEW.created_at);
            ELSIF TG_TABLE_NAME = 'grounded_explanation_outbox_events' THEN
                failure_pipeline := 'grounded_explanation';
                dispatch_code := 'GROUNDED_EXPLANATION_OUTBOX_FAILED';
                safe_failure_code := COALESCE(NEW.failure_code, 'GROUNDED_EXPLANATION_EVENT_FAILED');
                failure_source_run := NEW.grounded_explanation_run_id;
                failure_correlation_id := NEW.correlation_id;
                occurred_at := COALESCE(NEW.failed_at, NEW.created_at);
            ELSIF TG_TABLE_NAME = 'policy_evaluation_outbox_events' THEN
                failure_pipeline := 'policy_evaluation';
                dispatch_code := 'POLICY_EVALUATION_OUTBOX_FAILED';
                safe_failure_code := COALESCE(NEW.failure_code, 'POLICY_EVALUATION_EVENT_FAILED');
                failure_source_run := NEW.policy_evaluation_run_id;
                failure_correlation_id := NEW.correlation_id;
                occurred_at := COALESCE(NEW.failed_at, NEW.created_at);
            ELSIF TG_TABLE_NAME = 'human_review_request_events' THEN
                failure_pipeline := 'human_review';
                dispatch_code := 'HUMAN_REVIEW_OUTBOX_FAILED';
                safe_failure_code := COALESCE(NEW.failure_code, 'HUMAN_REVIEW_EVENT_FAILED');
                failure_source_run := NEW.policy_evaluation_run_id;
                failure_correlation_id := NEW.correlation_id;
                occurred_at := COALESCE(NEW.failed_at, NEW.created_at);
            ELSIF TG_TABLE_NAME = 'case_resolution_request_events' THEN
                failure_pipeline := 'case_resolution';
                dispatch_code := 'CASE_RESOLUTION_OUTBOX_FAILED';
                safe_failure_code := COALESCE(NEW.failure_code, 'CASE_RESOLUTION_EVENT_FAILED');
                failure_source_run := NEW.resolution_id;
                failure_correlation_id := NEW.correlation_id;
                occurred_at := COALESCE(NEW.failed_at, NEW.created_at);
            ELSIF TG_TABLE_NAME = 'external_action_simulation_request_events' THEN
                failure_pipeline := 'action_simulation';
                dispatch_code := 'EXTERNAL_ACTION_SIMULATION_OUTBOX_FAILED';
                safe_failure_code := COALESCE(
                    NEW.failure_code,
                    'EXTERNAL_ACTION_SIMULATION_EVENT_FAILED'
                );
                failure_source_run := NEW.external_action_intent_id;
                failure_correlation_id := NEW.correlation_id;
                occurred_at := COALESCE(NEW.failed_at, NEW.created_at);
            ELSIF TG_TABLE_NAME = 'operational_failure_recovery_events' THEN
                failure_pipeline := 'failure_recovery';
                dispatch_code := 'FAILURE_RECOVERY_OUTBOX_FAILED';
                safe_failure_code := COALESCE(NEW.failure_code, dispatch_code);
                failure_source_run := NEW.recovery_run_id;
                failure_correlation_id := NEW.correlation_id;
                occurred_at := COALESCE(NEW.failed_at, NEW.created_at);
            ELSE
                RAISE EXCEPTION 'unsupported CSight outbox failure source: %', TG_TABLE_NAME;
            END IF;

            IF safe_failure_code !~ '^[A-Z][A-Z0-9_]{1,127}$' THEN
                safe_failure_code := 'UNCLASSIFIED_ASYNC_FAILURE';
            END IF;
            failure_kind := CASE
                WHEN safe_failure_code = dispatch_code THEN 'DISPATCH'
                ELSE 'CONSUMER'
            END;

            INSERT INTO public.operational_failures (
                id, tenant_id, pipeline, failure_kind, source_table, source_event_id,
                source_run_id, source_stage_id, failure_code, correlation_id,
                replayable, occurred_at, recorded_at
            ) VALUES (
                gen_random_uuid(), NEW.tenant_id, failure_pipeline, failure_kind,
                TG_TABLE_NAME, NEW.id, failure_source_run, failure_source_stage,
                safe_failure_code, failure_correlation_id,
                failure_kind = 'DISPATCH' AND failure_pipeline <> 'failure_recovery',
                occurred_at, clock_timestamp()
            )
            ON CONFLICT DO NOTHING;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.csight_capture_outbox_failure() FROM PUBLIC")

    for table_name in (
        "outbox_events",
        *[spec[0] for spec in _SOURCE_OUTBOXES],
        "operational_failure_recovery_events",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_capture_failure
            AFTER INSERT OR UPDATE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION public.csight_capture_outbox_failure()
            """
        )


def _create_append_only_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION public.csight_reject_operational_history_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            RAISE EXCEPTION 'CSight operational recovery history is append-only';
        END;
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.csight_reject_operational_history_mutation() FROM PUBLIC"
    )
    for table_name in _IMMUTABLE_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_append_only
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION public.csight_reject_operational_history_mutation()
            """
        )


def _enable_rls_and_grants() -> None:
    api_tables = (
        "operational_failures",
        "operational_failure_recovery_runs",
        "operational_failure_recovery_events",
        "operational_failure_resolutions",
    )
    for table_name in api_tables:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY csight_tenant_scope ON {table_name}
            FOR ALL TO csight_api_role
            USING ({_TENANT_EXPRESSION})
            WITH CHECK ({_TENANT_EXPRESSION})
            """
        )
        op.execute(f"GRANT SELECT ON {table_name} TO csight_api_role")

    # The SECURITY DEFINER trigger is created by the same migration owner as
    # the table. FORCE RLS therefore still applies; grant that exact owner an
    # insert-only policy instead of giving the Dispatcher table access.
    op.execute(
        """
        CREATE POLICY csight_failure_capture_insert ON operational_failures
        FOR INSERT TO CURRENT_USER
        WITH CHECK (true)
        """
    )

    for table_name in (
        "operational_failure_recovery_runs",
        "operational_failure_recovery_events",
        "operational_failure_resolutions",
    ):
        op.execute(f"GRANT INSERT ON {table_name} TO csight_api_role")
    # SELECT ... FOR UPDATE requires UPDATE privilege even though the immutable
    # trigger rejects every actual row mutation. This grant only permits the
    # row lock that fences one replay/cancel action.
    op.execute("GRANT UPDATE ON operational_failures TO csight_api_role")

    op.execute(
        """
        CREATE POLICY csight_dispatcher_outbox_scope
        ON operational_failure_recovery_events
        FOR ALL TO csight_dispatcher_role
        USING (true)
        WITH CHECK (true)
        """
    )
    op.execute(
        "GRANT SELECT, UPDATE ON operational_failure_recovery_events TO csight_dispatcher_role"
    )


def _backfill_existing_failures() -> None:
    op.execute(
        """
        INSERT INTO operational_failures (
            id, tenant_id, pipeline, failure_kind, source_table, source_event_id,
            source_run_id, source_stage_id, failure_code, correlation_id,
            replayable, occurred_at, recorded_at
        )
        SELECT gen_random_uuid(), tenant_id, 'analysis',
               CASE WHEN last_error = 'Message publication failed permanently.'
                    THEN 'DISPATCH' ELSE 'CONSUMER' END,
               'outbox_events', id, aggregate_id,
               CASE
                   WHEN lower(COALESCE(payload->>'stage_run_id', '')) ~
                     '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
                   THEN (payload->>'stage_run_id')::uuid
               END,
               CASE WHEN last_error = 'Message publication failed permanently.'
                    THEN 'OUTBOX_DISPATCH_FAILED' ELSE 'ANALYSIS_QUEUE_EVENT_FAILED' END,
               payload->>'correlation_id',
               last_error = 'Message publication failed permanently.',
               updated_at, clock_timestamp()
          FROM outbox_events
         WHERE status = 'FAILED'
        ON CONFLICT DO NOTHING
        """
    )
    for table_name, pipeline, run_attribute, dispatch_code in _SOURCE_OUTBOXES:
        fallback_code = f"{pipeline.upper()}_EVENT_FAILED"
        op.execute(
            f"""
            INSERT INTO operational_failures (
                id, tenant_id, pipeline, failure_kind, source_table, source_event_id,
                source_run_id, source_stage_id, failure_code, correlation_id,
                replayable, occurred_at, recorded_at
            )
            SELECT gen_random_uuid(), tenant_id, '{pipeline}',
                   CASE WHEN failure_code = '{dispatch_code}'
                        THEN 'DISPATCH' ELSE 'CONSUMER' END,
                   '{table_name}', id, {run_attribute}, NULL,
                   CASE WHEN COALESCE(failure_code, '') ~ '^[A-Z][A-Z0-9_]{{1,127}}$'
                        THEN failure_code ELSE '{fallback_code}' END,
                   correlation_id, failure_code = '{dispatch_code}',
                   COALESCE(failed_at, created_at), clock_timestamp()
              FROM {table_name}
             WHERE status = 'FAILED'
            ON CONFLICT DO NOTHING
            """
        )


def upgrade() -> None:
    _create_tables()
    _create_failure_capture_function()
    _create_append_only_guards()
    _enable_rls_and_grants()
    _backfill_existing_failures()


def downgrade() -> None:
    op.execute(
        "REVOKE SELECT, UPDATE ON operational_failure_recovery_events FROM csight_dispatcher_role"
    )
    op.execute("DROP POLICY csight_dispatcher_outbox_scope ON operational_failure_recovery_events")
    op.execute("DROP POLICY csight_failure_capture_insert ON operational_failures")

    for table_name in reversed(
        (
            "operational_failures",
            "operational_failure_recovery_runs",
            "operational_failure_recovery_events",
            "operational_failure_resolutions",
        )
    ):
        op.execute(f"REVOKE ALL PRIVILEGES ON {table_name} FROM csight_api_role")
        op.execute(f"DROP POLICY csight_tenant_scope ON {table_name}")

    for table_name in reversed(_IMMUTABLE_TABLES):
        op.execute(f"DROP TRIGGER trg_{table_name}_append_only ON {table_name}")
    op.execute("DROP FUNCTION public.csight_reject_operational_history_mutation()")

    for table_name in reversed(
        (
            "outbox_events",
            *[spec[0] for spec in _SOURCE_OUTBOXES],
            "operational_failure_recovery_events",
        )
    ):
        op.execute(f"DROP TRIGGER trg_{table_name}_capture_failure ON {table_name}")
    op.execute("DROP FUNCTION public.csight_capture_outbox_failure()")

    op.drop_table("operational_failure_resolutions")
    op.drop_table("operational_failure_recovery_events")
    op.drop_table("operational_failure_recovery_runs")
    op.drop_table("operational_failures")
