"""Provider-neutral billing persistence models."""

from __future__ import annotations

from datetime import datetime
import enum
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class BillingProviderName(str, enum.Enum):
    MOCK = "mock"
    WECHAT_PAY = "wechat_pay"
    ALIPAY = "alipay"


class BillingOrderStatus(str, enum.Enum):
    CHECKOUT_PENDING = "checkout_pending"
    PAID = "paid"
    PAYMENT_FAILED = "payment_failed"
    CLOSED = "closed"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REFUNDED = "refunded"


class BillingSubscriptionStatus(str, enum.Enum):
    CHECKOUT_PENDING = "checkout_pending"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCEL_AT_PERIOD_END = "cancel_at_period_end"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REFUNDED = "refunded"
    PAYMENT_FAILED = "payment_failed"


class BillingRefundStatus(str, enum.Enum):
    REQUESTED = "requested"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class BillingEventProcessingStatus(str, enum.Enum):
    VERIFIED = "verified"
    PROCESSED = "processed"
    IGNORED = "ignored"
    FAILED = "failed"


def _values(enum_cls: type[enum.Enum]) -> str:
    return ", ".join(f"'{item.value}'" for item in enum_cls)


class BillingOrder(Base):
    """A user-initiated checkout order in smallest currency units."""

    __tablename__ = "billing_orders"
    __table_args__ = (
        UniqueConstraint("local_order_id", name="uq_billing_orders_local_order_id"),
        UniqueConstraint("provider_order_id", name="uq_billing_orders_provider_order_id"),
        UniqueConstraint("provider_payment_id", name="uq_billing_orders_provider_payment_id"),
        CheckConstraint("amount_minor >= 0", name="ck_billing_orders_amount_non_negative"),
        CheckConstraint("length(currency) = 3", name="ck_billing_orders_currency_iso_4217"),
        CheckConstraint(
            f"provider in ({_values(BillingProviderName)})",
            name="ck_billing_orders_provider",
        ),
        CheckConstraint(
            f"status in ({_values(BillingOrderStatus)})",
            name="ck_billing_orders_status",
        ),
        Index("ix_billing_orders_user_provider_status", "user_id", "provider", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    plan: Mapped[str] = mapped_column(String(30), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    local_order_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    provider_order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CNY", server_default="CNY", nullable=False)
    status: Mapped[str] = mapped_column(
        String(40),
        default=BillingOrderStatus.CHECKOUT_PENDING.value,
        server_default=BillingOrderStatus.CHECKOUT_PENDING.value,
        index=True,
        nullable=False,
    )
    checkout_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    provider_request_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    audit_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BillingSubscription(Base):
    """Provider-neutral subscription entitlement state."""

    __tablename__ = "billing_subscriptions"
    __table_args__ = (
        UniqueConstraint("local_subscription_id", name="uq_billing_subscriptions_local_subscription_id"),
        UniqueConstraint("provider_subscription_id", name="uq_billing_subscriptions_provider_subscription_id"),
        CheckConstraint("amount_minor >= 0", name="ck_billing_subscriptions_amount_non_negative"),
        CheckConstraint("length(currency) = 3", name="ck_billing_subscriptions_currency_iso_4217"),
        CheckConstraint(
            f"provider in ({_values(BillingProviderName)})",
            name="ck_billing_subscriptions_provider",
        ),
        CheckConstraint(
            f"status in ({_values(BillingSubscriptionStatus)})",
            name="ck_billing_subscriptions_status",
        ),
        Index("ix_billing_subscriptions_user_provider_status", "user_id", "provider", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    current_order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("billing_orders.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    plan: Mapped[str] = mapped_column(String(30), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    local_subscription_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    provider_subscription_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CNY", server_default="CNY", nullable=False)
    status: Mapped[str] = mapped_column(
        String(40),
        default=BillingSubscriptionStatus.CHECKOUT_PENDING.value,
        server_default=BillingSubscriptionStatus.CHECKOUT_PENDING.value,
        index=True,
        nullable=False,
    )
    current_period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    audit_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BillingProviderEvent(Base):
    """Verified provider webhook or reconciliation event."""

    __tablename__ = "billing_provider_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_billing_provider_events_provider_event_id"),
        CheckConstraint(
            f"provider in ({_values(BillingProviderName)})",
            name="ck_billing_provider_events_provider",
        ),
        CheckConstraint(
            f"processing_status in ({_values(BillingEventProcessingStatus)})",
            name="ck_billing_provider_events_processing_status",
        ),
        Index("ix_billing_provider_events_provider_order", "provider", "provider_order_id"),
        Index("ix_billing_provider_events_provider_payment", "provider", "provider_payment_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    provider_order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_refund_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_request_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    raw_body_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    signature_algorithm: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(40),
        default=BillingEventProcessingStatus.VERIFIED.value,
        server_default=BillingEventProcessingStatus.VERIFIED.value,
        index=True,
        nullable=False,
    )
    status_before: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    status_after: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)


class BillingRefund(Base):
    """Refund request and provider status."""

    __tablename__ = "billing_refunds"
    __table_args__ = (
        UniqueConstraint("out_refund_no", name="uq_billing_refunds_out_refund_no"),
        UniqueConstraint("provider_refund_id", name="uq_billing_refunds_provider_refund_id"),
        CheckConstraint("amount_minor > 0", name="ck_billing_refunds_amount_positive"),
        CheckConstraint("length(currency) = 3", name="ck_billing_refunds_currency_iso_4217"),
        CheckConstraint(
            f"provider in ({_values(BillingProviderName)})",
            name="ck_billing_refunds_provider",
        ),
        CheckConstraint(
            f"status in ({_values(BillingRefundStatus)})",
            name="ck_billing_refunds_status",
        ),
        Index("ix_billing_refunds_user_provider_status", "user_id", "provider", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("billing_orders.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    out_refund_no: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    provider_refund_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CNY", server_default="CNY", nullable=False)
    status: Mapped[str] = mapped_column(
        String(40),
        default=BillingRefundStatus.REQUESTED.value,
        server_default=BillingRefundStatus.REQUESTED.value,
        index=True,
        nullable=False,
    )
    reason: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    provider_request_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    requested_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    audit_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
