"""Archive local synthetic review outcomes before an explicit admin reset."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260920_0039_demo_review_reset"
down_revision = "20260910_0038_fixture_evidence_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_review_resets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("ALTER TABLE demo_review_resets ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE demo_review_resets FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON demo_review_resets
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='csight_api_role') THEN
            GRANT SELECT, INSERT ON demo_review_resets TO csight_api_role;
        END IF;
    END $$""")


def downgrade() -> None:
    # Archival data must be exported explicitly before a destructive schema downgrade.
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM demo_review_resets)")):
        raise RuntimeError("Export reset archives before downgrading")
    op.drop_table("demo_review_resets")
