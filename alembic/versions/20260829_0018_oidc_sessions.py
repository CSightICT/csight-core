"""Add one-time OIDC login transactions and hashed browser sessions.

Revision ID: 20260829_0018_oidc_sessions
Revises: 20260829_0017_service_pilot_foundation
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260829_0018_oidc_sessions"
down_revision: str | None = "20260829_0017_service_pilot_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oidc_login_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_key", sa.String(64), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("nonce", sa.String(512), nullable=False),
        sa.Column("pkce_verifier", sa.String(128), nullable=False),
        sa.Column("return_path", sa.String(2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(btrim(provider_key)) > 0",
            name=op.f("ck_oidc_login_transactions_provider_key_nonempty"),
        ),
        sa.CheckConstraint(
            "state_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_oidc_login_transactions_state_hash_valid"),
        ),
        sa.CheckConstraint(
            "length(nonce) BETWEEN 32 AND 512",
            name=op.f("ck_oidc_login_transactions_nonce_length"),
        ),
        sa.CheckConstraint(
            "length(pkce_verifier) BETWEEN 43 AND 128",
            name=op.f("ck_oidc_login_transactions_pkce_verifier_length"),
        ),
        sa.CheckConstraint(
            "length(return_path) BETWEEN 1 AND 2048 AND left(return_path, 1) = '/'",
            name=op.f("ck_oidc_login_transactions_return_path_relative"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_oidc_login_transactions_expiry_after_creation"),
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR (consumed_at >= created_at AND consumed_at <= expires_at)",
            name=op.f("ck_oidc_login_transactions_consumed_within_lifetime"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oidc_login_transactions")),
        sa.UniqueConstraint(
            "state_hash",
            name="uq_oidc_login_transactions_state_hash",
        ),
    )
    op.create_index(
        "ix_oidc_login_transactions_pending_expiry",
        "oidc_login_transactions",
        ["expires_at"],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )

    op.create_table(
        "oidc_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider_issuer", sa.String(2048), nullable=False),
        sa.Column("provider_subject", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_oidc_sessions_tenant_user",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "session_id_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_oidc_sessions_session_id_hash_valid"),
        ),
        sa.CheckConstraint(
            "csrf_token_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_oidc_sessions_csrf_token_hash_valid"),
        ),
        sa.CheckConstraint(
            "last_seen_at >= created_at",
            name=op.f("ck_oidc_sessions_last_seen_after_creation"),
        ),
        sa.CheckConstraint(
            "absolute_expires_at > created_at "
            "AND absolute_expires_at <= created_at + INTERVAL '8 hours'",
            name=op.f("ck_oidc_sessions_absolute_lifetime_max_eight_hours"),
        ),
        sa.CheckConstraint(
            "idle_expires_at > last_seen_at "
            "AND idle_expires_at <= last_seen_at + INTERVAL '30 minutes' "
            "AND idle_expires_at <= absolute_expires_at",
            name=op.f("ck_oidc_sessions_idle_lifetime_thirty_minutes"),
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revocation_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)",
            name=op.f("ck_oidc_sessions_revocation_state_consistent"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oidc_sessions")),
        sa.UniqueConstraint("session_id_hash", name="uq_oidc_sessions_session_id_hash"),
    )
    op.create_index(
        "ix_oidc_sessions_active_expiry",
        "oidc_sessions",
        ["idle_expires_at", "absolute_expires_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_oidc_sessions_tenant_user",
        "oidc_sessions",
        ["tenant_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_oidc_sessions_tenant_user", table_name="oidc_sessions")
    op.drop_index("ix_oidc_sessions_active_expiry", table_name="oidc_sessions")
    op.drop_table("oidc_sessions")
    op.drop_index(
        "ix_oidc_login_transactions_pending_expiry",
        table_name="oidc_login_transactions",
    )
    op.drop_table("oidc_login_transactions")
