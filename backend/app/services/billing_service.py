"""Provider-neutral billing orchestration and state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import uuid4

from fastapi import Request
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.models.billing import (
    BillingEventProcessingStatus,
    BillingOrder,
    BillingOrderStatus,
    BillingProviderEvent,
    BillingRefund,
    BillingRefundStatus,
    BillingSubscription,
    BillingSubscriptionStatus,
)
from app.models.user import SubscriptionPlan, SubscriptionStatus, User
from app.services.auth_security import audit_security_event
from app.services.billing_providers import (
    BillingAdapter,
    BillingProviderNotReadyError,
    BillingTransition,
    ProviderCheckoutRequest,
    ProviderRefundRequest,
    VerifiedBillingEvent,
    get_billing_adapter,
)
from app.services.entitlements import BillingLifecycleResult, CheckoutSession, PlanTier


ORDER_TERMINAL_STATUSES = {
    BillingOrderStatus.CLOSED.value,
    BillingOrderStatus.CANCELED.value,
    BillingOrderStatus.EXPIRED.value,
    BillingOrderStatus.REFUNDED.value,
}
SUBSCRIPTION_TERMINAL_STATUSES = {
    BillingSubscriptionStatus.CANCELED.value,
    BillingSubscriptionStatus.EXPIRED.value,
    BillingSubscriptionStatus.REFUNDED.value,
}
NON_TERMINAL_SUBSCRIPTION_REGRESSIONS = {
    BillingSubscriptionStatus.ACTIVE.value,
    BillingSubscriptionStatus.PAST_DUE.value,
    BillingSubscriptionStatus.PAYMENT_FAILED.value,
}


@dataclass(frozen=True)
class BillingWebhookProcessResult:
    provider: str
    event_id: str
    status: str
    transition_applied: bool
    message: str


@dataclass(frozen=True)
class BillingRefundProcessResult:
    provider: str
    out_refund_no: str
    status: str
    message: str


@dataclass(frozen=True)
class BillingReconcileResult:
    provider: str
    order_id: int
    status: str
    transition_applied: bool
    message: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_provider_safe_id(prefix: str) -> str:
    return f"{prefix}{uuid4().hex}"[:32]


def _plan_price_minor(config: Settings, plan: PlanTier) -> int:
    prices = {str(key).upper(): value for key, value in config.billing_price_cny_minor_by_plan.items()}
    return int(prices.get(plan.value, 0))


def _assert_adapter_ready(adapter: BillingAdapter, *, require_webhook: bool = False) -> None:
    readiness = adapter.readiness()
    if not readiness.ready:
        detail = ", ".join(readiness.blocking) or "provider_not_ready"
        raise BillingProviderNotReadyError(f"{readiness.provider} billing provider is blocked: {detail}")
    if require_webhook and not readiness.webhook_configured:
        detail = ", ".join(readiness.webhook_gaps) or "webhook_not_configured"
        raise BillingProviderNotReadyError(f"{readiness.provider} webhook is blocked: {detail}")


def _should_apply_order_transition(current: str, incoming: str | None) -> bool:
    if not incoming or incoming == current:
        return False
    if current in ORDER_TERMINAL_STATUSES and incoming in {
        BillingOrderStatus.PAID.value,
        BillingOrderStatus.PAYMENT_FAILED.value,
    }:
        return False
    if current == BillingOrderStatus.REFUNDED.value and incoming != BillingOrderStatus.REFUNDED.value:
        return False
    return True


def _should_apply_subscription_transition(current: str, incoming: str | None) -> bool:
    if not incoming or incoming == current:
        return False
    if current in SUBSCRIPTION_TERMINAL_STATUSES and incoming in NON_TERMINAL_SUBSCRIPTION_REGRESSIONS:
        return False
    if current == BillingSubscriptionStatus.REFUNDED.value and incoming != BillingSubscriptionStatus.REFUNDED.value:
        return False
    return True


def _coerce_user_plan(plan: str) -> SubscriptionPlan:
    try:
        return SubscriptionPlan(plan)
    except ValueError:
        return SubscriptionPlan.FREE


def _project_subscription_to_user(user: User, subscription: BillingSubscription, now: datetime) -> None:
    user.subscription_plan = _coerce_user_plan(subscription.plan)
    if subscription.status == BillingSubscriptionStatus.ACTIVE.value:
        user.subscription_status = SubscriptionStatus.ACTIVE
    elif subscription.status in {
        BillingSubscriptionStatus.PAYMENT_FAILED.value,
        BillingSubscriptionStatus.PAST_DUE.value,
        BillingSubscriptionStatus.CHECKOUT_PENDING.value,
    }:
        user.subscription_status = SubscriptionStatus.INACTIVE
    else:
        user.subscription_status = SubscriptionStatus.CANCELED
    user.subscription_updated_at = now


async def create_checkout_order(
    db: AsyncSession,
    *,
    user: User,
    plan: PlanTier,
    request: Request | None = None,
    config: Settings = settings,
    activate_mock_compat: bool = True,
) -> CheckoutSession:
    """Create a provider checkout and local pending billing records."""
    if plan == PlanTier.FREE:
        raise ValueError("FREE plan does not require checkout")

    adapter = get_billing_adapter(config.billing_provider, config=config)
    _assert_adapter_ready(adapter)

    amount_minor = _plan_price_minor(config, plan)
    if amount_minor <= 0:
        raise ValueError(f"plan {plan.value} is missing a positive price mapping")

    local_order_id = _new_provider_safe_id("pmc")
    local_subscription_id = _new_provider_safe_id("sub")
    now = _utcnow()
    checkout_request = ProviderCheckoutRequest(
        user_id=user.id,
        plan=plan.value,
        amount_minor=amount_minor,
        currency=config.billing_currency,
        local_order_id=local_order_id,
        description=f"Prism {plan.value} monthly subscription",
        metadata={"source": "user_checkout"},
    )
    order = BillingOrder(
        user_id=user.id,
        plan=plan.value,
        provider=adapter.provider_name,
        local_order_id=local_order_id,
        amount_minor=amount_minor,
        currency=config.billing_currency,
        status=BillingOrderStatus.CHECKOUT_PENDING.value,
        metadata_json={"source": "checkout"},
        audit_json={"created_by": "user", "reason": "checkout"},
    )
    db.add(order)
    await db.flush()
    subscription = BillingSubscription(
        user_id=user.id,
        current_order_id=order.id,
        plan=plan.value,
        provider=adapter.provider_name,
        local_subscription_id=local_subscription_id,
        amount_minor=amount_minor,
        currency=config.billing_currency,
        status=BillingSubscriptionStatus.CHECKOUT_PENDING.value,
        metadata_json={"source": "checkout"},
        audit_json={"created_by": "user", "reason": "checkout"},
    )
    db.add(subscription)
    await db.flush()

    provider_result = await adapter.create_checkout(checkout_request)
    order.provider_order_id = provider_result.provider_order_id
    order.checkout_url = provider_result.checkout_url
    order.provider_request_id = provider_result.provider_request_id
    order.expires_at = provider_result.expires_at

    if adapter.provider_name == "mock" and activate_mock_compat:
        order.status = BillingOrderStatus.PAID.value
        order.provider_payment_id = f"mock_payment_{local_order_id}"
        order.paid_at = now
        subscription.status = BillingSubscriptionStatus.ACTIVE.value
        subscription.provider_payment_id = order.provider_payment_id
        subscription.activated_at = now
        subscription.current_period_start = now
        subscription.current_period_end = now + timedelta(days=30)
        _project_subscription_to_user(user, subscription, now)

    await db.flush()
    await audit_security_event(
        db,
        event_type="billing.checkout",
        event_status="success",
        user_id=user.id,
        request=request,
        route_name="/api/billing/checkout",
        metadata={
            "provider": adapter.provider_name,
            "plan": plan.value,
            "local_order_id": local_order_id,
            "provider_order_id": order.provider_order_id,
            "status": order.status,
            "amount_minor": amount_minor,
            "currency": config.billing_currency,
            "provider_request_id": provider_result.provider_request_id,
            "mock_compat_activation": adapter.provider_name == "mock" and activate_mock_compat,
        },
    )
    checkout_status = (
        provider_result.status
        if adapter.provider_name == "mock"
        else BillingOrderStatus.CHECKOUT_PENDING.value
    )
    return CheckoutSession(
        provider=adapter.provider_name,
        plan=plan,
        checkout_id=provider_result.checkout_id,
        checkout_url=provider_result.checkout_url,
        status=checkout_status,
        message=provider_result.message,
        local_order_id=local_order_id,
        provider_order_id=order.provider_order_id,
        expires_at=provider_result.expires_at,
    )


async def _find_existing_event(
    db: AsyncSession,
    *,
    provider: str,
    event_id: str,
) -> BillingProviderEvent | None:
    result = await db.execute(
        select(BillingProviderEvent).where(
            BillingProviderEvent.provider == provider,
            BillingProviderEvent.event_id == event_id,
        )
    )
    return result.scalar_one_or_none()


async def _find_order_for_event(db: AsyncSession, event: VerifiedBillingEvent) -> BillingOrder | None:
    predicates = []
    if event.provider_order_id:
        predicates.append(BillingOrder.provider_order_id == event.provider_order_id)
        predicates.append(BillingOrder.local_order_id == event.provider_order_id)
    if event.provider_payment_id:
        predicates.append(BillingOrder.provider_payment_id == event.provider_payment_id)
    if not predicates:
        return None
    result = await db.execute(
        select(BillingOrder)
        .where(BillingOrder.provider == event.provider, or_(*predicates))
        .order_by(desc(BillingOrder.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _find_subscription_for_order(db: AsyncSession, order: BillingOrder) -> BillingSubscription | None:
    predicates = []
    if order.id is not None:
        predicates.append(BillingSubscription.current_order_id == order.id)
    if order.user_id is not None:
        predicates.append(BillingSubscription.user_id == order.user_id)
    if not predicates:
        return None
    result = await db.execute(
        select(BillingSubscription)
        .where(
            BillingSubscription.provider == order.provider,
            BillingSubscription.plan == order.plan,
            or_(*predicates),
        )
        .order_by(desc(BillingSubscription.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _find_user(db: AsyncSession, user_id: int | None) -> User | None:
    if user_id is None:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def _apply_transition(
    db: AsyncSession,
    *,
    event_row: BillingProviderEvent,
    event: VerifiedBillingEvent,
    transition: BillingTransition,
) -> bool:
    now = _utcnow()
    order = await _find_order_for_event(db, event)
    if order is None:
        event_row.processing_status = BillingEventProcessingStatus.IGNORED.value
        event_row.processed_at = now
        event_row.metadata_json = {
            **(event_row.metadata_json or {}),
            "ignore_reason": "order_not_found",
            "transition_reason": transition.reason,
        }
        await db.flush()
        return False

    subscription = await _find_subscription_for_order(db, order)
    if subscription is None:
        subscription = BillingSubscription(
            user_id=order.user_id,
            current_order_id=order.id,
            plan=event.plan or order.plan,
            provider=order.provider,
            local_subscription_id=_new_provider_safe_id("sub"),
            amount_minor=order.amount_minor,
            currency=order.currency,
            status=BillingSubscriptionStatus.CHECKOUT_PENDING.value,
            metadata_json={"source": "provider_event"},
        )
        db.add(subscription)
        await db.flush()

    status_before = f"order:{order.status};subscription:{subscription.status}"
    applied = False
    if event.provider_payment_id and not order.provider_payment_id:
        order.provider_payment_id = event.provider_payment_id
    if event.provider_payment_id and not subscription.provider_payment_id:
        subscription.provider_payment_id = event.provider_payment_id

    if _should_apply_order_transition(order.status, transition.order_status):
        order.status = transition.order_status or order.status
        applied = True
        if order.status == BillingOrderStatus.PAID.value:
            order.paid_at = event.occurred_at or now
        if order.status in ORDER_TERMINAL_STATUSES:
            order.closed_at = event.occurred_at or now

    if _should_apply_subscription_transition(subscription.status, transition.subscription_status):
        subscription.status = transition.subscription_status or subscription.status
        applied = True
        if subscription.status == BillingSubscriptionStatus.ACTIVE.value:
            subscription.activated_at = event.occurred_at or now
            subscription.current_period_start = event.occurred_at or now
            subscription.current_period_end = (event.occurred_at or now) + timedelta(days=30)
        if subscription.status == BillingSubscriptionStatus.CANCEL_AT_PERIOD_END.value:
            subscription.cancel_at_period_end = True
        if subscription.status in SUBSCRIPTION_TERMINAL_STATUSES:
            subscription.canceled_at = event.occurred_at or now
            subscription.cancel_at_period_end = False

    user = await _find_user(db, order.user_id)
    if user is not None and applied:
        _project_subscription_to_user(user, subscription, now)

    event_row.status_before = status_before
    event_row.status_after = f"order:{order.status};subscription:{subscription.status}"
    event_row.processing_status = (
        BillingEventProcessingStatus.PROCESSED.value if applied else BillingEventProcessingStatus.IGNORED.value
    )
    event_row.processed_at = now
    event_row.metadata_json = {
        **(event_row.metadata_json or {}),
        "transition_reason": transition.reason,
        "order_id": order.id,
        "subscription_id": subscription.id,
        "applied": applied,
    }
    await db.flush()
    return applied


async def _persist_and_apply_event(
    db: AsyncSession,
    *,
    adapter: BillingAdapter,
    event: VerifiedBillingEvent,
    raw_body_sha256: str | None = None,
    request: Request | None = None,
    route_name: str,
    audit_event_type: str,
) -> BillingWebhookProcessResult:
    existing = await _find_existing_event(db, provider=event.provider, event_id=event.event_id)
    if existing is not None:
        return BillingWebhookProcessResult(
            provider=event.provider,
            event_id=event.event_id,
            status="duplicate",
            transition_applied=False,
            message="Duplicate billing provider event ignored idempotently.",
        )

    transition = adapter.map_event_to_transition(event)
    event_row = BillingProviderEvent(
        provider=event.provider,
        event_id=event.event_id,
        event_type=event.event_type,
        resource_type=event.resource_type,
        provider_order_id=event.provider_order_id,
        provider_payment_id=event.provider_payment_id,
        provider_refund_id=event.provider_refund_id,
        provider_request_id=event.provider_request_id,
        raw_body_sha256=raw_body_sha256 or event.raw_body_sha256,
        signature_algorithm=event.signature_algorithm,
        processing_status=BillingEventProcessingStatus.VERIFIED.value,
        occurred_at=event.occurred_at,
        metadata_json={
            "event_metadata": event.metadata,
            "transition_reason": transition.reason,
        },
    )
    db.add(event_row)
    await db.flush()
    applied = await _apply_transition(db, event_row=event_row, event=event, transition=transition)
    await audit_security_event(
        db,
        event_type=audit_event_type,
        event_status=event_row.processing_status,
        user_id=None,
        request=request,
        route_name=route_name,
        metadata={
            "provider": event.provider,
            "event_id": event.event_id,
            "event_type": event.event_type,
            "provider_order_id": event.provider_order_id,
            "provider_payment_id": event.provider_payment_id,
            "provider_refund_id": event.provider_refund_id,
            "provider_request_id": event.provider_request_id,
            "processing_status": event_row.processing_status,
            "transition_applied": applied,
        },
    )
    return BillingWebhookProcessResult(
        provider=event.provider,
        event_id=event.event_id,
        status=event_row.processing_status,
        transition_applied=applied,
        message="Billing provider event processed." if applied else "Billing provider event verified but ignored.",
    )


async def process_webhook(
    db: AsyncSession,
    *,
    provider: str,
    raw_body: bytes,
    headers: Mapping[str, str],
    request: Request | None = None,
    config: Settings = settings,
) -> BillingWebhookProcessResult:
    adapter = get_billing_adapter(provider, config=config)
    _assert_adapter_ready(adapter, require_webhook=True)
    event = await adapter.verify_webhook(raw_body, headers)
    return await _persist_and_apply_event(
        db,
        adapter=adapter,
        event=event,
        raw_body_sha256=event.raw_body_sha256,
        request=request,
        route_name=f"/api/billing/webhooks/{adapter.provider_name}",
        audit_event_type="billing.webhook",
    )


async def cancel_user_subscription(
    db: AsyncSession,
    *,
    user: User,
    request: Request | None = None,
    reason: str = "user_cancel",
    config: Settings = settings,
) -> BillingLifecycleResult:
    adapter = get_billing_adapter(config.billing_provider, config=config)
    _assert_adapter_ready(adapter)
    previous_plan = getattr(user.subscription_plan, "value", user.subscription_plan)
    previous_status = getattr(user.subscription_status, "value", user.subscription_status)
    provider_order_id = None
    result = await db.execute(
        select(BillingSubscription)
        .where(
            BillingSubscription.user_id == user.id,
            BillingSubscription.provider == adapter.provider_name,
        )
        .order_by(desc(BillingSubscription.created_at))
        .limit(1)
    )
    subscription = result.scalar_one_or_none()
    order = None
    if subscription and subscription.current_order_id is not None:
        order_result = await db.execute(select(BillingOrder).where(BillingOrder.id == subscription.current_order_id))
        order = order_result.scalar_one_or_none()
        provider_order_id = order.provider_order_id if order else None

    if provider_order_id:
        await adapter.cancel_order(provider_order_id, reason=reason)

    now = _utcnow()
    if subscription is not None:
        subscription.status = BillingSubscriptionStatus.CANCELED.value
        subscription.canceled_at = now
        subscription.cancel_at_period_end = False
    if order is not None and order.status not in {BillingOrderStatus.REFUNDED.value, BillingOrderStatus.CANCELED.value}:
        order.status = BillingOrderStatus.CANCELED.value
        order.closed_at = now
    if previous_plan == SubscriptionPlan.FREE.value:
        user.subscription_plan = SubscriptionPlan.FREE
        user.subscription_status = SubscriptionStatus.INACTIVE
    else:
        user.subscription_status = SubscriptionStatus.CANCELED
    user.subscription_updated_at = now
    await db.flush()
    await audit_security_event(
        db,
        event_type="billing.subscription.cancel",
        event_status="success",
        user_id=user.id,
        request=request,
        route_name="/api/billing/subscription/cancel",
        metadata={
            "provider": adapter.provider_name,
            "previous_plan": previous_plan,
            "previous_status": previous_status,
            "billing_plan": getattr(user.subscription_plan, "value", user.subscription_plan),
            "status": getattr(user.subscription_status, "value", user.subscription_status),
            "provider_order_id": provider_order_id,
            "reason": reason,
        },
    )
    return BillingLifecycleResult(
        provider=adapter.provider_name,
        plan=PlanTier.FREE,
        status=user.subscription_status,
        message="Subscription cancellation recorded. No future entitlement will be activated without a verified payment.",
    )


async def refund_order(
    db: AsyncSession,
    *,
    user: User,
    order_id: int,
    amount_minor: int | None = None,
    reason: str | None = None,
    request: Request | None = None,
    config: Settings = settings,
) -> BillingRefundProcessResult:
    adapter = get_billing_adapter(config.billing_provider, config=config)
    _assert_adapter_ready(adapter)
    result = await db.execute(
        select(BillingOrder).where(
            BillingOrder.id == order_id,
            BillingOrder.user_id == user.id,
            BillingOrder.provider == adapter.provider_name,
        )
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise ValueError("billing order not found")
    if not order.provider_payment_id:
        raise ValueError("billing order has no provider payment id to refund")

    refund_amount = amount_minor or order.amount_minor
    if refund_amount <= 0 or refund_amount > order.amount_minor:
        raise ValueError("refund amount is invalid")

    out_refund_no = _new_provider_safe_id("rf")
    refund = BillingRefund(
        user_id=user.id,
        order_id=order.id,
        provider=adapter.provider_name,
        out_refund_no=out_refund_no,
        provider_payment_id=order.provider_payment_id,
        amount_minor=refund_amount,
        currency=order.currency,
        status=BillingRefundStatus.REQUESTED.value,
        reason=reason,
        requested_by_user_id=user.id,
        metadata_json={"source": "user_refund_request"},
    )
    db.add(refund)
    await db.flush()
    provider_result = await adapter.refund(
        ProviderRefundRequest(
            provider_payment_id=order.provider_payment_id,
            out_refund_no=out_refund_no,
            amount_minor=refund_amount,
            currency=order.currency,
            reason=reason,
        )
    )
    refund.provider_refund_id = provider_result.provider_refund_id
    refund.provider_request_id = provider_result.provider_request_id
    refund.status = provider_result.status
    if provider_result.status == BillingRefundStatus.SUCCEEDED.value:
        order.status = BillingOrderStatus.REFUNDED.value
        order.closed_at = _utcnow()
        subscription = await _find_subscription_for_order(db, order)
        if subscription is not None:
            subscription.status = BillingSubscriptionStatus.REFUNDED.value
            subscription.canceled_at = _utcnow()
            _project_subscription_to_user(user, subscription, _utcnow())
    await db.flush()
    await audit_security_event(
        db,
        event_type="billing.refund",
        event_status="success",
        user_id=user.id,
        request=request,
        route_name=f"/api/billing/orders/{order_id}/refunds",
        metadata={
            "provider": adapter.provider_name,
            "order_id": order_id,
            "out_refund_no": out_refund_no,
            "provider_refund_id": provider_result.provider_refund_id,
            "provider_payment_id": order.provider_payment_id,
            "amount_minor": refund_amount,
            "currency": order.currency,
            "status": refund.status,
            "reason": reason,
        },
    )
    return BillingRefundProcessResult(
        provider=adapter.provider_name,
        out_refund_no=out_refund_no,
        status=refund.status,
        message=provider_result.message,
    )


async def reconcile_order(
    db: AsyncSession,
    *,
    user: User,
    order_id: int,
    request: Request | None = None,
    config: Settings = settings,
) -> BillingReconcileResult:
    adapter = get_billing_adapter(config.billing_provider, config=config)
    _assert_adapter_ready(adapter)
    result = await db.execute(
        select(BillingOrder).where(
            BillingOrder.id == order_id,
            BillingOrder.user_id == user.id,
            BillingOrder.provider == adapter.provider_name,
        )
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise ValueError("billing order not found")
    provider_order_id = order.provider_order_id or order.local_order_id
    provider_result = await adapter.query(provider_order_id)
    if provider_result.event is None:
        return BillingReconcileResult(
            provider=adapter.provider_name,
            order_id=order_id,
            status=provider_result.status,
            transition_applied=False,
            message="Provider query returned no transition event.",
        )
    process_result = await _persist_and_apply_event(
        db,
        adapter=adapter,
        event=provider_result.event,
        request=request,
        route_name=f"/api/billing/orders/{order_id}/reconcile",
        audit_event_type="billing.reconcile",
    )
    return BillingReconcileResult(
        provider=adapter.provider_name,
        order_id=order_id,
        status=process_result.status,
        transition_applied=process_result.transition_applied,
        message=process_result.message,
    )
