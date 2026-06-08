"""add intake review telemetry snapshots

Revision ID: 20260607_0015
Revises: 20260607_0014
Create Date: 2026-06-07 12:15:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260607_0015"
down_revision = "20260607_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intake_review_telemetry_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("in_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("low_confidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("high_risk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hard_block_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_counts_json", sa.JSON(), nullable=True),
        sa.Column("status_counts_json", sa.JSON(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_intake_review_telemetry_snapshots_user_id",
        "intake_review_telemetry_snapshots",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_intake_review_telemetry_snapshots_generated_at",
        "intake_review_telemetry_snapshots",
        ["generated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_intake_review_telemetry_snapshots_generated_at", table_name="intake_review_telemetry_snapshots")
    op.drop_index("ix_intake_review_telemetry_snapshots_user_id", table_name="intake_review_telemetry_snapshots")
    op.drop_table("intake_review_telemetry_snapshots")
