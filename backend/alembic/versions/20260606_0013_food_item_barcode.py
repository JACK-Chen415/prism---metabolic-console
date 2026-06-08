"""add barcode to food items

Revision ID: 20260606_0013
Revises: 20260601_0012
Create Date: 2026-06-06 16:35:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260606_0013"
down_revision = "20260601_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("food_items", sa.Column("barcode", sa.String(length=32), nullable=True))
    op.create_index("ix_food_items_barcode", "food_items", ["barcode"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_food_items_barcode", table_name="food_items")
    op.drop_column("food_items", "barcode")
