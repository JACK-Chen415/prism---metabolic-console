"""link ai feedback to app messages

Revision ID: 20260530_0009
Revises: 20260530_0008
Create Date: 2026-05-30 21:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260530_0009"
down_revision = "20260530_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_feedback", sa.Column("app_message_id", sa.Integer(), nullable=True))
    op.create_index("ix_ai_feedback_app_message_id", "ai_feedback", ["app_message_id"], unique=False)
    op.create_foreign_key(
        "fk_ai_feedback_app_message_id_app_messages",
        "ai_feedback",
        "app_messages",
        ["app_message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_ai_feedback_app_message_id_app_messages", "ai_feedback", type_="foreignkey")
    op.drop_index("ix_ai_feedback_app_message_id", table_name="ai_feedback")
    op.drop_column("ai_feedback", "app_message_id")
