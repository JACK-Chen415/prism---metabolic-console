"""ai feedback and health metrics

Revision ID: 20260530_0006
Revises: 20260530_0005
Create Date: 2026-05-30 03:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260530_0006"
down_revision = "20260530_0005"
branch_labels = None
depends_on = None


feedback_type_enum = postgresql.ENUM(
    "helpful",
    "not_helpful",
    "unsafe",
    "correction",
    "recognition_correction",
    "knowledge_gap",
    name="aifeedbacktype",
)
feedback_status_enum = postgresql.ENUM("open", "reviewed", "closed", name="aifeedbackstatus")
health_metric_type_enum = postgresql.ENUM(
    "weight",
    "body_fat",
    "blood_pressure",
    "blood_glucose",
    "uric_acid",
    "blood_lipid",
    "waist",
    name="healthmetrictype",
)

feedback_type_ref = postgresql.ENUM(
    "helpful",
    "not_helpful",
    "unsafe",
    "correction",
    "recognition_correction",
    "knowledge_gap",
    name="aifeedbacktype",
    create_type=False,
)
feedback_status_ref = postgresql.ENUM(
    "open",
    "reviewed",
    "closed",
    name="aifeedbackstatus",
    create_type=False,
)
health_metric_type_ref = postgresql.ENUM(
    "weight",
    "body_fat",
    "blood_pressure",
    "blood_glucose",
    "uric_acid",
    "blood_lipid",
    "waist",
    name="healthmetrictype",
    create_type=False,
)


def upgrade() -> None:
    feedback_type_enum.create(op.get_bind(), checkfirst=True)
    feedback_status_enum.create(op.get_bind(), checkfirst=True)
    health_metric_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "ai_feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("feedback_type", feedback_type_ref, nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=True),
        sa.Column("correction_text", sa.Text(), nullable=True),
        sa.Column("correction_text_hash", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("status", feedback_status_ref, nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ai_feedback_user_id", "ai_feedback", ["user_id"], unique=False)
    op.create_index("ix_ai_feedback_session_id", "ai_feedback", ["session_id"], unique=False)
    op.create_index("ix_ai_feedback_message_id", "ai_feedback", ["message_id"], unique=False)
    op.create_index("ix_ai_feedback_feedback_type", "ai_feedback", ["feedback_type"], unique=False)

    op.create_table(
        "health_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("metric_type", health_metric_type_ref, nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("value_secondary", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=24), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="manual"),
        sa.Column("provider", sa.String(length=120), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_health_metrics_user_recorded_at", "health_metrics", ["user_id", "recorded_at"], unique=False)
    op.create_index(
        "ix_health_metrics_user_type_recorded_at",
        "health_metrics",
        ["user_id", "metric_type", "recorded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_health_metrics_user_type_recorded_at", table_name="health_metrics")
    op.drop_index("ix_health_metrics_user_recorded_at", table_name="health_metrics")
    op.drop_table("health_metrics")

    op.drop_index("ix_ai_feedback_feedback_type", table_name="ai_feedback")
    op.drop_index("ix_ai_feedback_message_id", table_name="ai_feedback")
    op.drop_index("ix_ai_feedback_session_id", table_name="ai_feedback")
    op.drop_index("ix_ai_feedback_user_id", table_name="ai_feedback")
    op.drop_table("ai_feedback")

    health_metric_type_enum.drop(op.get_bind(), checkfirst=True)
    feedback_status_enum.drop(op.get_bind(), checkfirst=True)
    feedback_type_enum.drop(op.get_bind(), checkfirst=True)
