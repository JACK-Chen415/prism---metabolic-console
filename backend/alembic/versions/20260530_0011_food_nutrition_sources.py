"""add nutrition source provenance to food items

Revision ID: 20260530_0011
Revises: 20260530_0010
Create Date: 2026-05-31 01:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260530_0011"
down_revision = "20260530_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "food_items",
        sa.Column(
            "nutrition_source_code",
            sa.String(length=120),
            nullable=False,
            server_default="core_v1_food_nutrition_estimate",
        ),
    )
    op.add_column(
        "food_items",
        sa.Column(
            "nutrition_source_detail",
            sa.String(length=255),
            nullable=False,
            server_default="Core v1 estimate from public composition references, labels, and recipe normalization.",
        ),
    )
    op.add_column(
        "food_items",
        sa.Column(
            "nutrition_estimate_quality",
            sa.String(length=50),
            nullable=False,
            server_default="MIXED_REFERENCE_AND_RECIPE_ESTIMATE",
        ),
    )
    op.add_column(
        "food_items",
        sa.Column(
            "nutrition_review_status",
            sa.String(length=50),
            nullable=False,
            server_default="REVIEWED",
        ),
    )


def downgrade() -> None:
    op.drop_column("food_items", "nutrition_review_status")
    op.drop_column("food_items", "nutrition_estimate_quality")
    op.drop_column("food_items", "nutrition_source_detail")
    op.drop_column("food_items", "nutrition_source_code")
