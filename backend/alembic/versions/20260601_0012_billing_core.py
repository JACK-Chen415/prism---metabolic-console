"""provider neutral billing core

Revision ID: 20260601_0012
Revises: 20260530_0011
Create Date: 2026-06-01 09:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260601_0012"
down_revision = "20260530_0011"
branch_labels = None
depends_on = None


PROVIDERS = "'mock', 'wechat_pay', 'alipay'"
ORDER_STATUSES = "'checkout_pending', 'paid', 'payment_failed', 'closed', 'canceled', 'expired', 'refunded'"
SUBSCRIPTION_STATUSES = (
    "'checkout_pending', 'active', 'past_due', 'cancel_at_period_end', "
    "'canceled', 'expired', 'refunded', 'payment_failed'"
)
EVENT_PROCESSING_STATUSES = "'verified', 'processed', 'ignored', 'failed'"
REFUND_STATUSES = "'requested', 'processing', 'succeeded', 'failed', 'canceled'"


def upgrade() -> None:
    op.create_table(
        "billing_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("plan", sa.String(length=30), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("local_order_id", sa.String(length=80), nullable=False),
        sa.Column("provider_order_id", sa.String(length=128), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="CNY"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="checkout_pending"),
        sa.Column("checkout_url", sa.String(length=1000), nullable=True),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("audit_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("local_order_id", name="uq_billing_orders_local_order_id"),
        sa.UniqueConstraint("provider_order_id", name="uq_billing_orders_provider_order_id"),
        sa.UniqueConstraint("provider_payment_id", name="uq_billing_orders_provider_payment_id"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_billing_orders_amount_non_negative"),
        sa.CheckConstraint("length(currency) = 3", name="ck_billing_orders_currency_iso_4217"),
        sa.CheckConstraint(f"provider in ({PROVIDERS})", name="ck_billing_orders_provider"),
        sa.CheckConstraint(f"status in ({ORDER_STATUSES})", name="ck_billing_orders_status"),
    )
    op.create_index("ix_billing_orders_user_id", "billing_orders", ["user_id"], unique=False)
    op.create_index("ix_billing_orders_provider", "billing_orders", ["provider"], unique=False)
    op.create_index("ix_billing_orders_local_order_id", "billing_orders", ["local_order_id"], unique=False)
    op.create_index("ix_billing_orders_status", "billing_orders", ["status"], unique=False)
    op.create_index(
        "ix_billing_orders_user_provider_status",
        "billing_orders",
        ["user_id", "provider", "status"],
        unique=False,
    )

    op.create_table(
        "billing_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("current_order_id", sa.Integer(), nullable=True),
        sa.Column("plan", sa.String(length=30), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("local_subscription_id", sa.String(length=80), nullable=False),
        sa.Column("provider_subscription_id", sa.String(length=128), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="CNY"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="checkout_pending"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("audit_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["current_order_id"], ["billing_orders.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("local_subscription_id", name="uq_billing_subscriptions_local_subscription_id"),
        sa.UniqueConstraint("provider_subscription_id", name="uq_billing_subscriptions_provider_subscription_id"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_billing_subscriptions_amount_non_negative"),
        sa.CheckConstraint("length(currency) = 3", name="ck_billing_subscriptions_currency_iso_4217"),
        sa.CheckConstraint(f"provider in ({PROVIDERS})", name="ck_billing_subscriptions_provider"),
        sa.CheckConstraint(f"status in ({SUBSCRIPTION_STATUSES})", name="ck_billing_subscriptions_status"),
    )
    op.create_index("ix_billing_subscriptions_user_id", "billing_subscriptions", ["user_id"], unique=False)
    op.create_index("ix_billing_subscriptions_current_order_id", "billing_subscriptions", ["current_order_id"], unique=False)
    op.create_index("ix_billing_subscriptions_provider", "billing_subscriptions", ["provider"], unique=False)
    op.create_index("ix_billing_subscriptions_local_subscription_id", "billing_subscriptions", ["local_subscription_id"], unique=False)
    op.create_index("ix_billing_subscriptions_status", "billing_subscriptions", ["status"], unique=False)
    op.create_index(
        "ix_billing_subscriptions_user_provider_status",
        "billing_subscriptions",
        ["user_id", "provider", "status"],
        unique=False,
    )

    op.create_table(
        "billing_provider_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=60), nullable=True),
        sa.Column("provider_order_id", sa.String(length=128), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=True),
        sa.Column("provider_refund_id", sa.String(length=128), nullable=True),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("raw_body_sha256", sa.String(length=64), nullable=True),
        sa.Column("signature_algorithm", sa.String(length=80), nullable=True),
        sa.Column("processing_status", sa.String(length=40), nullable=False, server_default="verified"),
        sa.Column("status_before", sa.String(length=40), nullable=True),
        sa.Column("status_after", sa.String(length=40), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.UniqueConstraint("provider", "event_id", name="uq_billing_provider_events_provider_event_id"),
        sa.CheckConstraint(f"provider in ({PROVIDERS})", name="ck_billing_provider_events_provider"),
        sa.CheckConstraint(
            f"processing_status in ({EVENT_PROCESSING_STATUSES})",
            name="ck_billing_provider_events_processing_status",
        ),
    )
    op.create_index("ix_billing_provider_events_provider", "billing_provider_events", ["provider"], unique=False)
    op.create_index("ix_billing_provider_events_processing_status", "billing_provider_events", ["processing_status"], unique=False)
    op.create_index(
        "ix_billing_provider_events_provider_order",
        "billing_provider_events",
        ["provider", "provider_order_id"],
        unique=False,
    )
    op.create_index(
        "ix_billing_provider_events_provider_payment",
        "billing_provider_events",
        ["provider", "provider_payment_id"],
        unique=False,
    )

    op.create_table(
        "billing_refunds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("out_refund_no", sa.String(length=80), nullable=False),
        sa.Column("provider_refund_id", sa.String(length=128), nullable=True),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="CNY"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="requested"),
        sa.Column("reason", sa.String(length=240), nullable=True),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("audit_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["billing_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("out_refund_no", name="uq_billing_refunds_out_refund_no"),
        sa.UniqueConstraint("provider_refund_id", name="uq_billing_refunds_provider_refund_id"),
        sa.CheckConstraint("amount_minor > 0", name="ck_billing_refunds_amount_positive"),
        sa.CheckConstraint("length(currency) = 3", name="ck_billing_refunds_currency_iso_4217"),
        sa.CheckConstraint(f"provider in ({PROVIDERS})", name="ck_billing_refunds_provider"),
        sa.CheckConstraint(f"status in ({REFUND_STATUSES})", name="ck_billing_refunds_status"),
    )
    op.create_index("ix_billing_refunds_user_id", "billing_refunds", ["user_id"], unique=False)
    op.create_index("ix_billing_refunds_order_id", "billing_refunds", ["order_id"], unique=False)
    op.create_index("ix_billing_refunds_provider", "billing_refunds", ["provider"], unique=False)
    op.create_index("ix_billing_refunds_out_refund_no", "billing_refunds", ["out_refund_no"], unique=False)
    op.create_index("ix_billing_refunds_status", "billing_refunds", ["status"], unique=False)
    op.create_index(
        "ix_billing_refunds_user_provider_status",
        "billing_refunds",
        ["user_id", "provider", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_billing_refunds_user_provider_status", table_name="billing_refunds")
    op.drop_index("ix_billing_refunds_status", table_name="billing_refunds")
    op.drop_index("ix_billing_refunds_out_refund_no", table_name="billing_refunds")
    op.drop_index("ix_billing_refunds_provider", table_name="billing_refunds")
    op.drop_index("ix_billing_refunds_order_id", table_name="billing_refunds")
    op.drop_index("ix_billing_refunds_user_id", table_name="billing_refunds")
    op.drop_table("billing_refunds")

    op.drop_index("ix_billing_provider_events_provider_payment", table_name="billing_provider_events")
    op.drop_index("ix_billing_provider_events_provider_order", table_name="billing_provider_events")
    op.drop_index("ix_billing_provider_events_processing_status", table_name="billing_provider_events")
    op.drop_index("ix_billing_provider_events_provider", table_name="billing_provider_events")
    op.drop_table("billing_provider_events")

    op.drop_index("ix_billing_subscriptions_user_provider_status", table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_status", table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_local_subscription_id", table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_provider", table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_current_order_id", table_name="billing_subscriptions")
    op.drop_index("ix_billing_subscriptions_user_id", table_name="billing_subscriptions")
    op.drop_table("billing_subscriptions")

    op.drop_index("ix_billing_orders_user_provider_status", table_name="billing_orders")
    op.drop_index("ix_billing_orders_status", table_name="billing_orders")
    op.drop_index("ix_billing_orders_local_order_id", table_name="billing_orders")
    op.drop_index("ix_billing_orders_provider", table_name="billing_orders")
    op.drop_index("ix_billing_orders_user_id", table_name="billing_orders")
    op.drop_table("billing_orders")
