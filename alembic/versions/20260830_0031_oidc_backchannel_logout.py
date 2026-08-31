"""Add signed OIDC back-channel logout receipts and provider session capabilities.

Revision ID: 20260830_0031_oidc_backchannel_logout
Revises: 20260830_0030_case_source_scope
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0031_oidc_backchannel_logout"
down_revision: str | None = "20260830_0030_case_source_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _provider_capability_expression() -> str:
    return """
        provider_subject_hash = NULLIF(
            current_setting('app.oidc_logout_subject_hash', true), ''
        )
        OR provider_session_hash = NULLIF(
            current_setting('app.oidc_logout_session_hash', true), ''
        )
    """


def upgrade() -> None:
    op.add_column(
        "oidc_sessions",
        sa.Column("provider_session_id", sa.String(512), nullable=True),
    )
    op.add_column(
        "oidc_sessions",
        sa.Column("provider_subject_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "oidc_sessions",
        sa.Column("provider_session_hash", sa.String(64), nullable=True),
    )

    op.execute(
        "UPDATE oidc_sessions SET provider_subject_hash = "
        "encode(sha256(convert_to(provider_issuer, 'UTF8') || decode('00', 'hex') || "
        "convert_to(provider_subject, 'UTF8')), 'hex') "
        "WHERE provider_subject_hash IS NULL"
    )

    op.alter_column(
        "oidc_sessions",
        "provider_subject_hash",
        existing_type=sa.String(64),
        nullable=False,
    )
    op.create_check_constraint(
        op.f("ck_oidc_sessions_provider_subject_hash_valid"),
        "oidc_sessions",
        "provider_subject_hash ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        op.f("ck_oidc_sessions_provider_session_hash_valid"),
        "oidc_sessions",
        "provider_session_hash IS NULL OR provider_session_hash ~ '^[0-9a-f]{64}$'",
    )
    op.create_index(
        "ix_oidc_sessions_active_provider_subject",
        "oidc_sessions",
        ["provider_subject_hash"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_oidc_sessions_active_provider_session",
        "oidc_sessions",
        ["provider_session_hash"],
        postgresql_where=sa.text("revoked_at IS NULL AND provider_session_hash IS NOT NULL"),
    )

    op.create_table(
        "oidc_logout_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_issuer", sa.String(2048), nullable=False),
        sa.Column("provider_subject_hash", sa.String(64), nullable=True),
        sa.Column("provider_session_hash", sa.String(64), nullable=True),
        sa.Column("token_jti_hash", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_session_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "token_jti_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_oidc_logout_events_token_jti_hash_valid"),
        ),
        sa.CheckConstraint(
            "provider_subject_hash IS NULL OR provider_subject_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_oidc_logout_events_provider_subject_hash_valid"),
        ),
        sa.CheckConstraint(
            "provider_session_hash IS NULL OR provider_session_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_oidc_logout_events_provider_session_hash_valid"),
        ),
        sa.CheckConstraint(
            "provider_subject_hash IS NOT NULL OR provider_session_hash IS NOT NULL",
            name=op.f("ck_oidc_logout_events_provider_target_present"),
        ),
        sa.CheckConstraint(
            "revoked_session_count >= 0",
            name=op.f("ck_oidc_logout_events_revoked_session_count_nonnegative"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oidc_logout_events")),
        sa.UniqueConstraint(
            "token_jti_hash",
            name="uq_oidc_logout_events_token_jti_hash",
        ),
    )

    op.execute("GRANT INSERT ON oidc_logout_events TO csight_api_role")
    op.execute("REVOKE SELECT, UPDATE, DELETE ON oidc_logout_events FROM csight_api_role")
    capability = _provider_capability_expression()
    op.execute(
        f"""
        CREATE POLICY csight_oidc_provider_logout_select ON oidc_sessions
        FOR SELECT TO csight_api_role
        USING ({capability})
        """
    )
    op.execute(
        f"""
        CREATE POLICY csight_oidc_provider_logout_update ON oidc_sessions
        FOR UPDATE TO csight_api_role
        USING ({capability})
        WITH CHECK ({capability})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY csight_oidc_provider_logout_update ON oidc_sessions")
    op.execute("DROP POLICY csight_oidc_provider_logout_select ON oidc_sessions")
    op.execute("REVOKE INSERT ON oidc_logout_events FROM csight_api_role")
    op.drop_table("oidc_logout_events")
    op.drop_index("ix_oidc_sessions_active_provider_session", table_name="oidc_sessions")
    op.drop_index("ix_oidc_sessions_active_provider_subject", table_name="oidc_sessions")
    op.drop_constraint(
        op.f("ck_oidc_sessions_provider_session_hash_valid"),
        "oidc_sessions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_oidc_sessions_provider_subject_hash_valid"),
        "oidc_sessions",
        type_="check",
    )
    op.drop_column("oidc_sessions", "provider_session_hash")
    op.drop_column("oidc_sessions", "provider_subject_hash")
    op.drop_column("oidc_sessions", "provider_session_id")
