"""add failed meal sync status

Revision ID: 20260530_0010
Revises: 20260530_0009
Create Date: 2026-05-30 23:30:00
"""

from alembic import op


revision = "20260530_0010"
down_revision = "20260530_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE syncstatus ADD VALUE IF NOT EXISTS 'FAILED'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely without rewriting dependent columns.
    # Keep downgrade intentionally non-destructive.
    pass
