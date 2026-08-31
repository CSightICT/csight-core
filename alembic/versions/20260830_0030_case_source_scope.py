"""Add immutable Case source scope for pilot-eligible metrics.

Revision ID: 20260830_0030_case_source_scope
Revises: 20260830_0029_terminal_content_erasure
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0030_case_source_scope"
down_revision: str | None = "20260830_0029_terminal_content_erasure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column(
            "source_scope",
            sa.String(length=32),
            nullable=False,
            server_default="NOT_ATTESTED",
        ),
    )
    op.add_column(
        "cases",
        sa.Column(
            "source_provenance",
            sa.String(length=255),
            nullable=False,
            server_default="unattested/legacy",
        ),
    )
    op.execute(
        "UPDATE cases SET source_scope = 'SYNTHETIC_DEMO', "
        "source_provenance = 'synthetic_commerce_context/1.0.0' "
        "WHERE attributes ? 'synthetic_commerce_context'"
    )
    op.alter_column("cases", "source_scope", server_default=None)
    op.alter_column("cases", "source_provenance", server_default=None)
    op.create_check_constraint(
        op.f("ck_cases_source_scope_allowed"),
        "cases",
        "source_scope IN ('SYNTHETIC_DEMO','SHADOW','IMPORTED','PILOT_LIVE','NOT_ATTESTED')",
    )
    op.create_check_constraint(
        op.f("ck_cases_source_provenance_nonempty"),
        "cases",
        "length(btrim(source_provenance)) BETWEEN 1 AND 255",
    )
    op.create_index(
        "ix_cases_tenant_source_scope_created",
        "cases",
        ["tenant_id", "source_scope", "created_at", "id"],
    )
    op.execute(
        """
        CREATE FUNCTION csight_reject_case_source_scope_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.source_scope IS DISTINCT FROM OLD.source_scope
             OR NEW.source_provenance IS DISTINCT FROM OLD.source_provenance THEN
            RAISE EXCEPTION 'Case source scope and provenance are immutable';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_cases_source_scope_immutable
        BEFORE UPDATE OF source_scope, source_provenance ON cases
        FOR EACH ROW EXECUTE FUNCTION csight_reject_case_source_scope_update()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_cases_source_scope_immutable ON cases")
    op.execute("DROP FUNCTION IF EXISTS csight_reject_case_source_scope_update()")
    op.drop_index("ix_cases_tenant_source_scope_created", table_name="cases")
    op.drop_constraint(op.f("ck_cases_source_provenance_nonempty"), "cases", type_="check")
    op.drop_constraint(op.f("ck_cases_source_scope_allowed"), "cases", type_="check")
    op.drop_column("cases", "source_provenance")
    op.drop_column("cases", "source_scope")
