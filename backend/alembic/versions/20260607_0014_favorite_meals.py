"""add favorite meals

Revision ID: 20260607_0014
Revises: 20260606_0013
Create Date: 2026-06-07 11:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260607_0014"
down_revision = "20260606_0013"
branch_labels = None
depends_on = None

meal_type = sa.Enum("BREAKFAST", "LUNCH", "DINNER", "SNACK", name="mealtype")
food_category = sa.Enum("STAPLE", "MEAT", "VEG", "DRINK", "SNACK", name="foodcategory")


def upgrade() -> None:
    op.create_table(
        "favorite_meals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_meal_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("portion", sa.String(length=50), nullable=False),
        sa.Column("meal_type", meal_type, nullable=False),
        sa.Column("category", food_category, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("calories", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sodium", sa.Float(), nullable=False, server_default="0"),
        sa.Column("purine", sa.Float(), nullable=False, server_default="0"),
        sa.Column("protein", sa.Float(), nullable=True),
        sa.Column("carbs", sa.Float(), nullable=True),
        sa.Column("fat", sa.Float(), nullable=True),
        sa.Column("fiber", sa.Float(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["source_meal_id"], ["meals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", "portion", "meal_type", name="uq_favorite_meals_user_meal"),
    )
    op.create_index("ix_favorite_meals_user_id", "favorite_meals", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_favorite_meals_user_id", table_name="favorite_meals")
    op.drop_table("favorite_meals")
