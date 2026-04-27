"""meal metadata for multimodal intake

Revision ID: 20260427_0003
Revises: 20260426_0002
Create Date: 2026-04-27 09:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_0003"
down_revision = "20260426_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meals", sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"))
    op.add_column("meals", sa.Column("source_detail", sa.String(length=100), nullable=True))
    op.add_column("meals", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("meals", sa.Column("estimated_fields_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.add_column("meals", sa.Column("rule_warnings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.add_column("meals", sa.Column("recognition_meta_json", sa.JSON(), nullable=True))

    op.alter_column("meals", "source", server_default=None)
    op.alter_column("meals", "estimated_fields_json", server_default=None)
    op.alter_column("meals", "rule_warnings_json", server_default=None)


def downgrade() -> None:
    op.drop_column("meals", "recognition_meta_json")
    op.drop_column("meals", "rule_warnings_json")
    op.drop_column("meals", "estimated_fields_json")
    op.drop_column("meals", "confidence")
    op.drop_column("meals", "source_detail")
    op.drop_column("meals", "source")
