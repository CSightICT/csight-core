"""Create the Sprint 0 PostgreSQL baseline.

Revision ID: 20260825_0001
Revises:
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260825_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable pgvector without pre-creating Sprint 1 business tables."""

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Remove pgvector; no Sprint 0 tables depend on it."""

    op.execute("DROP EXTENSION IF EXISTS vector")
