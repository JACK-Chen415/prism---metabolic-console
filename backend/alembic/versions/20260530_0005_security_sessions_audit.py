"""security sessions and audit logs

Revision ID: 20260530_0005
Revises: 20260511_0004
Create Date: 2026-05-30 02:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260530_0005"
down_revision = "20260511_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("refresh_jti_hash", sa.String(length=128), nullable=False),
        sa.Column("device_label", sa.String(length=120), nullable=True),
        sa.Column("user_agent_hash", sa.String(length=128), nullable=True),
        sa.Column("ip_hash", sa.String(length=128), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_id", name="uq_device_sessions_session_id"),
        sa.UniqueConstraint("refresh_jti_hash", name="uq_device_sessions_refresh_jti_hash"),
    )
    op.create_index("ix_device_sessions_user_id", "device_sessions", ["user_id"], unique=False)
    op.create_index("ix_device_sessions_session_id", "device_sessions", ["session_id"], unique=True)
    op.create_index("ix_device_sessions_refresh_jti_hash", "device_sessions", ["refresh_jti_hash"], unique=True)

    op.create_table(
        "security_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("event_status", sa.String(length=30), nullable=False),
        sa.Column("route_name", sa.String(length=160), nullable=True),
        sa.Column("actor_hash", sa.String(length=128), nullable=True),
        sa.Column("ip_hash", sa.String(length=128), nullable=True),
        sa.Column("user_agent_hash", sa.String(length=128), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_security_audit_logs_user_id", "security_audit_logs", ["user_id"], unique=False)
    op.create_index("ix_security_audit_logs_event_type", "security_audit_logs", ["event_type"], unique=False)
    op.create_index("ix_security_audit_logs_event_status", "security_audit_logs", ["event_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_security_audit_logs_event_status", table_name="security_audit_logs")
    op.drop_index("ix_security_audit_logs_event_type", table_name="security_audit_logs")
    op.drop_index("ix_security_audit_logs_user_id", table_name="security_audit_logs")
    op.drop_table("security_audit_logs")

    op.drop_index("ix_device_sessions_refresh_jti_hash", table_name="device_sessions")
    op.drop_index("ix_device_sessions_session_id", table_name="device_sessions")
    op.drop_index("ix_device_sessions_user_id", table_name="device_sessions")
    op.drop_table("device_sessions")
