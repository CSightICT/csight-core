"""Admit a separate idempotency namespace for signed Case intake.

Revision ID: 20260831_0032_signed_case_intake
Revises: 20260830_0031_oidc_backchannel_logout
Create Date: 2026-08-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260831_0032_signed_case_intake"
down_revision: str | None = "20260830_0031_oidc_backchannel_logout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_idempotency_records_operation_allowed"),
        "idempotency_records",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_idempotency_records_operation_allowed"),
        "idempotency_records",
        "operation IN ('case.create.v1','case.intake.signed.v1')",
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM idempotency_records
             WHERE operation = 'case.intake.signed.v1'
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade while signed intake idempotency records exist';
          END IF;
        END;
        $$
        """
    )
    op.drop_constraint(
        op.f("ck_idempotency_records_operation_allowed"),
        "idempotency_records",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_idempotency_records_operation_allowed"),
        "idempotency_records",
        "operation = 'case.create.v1'",
    )
