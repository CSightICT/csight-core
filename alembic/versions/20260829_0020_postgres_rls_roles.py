"""Add fail-closed tenant RLS and process database roles.

Revision ID: 20260829_0020_postgres_rls_roles
Revises: 20260829_0019_analysis_execution_modes
Create Date: 2026-08-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260829_0020_postgres_rls_roles"
down_revision: str | None = "20260829_0019_analysis_execution_modes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APPLICATION_ROLES = (
    "csight_api_role",
    "csight_worker_role",
    "csight_dispatcher_role",
)

# Every current table that owns a tenant_id column.  This is intentionally
# explicit: a future migration that adds a tenant table must also make a visible
# RLS decision rather than inheriting a permissive default accidentally.
_TENANT_TABLES = (
    "analysis_request_idempotency_records",
    "analysis_run_evidence",
    "analysis_runs",
    "analysis_stage_attempts",
    "analysis_stage_runs",
    "case_evidence",
    "case_learning_assets",
    "case_resolution_events",
    "case_resolution_request_events",
    "case_resolutions",
    "case_sensitive_payloads",
    "case_status_history",
    "cases",
    "customer_communication_simulations",
    "data_lifecycle_events",
    "external_action_intents",
    "external_action_simulation_attempts",
    "external_action_simulation_request_events",
    "external_action_simulation_results",
    "grounded_explanation_outbox_events",
    "grounded_explanation_results",
    "grounded_explanation_runs",
    "human_review_actions",
    "human_review_assignments",
    "human_review_decision_basis",
    "human_review_decisions",
    "human_review_packets",
    "human_review_request_events",
    "human_review_tasks",
    "idempotency_records",
    "llm_extraction_results",
    "llm_extraction_results_v2",
    "oidc_sessions",
    "outbox_events",
    "policy_citation_pack_items",
    "policy_citation_packs",
    "policy_clause_embeddings",
    "policy_clauses",
    "policy_condition_evaluation_results",
    "policy_documents",
    "policy_evaluation_effects",
    "policy_evaluation_input_snapshots",
    "policy_evaluation_outbox_events",
    "policy_evaluation_runs",
    "policy_index_versions",
    "policy_retrieval_outbox_events",
    "policy_retrieval_run_hits",
    "policy_retrieval_run_queries",
    "policy_retrieval_runs",
    "policy_rule_evaluation_results",
    "policy_rule_set_activations",
    "policy_rule_sets",
    "policy_rule_source_clauses",
    "policy_rules",
    "review_reports",
    "user_roles",
    "users",
    "vision_analysis_results",
    "vision_detections",
    "vision_image_assessments",
)

_OUTBOX_TABLES = (
    "outbox_events",
    "policy_retrieval_outbox_events",
    "grounded_explanation_outbox_events",
    "policy_evaluation_outbox_events",
    "human_review_request_events",
    "case_resolution_request_events",
    "external_action_simulation_request_events",
)

_MUTABLE_PROFILE_TABLES = (
    "grounding_profiles",
    "policy_embedding_profiles",
    "policy_ingestion_runs",
    "policy_query_builder_profiles",
    "policy_reranker_profiles",
    "policy_retrieval_execution_profiles",
)

_TENANT_EXPRESSION = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def _create_application_roles() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            role_name text;
            unsafe_role boolean;
        BEGIN
            FOREACH role_name IN ARRAY ARRAY[
                'csight_api_role',
                'csight_worker_role',
                'csight_dispatcher_role'
            ]
            LOOP
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
                    EXECUTE format(
                        'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB '
                        'NOCREATEROLE NOREPLICATION NOBYPASSRLS',
                        role_name
                    );
                ELSE
                    SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication
                           OR rolbypassrls OR rolcanlogin
                      INTO unsafe_role
                      FROM pg_roles
                     WHERE rolname = role_name;
                    IF unsafe_role THEN
                        RAISE EXCEPTION 'existing CSight application role % is unsafe', role_name;
                    END IF;
                END IF;
            END LOOP;
        END;
        $$
        """
    )


def _grant_runtime_privileges() -> None:
    for role in _APPLICATION_ROLES:
        op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")

    for role in ("csight_api_role", "csight_worker_role"):
        op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
        for table_name in _TENANT_TABLES:
            op.execute(f"GRANT INSERT, UPDATE, DELETE ON {table_name} TO {role}")
        for table_name in _MUTABLE_PROFILE_TABLES:
            op.execute(f"GRANT INSERT, UPDATE, DELETE ON {table_name} TO {role}")

    op.execute("GRANT INSERT, UPDATE, DELETE ON oidc_login_transactions TO csight_api_role")

    # A session hash is a read/update capability, not permission to rewrite its
    # owner or provider identity.  INSERT remains tenant-context protected.
    op.execute("REVOKE UPDATE ON oidc_sessions FROM csight_api_role")
    op.execute("REVOKE DELETE ON oidc_sessions FROM csight_api_role")
    op.execute(
        "GRANT UPDATE (csrf_token_hash, last_seen_at, idle_expires_at, revoked_at, "
        "revocation_reason) ON oidc_sessions TO csight_api_role"
    )
    op.execute("REVOKE INSERT, UPDATE, DELETE ON oidc_sessions FROM csight_worker_role")

    for table_name in _OUTBOX_TABLES:
        op.execute(f"GRANT SELECT, UPDATE ON {table_name} TO csight_dispatcher_role")


def _enable_tenant_policies() -> None:
    for table_name in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY csight_tenant_scope ON {table_name}
            FOR ALL TO csight_api_role, csight_worker_role
            USING ({_TENANT_EXPRESSION})
            WITH CHECK ({_TENANT_EXPRESSION})
            """
        )
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY csight_tenant_scope ON tenants
        FOR ALL TO csight_api_role, csight_worker_role
        USING (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY csight_login_tenant_lookup ON tenants
        FOR SELECT TO csight_api_role
        USING (slug = NULLIF(current_setting('app.login_tenant_slug', true), ''))
        """
    )

    # Before a browser session reveals its tenant, only the exact 256-bit
    # session digest presented by the application may be selected/touched.
    op.execute(
        """
        CREATE POLICY csight_oidc_session_capability_select ON oidc_sessions
        FOR SELECT TO csight_api_role
        USING (
            session_id_hash = NULLIF(
                current_setting('app.oidc_session_hash', true), ''
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY csight_oidc_session_capability_update ON oidc_sessions
        FOR UPDATE TO csight_api_role
        USING (
            session_id_hash = NULLIF(
                current_setting('app.oidc_session_hash', true), ''
            )
        )
        WITH CHECK (
            session_id_hash = NULLIF(
                current_setting('app.oidc_session_hash', true), ''
            )
        )
        """
    )

    # A malformed queue body can omit tenant_id while retaining a valid event
    # identifier.  The worker may durably quarantine only that exact event.
    for table_name in _OUTBOX_TABLES:
        op.execute(
            f"""
            CREATE POLICY csight_worker_event_capability_select ON {table_name}
            FOR SELECT TO csight_worker_role
            USING (
                id = NULLIF(
                    current_setting('app.worker_event_id', true), ''
                )::uuid
            )
            """
        )
        op.execute(
            f"""
            CREATE POLICY csight_worker_event_capability_update ON {table_name}
            FOR UPDATE TO csight_worker_role
            USING (
                id = NULLIF(
                    current_setting('app.worker_event_id', true), ''
                )::uuid
            )
            WITH CHECK (
                id = NULLIF(
                    current_setting('app.worker_event_id', true), ''
                )::uuid
            )
            """
        )

        op.execute(
            f"""
            CREATE POLICY csight_dispatcher_outbox_scope ON {table_name}
            FOR ALL TO csight_dispatcher_role
            USING (true)
            WITH CHECK (true)
            """
        )


def upgrade() -> None:
    _create_application_roles()
    _grant_runtime_privileges()
    _enable_tenant_policies()


def downgrade() -> None:
    for table_name in reversed(_OUTBOX_TABLES):
        op.execute(f"DROP POLICY csight_dispatcher_outbox_scope ON {table_name}")
        op.execute(f"DROP POLICY csight_worker_event_capability_update ON {table_name}")
        op.execute(f"DROP POLICY csight_worker_event_capability_select ON {table_name}")

    op.execute("DROP POLICY csight_oidc_session_capability_update ON oidc_sessions")
    op.execute("DROP POLICY csight_oidc_session_capability_select ON oidc_sessions")
    op.execute("DROP POLICY csight_login_tenant_lookup ON tenants")
    op.execute("DROP POLICY csight_tenant_scope ON tenants")
    op.execute("ALTER TABLE tenants NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants DISABLE ROW LEVEL SECURITY")

    for table_name in reversed(_TENANT_TABLES):
        op.execute(f"DROP POLICY csight_tenant_scope ON {table_name}")
        op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")

    for table_name in _OUTBOX_TABLES:
        op.execute(f"REVOKE SELECT, UPDATE ON {table_name} FROM csight_dispatcher_role")
    op.execute(
        "REVOKE UPDATE (csrf_token_hash, last_seen_at, idle_expires_at, revoked_at, "
        "revocation_reason) ON oidc_sessions FROM csight_api_role"
    )
    op.execute("REVOKE ALL PRIVILEGES ON oidc_login_transactions FROM csight_api_role")
    for role in ("csight_api_role", "csight_worker_role"):
        for table_name in _MUTABLE_PROFILE_TABLES:
            op.execute(f"REVOKE INSERT, UPDATE, DELETE ON {table_name} FROM {role}")
        for table_name in _TENANT_TABLES:
            op.execute(f"REVOKE INSERT, UPDATE, DELETE ON {table_name} FROM {role}")
        op.execute(f"REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM {role}")
        op.execute(f"REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM {role}")
    for role in _APPLICATION_ROLES:
        op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role}")

    # PostgreSQL roles are cluster-scoped and may already be granted to login
    # principals or used by another database.  The reversible database objects
    # and privileges are removed above; the inert NOLOGIN group roles remain.
