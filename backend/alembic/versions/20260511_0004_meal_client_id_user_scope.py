"""scope meal client ids per user

Revision ID: 20260511_0004
Revises: 20260427_0003
Create Date: 2026-05-11 13:45:00
"""

from alembic import op


revision = "20260511_0004"
down_revision = "20260427_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("meals") as batch_op:
        batch_op.drop_index("ix_meals_client_id")
        batch_op.drop_constraint("uq_meals_client_id", type_="unique")
        batch_op.create_unique_constraint("uq_meals_user_client_id", ["user_id", "client_id"])

    op.create_index("ix_meals_client_id", "meals", ["client_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_meals_client_id", table_name="meals")

    with op.batch_alter_table("meals") as batch_op:
        batch_op.drop_constraint("uq_meals_user_client_id", type_="unique")
        batch_op.create_unique_constraint("uq_meals_client_id", ["client_id"])

    op.create_index("ix_meals_client_id", "meals", ["client_id"], unique=True)
