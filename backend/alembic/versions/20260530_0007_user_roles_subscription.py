"""user roles and subscription state

Revision ID: 20260530_0007
Revises: 20260530_0006
Create Date: 2026-05-30 05:15:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260530_0007"
down_revision = "20260530_0006"
branch_labels = None
depends_on = None


user_role_enum = postgresql.ENUM("USER", "ADMIN", "COACH", name="userrole")
subscription_plan_enum = postgresql.ENUM("FREE", "PRO", "COACH", name="subscriptionplan")
subscription_status_enum = postgresql.ENUM(
    "inactive",
    "active",
    "canceled",
    name="subscriptionstatus",
)

user_role_ref = postgresql.ENUM("USER", "ADMIN", "COACH", name="userrole", create_type=False)
subscription_plan_ref = postgresql.ENUM(
    "FREE",
    "PRO",
    "COACH",
    name="subscriptionplan",
    create_type=False,
)
subscription_status_ref = postgresql.ENUM(
    "inactive",
    "active",
    "canceled",
    name="subscriptionstatus",
    create_type=False,
)


def upgrade() -> None:
    user_role_enum.create(op.get_bind(), checkfirst=True)
    subscription_plan_enum.create(op.get_bind(), checkfirst=True)
    subscription_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column("role", user_role_ref, nullable=False, server_default="USER"),
    )
    op.add_column(
        "users",
        sa.Column("subscription_plan", subscription_plan_ref, nullable=False, server_default="FREE"),
    )
    op.add_column(
        "users",
        sa.Column(
            "subscription_status",
            subscription_status_ref,
            nullable=False,
            server_default="inactive",
        ),
    )
    op.add_column(
        "users",
        sa.Column("subscription_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_role", "users", ["role"], unique=False)
    op.create_index("ix_users_subscription_plan", "users", ["subscription_plan"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_subscription_plan", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_column("users", "subscription_updated_at")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "subscription_plan")
    op.drop_column("users", "role")

    subscription_status_enum.drop(op.get_bind(), checkfirst=True)
    subscription_plan_enum.drop(op.get_bind(), checkfirst=True)
    user_role_enum.drop(op.get_bind(), checkfirst=True)
