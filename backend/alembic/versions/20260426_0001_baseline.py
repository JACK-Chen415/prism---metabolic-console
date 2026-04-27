"""baseline existing core schema

Revision ID: 20260426_0001
Revises:
Create Date: 2026-04-26 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260426_0001"
down_revision = None
branch_labels = None
depends_on = None


gender_enum = postgresql.ENUM("MALE", "FEMALE", name="gender")
condition_type_enum = postgresql.ENUM("CHRONIC", "ALLERGY", name="conditiontype")
condition_status_enum = postgresql.ENUM("ACTIVE", "MONITORING", "STABLE", "ALERT", name="conditionstatus")
trend_type_enum = postgresql.ENUM("IMPROVED", "WORSENING", "STABLE", name="trendtype")
meal_type_enum = postgresql.ENUM("BREAKFAST", "LUNCH", "DINNER", "SNACK", name="mealtype")
food_category_enum = postgresql.ENUM("STAPLE", "MEAT", "VEG", "DRINK", "SNACK", name="foodcategory")
sync_status_enum = postgresql.ENUM("PENDING", "SYNCED", "CONFLICT", name="syncstatus")
message_type_enum = postgresql.ENUM("WARNING", "ADVICE", "BRIEF", name="messagetype")
message_role_enum = postgresql.ENUM("user", "assistant", "system", name="messagerole")

gender_enum_ref = postgresql.ENUM("MALE", "FEMALE", name="gender", create_type=False)
condition_type_enum_ref = postgresql.ENUM("CHRONIC", "ALLERGY", name="conditiontype", create_type=False)
condition_status_enum_ref = postgresql.ENUM(
    "ACTIVE",
    "MONITORING",
    "STABLE",
    "ALERT",
    name="conditionstatus",
    create_type=False,
)
trend_type_enum_ref = postgresql.ENUM("IMPROVED", "WORSENING", "STABLE", name="trendtype", create_type=False)
meal_type_enum_ref = postgresql.ENUM("BREAKFAST", "LUNCH", "DINNER", "SNACK", name="mealtype", create_type=False)
food_category_enum_ref = postgresql.ENUM("STAPLE", "MEAT", "VEG", "DRINK", "SNACK", name="foodcategory", create_type=False)
sync_status_enum_ref = postgresql.ENUM("PENDING", "SYNCED", "CONFLICT", name="syncstatus", create_type=False)
message_type_enum_ref = postgresql.ENUM("WARNING", "ADVICE", "BRIEF", name="messagetype", create_type=False)
message_role_enum_ref = postgresql.ENUM("user", "assistant", "system", name="messagerole", create_type=False)


def upgrade() -> None:
    gender_enum.create(op.get_bind(), checkfirst=True)
    condition_type_enum.create(op.get_bind(), checkfirst=True)
    condition_status_enum.create(op.get_bind(), checkfirst=True)
    trend_type_enum.create(op.get_bind(), checkfirst=True)
    meal_type_enum.create(op.get_bind(), checkfirst=True)
    food_category_enum.create(op.get_bind(), checkfirst=True)
    sync_status_enum.create(op.get_bind(), checkfirst=True)
    message_type_enum.create(op.get_bind(), checkfirst=True)
    message_role_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("nickname", sa.String(length=50), nullable=True),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("gender", gender_enum_ref, nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("height", sa.Float(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("phone", name="uq_users_phone"),
    )
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    op.create_table(
        "health_conditions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("condition_code", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("icon", sa.String(length=50), nullable=False, server_default="medical_services"),
        sa.Column("condition_type", condition_type_enum_ref, nullable=False),
        sa.Column("status", condition_status_enum_ref, nullable=False, server_default="MONITORING"),
        sa.Column("trend", trend_type_enum_ref, nullable=False, server_default="STABLE"),
        sa.Column("value", sa.String(length=50), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("dictum", sa.Text(), nullable=True),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_health_conditions_user_id", "health_conditions", ["user_id"], unique=False)
    op.create_index("ix_health_conditions_condition_code", "health_conditions", ["condition_code"], unique=False)

    op.create_table(
        "meals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("portion", sa.String(length=50), nullable=False),
        sa.Column("calories", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sodium", sa.Float(), nullable=False, server_default="0"),
        sa.Column("purine", sa.Float(), nullable=False, server_default="0"),
        sa.Column("protein", sa.Float(), nullable=True),
        sa.Column("carbs", sa.Float(), nullable=True),
        sa.Column("fat", sa.Float(), nullable=True),
        sa.Column("fiber", sa.Float(), nullable=True),
        sa.Column("meal_type", meal_type_enum_ref, nullable=False),
        sa.Column("category", food_category_enum_ref, nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("ai_recognized", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sync_status", sync_status_enum_ref, nullable=False, server_default="SYNCED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("client_id", name="uq_meals_client_id"),
    )
    op.create_index("ix_meals_user_id", "meals", ["user_id"], unique=False)
    op.create_index("ix_meals_client_id", "meals", ["client_id"], unique=True)
    op.create_index("ix_meals_record_date", "meals", ["record_date"], unique=False)

    op.create_table(
        "app_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("message_type", message_type_enum_ref, nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_app_messages_user_id", "app_messages", ["user_id"], unique=False)

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False, server_default="新对话"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"], unique=False)

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", message_role_enum_ref, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("attachments", sa.JSON(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
    op.drop_index("ix_app_messages_user_id", table_name="app_messages")
    op.drop_table("app_messages")
    op.drop_index("ix_meals_record_date", table_name="meals")
    op.drop_index("ix_meals_client_id", table_name="meals")
    op.drop_index("ix_meals_user_id", table_name="meals")
    op.drop_table("meals")
    op.drop_index("ix_health_conditions_condition_code", table_name="health_conditions")
    op.drop_index("ix_health_conditions_user_id", table_name="health_conditions")
    op.drop_table("health_conditions")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_table("users")

    message_role_enum.drop(op.get_bind(), checkfirst=True)
    message_type_enum.drop(op.get_bind(), checkfirst=True)
    sync_status_enum.drop(op.get_bind(), checkfirst=True)
    food_category_enum.drop(op.get_bind(), checkfirst=True)
    meal_type_enum.drop(op.get_bind(), checkfirst=True)
    trend_type_enum.drop(op.get_bind(), checkfirst=True)
    condition_status_enum.drop(op.get_bind(), checkfirst=True)
    condition_type_enum.drop(op.get_bind(), checkfirst=True)
    gender_enum.drop(op.get_bind(), checkfirst=True)
