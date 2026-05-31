"""registration consent audit fields

Revision ID: 20260530_0008
Revises: 20260530_0007
Create Date: 2026-05-30 08:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260530_0008"
down_revision = "20260530_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("consent_version", sa.String(length=40), nullable=True))
    op.add_column("users", sa.Column("consent_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("consent_terms_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("consent_privacy_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("consent_ai_use_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("consent_health_disclaimer_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "consent_health_disclaimer_accepted")
    op.drop_column("users", "consent_ai_use_accepted")
    op.drop_column("users", "consent_privacy_accepted")
    op.drop_column("users", "consent_terms_accepted")
    op.drop_column("users", "consent_accepted_at")
    op.drop_column("users", "consent_version")
