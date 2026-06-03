import json
from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.models.billing import (
    BillingOrder,
    BillingOrderStatus,
    BillingProviderEvent,
    BillingRefund,
    BillingSubscription,
    BillingSubscriptionStatus,
)
from app.models.security import SecurityAuditLog
from app.models.user import SubscriptionPlan, SubscriptionStatus, User
from app.services import billing_service
from app.services.billing_providers import (
    BillingProviderNotReadyError,
    BillingProviderReadiness,
    BillingWebhookVerificationError,
    ProviderCheckoutResult,
    get_billing_adapter,
)
from app.services.billing_service import (
    cancel_user_subscription,
    create_checkout_order,
    process_webhook,
    refund_order,
)
from app.services.entitlements import PlanTier


class FakeResult:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class FakeDb:
    def __init__(self, execute_results=None):
        self.added = []
        self.executed = []
        self.execute_results = list(execute_results or [])
        self.flush_count = 0
        self._next_id = 1

    def add(self, item):
        if hasattr(item, "id") and getattr(item, "id", None) is None:
            setattr(item, "id", self._next_id)
            self._next_id += 1
        self.added.append(item)

    async def flush(self):
        self.flush_count += 1

    async def execute(self, statement):
        self.executed.append(statement)
        if not self.execute_results:
            raise AssertionError("Unexpected DB execute")
        return FakeResult(self.execute_results.pop(0))


class FakeReadyAdapter:
    provider_name = "wechat_pay"

    def readiness(self):
        return BillingProviderReadiness(
            provider=self.provider_name,
            mode="non_production",
            configured=True,
            webhook_configured=True,
            adapter_implementation_status="test_ready",
            price_mapping_status="configured",
            ready=True,
        )

    async def create_checkout(self, request):
        return ProviderCheckoutResult(
            checkout_id=request.local_order_id,
            checkout_url=f"https://pay.example.test/{request.local_order_id}",
            provider_order_id=f"wx_{request.local_order_id}",
            status="checkout_pending",
        )

    async def verify_webhook(self, raw_body, headers):
        raise AssertionError("not used")

    def map_event_to_transition(self, event):
        raise AssertionError("not used")

    async def cancel_order(self, provider_order_id, *, reason=None):
        raise AssertionError("not used")

    async def refund(self, request):
        raise AssertionError("not used")

    async def query(self, provider_order_id):
        raise AssertionError("not used")


def _mock_settings(**overrides):
    data = {
        "_env_file": None,
        "app_env": "development",
        "billing_provider": "mock",
        "billing_mock_webhook_secret": "mock-webhook-secret",
    }
    data.update(overrides)
    return Settings(**data)


def _paid_order():
    return BillingOrder(
        id=7,
        user_id=1,
        plan="PRO",
        provider="mock",
        local_order_id="pmc_test_order",
        provider_order_id="pmc_test_order",
        provider_payment_id="mock_payment_pmc_test_order",
        amount_minor=2900,
        currency="CNY",
        status=BillingOrderStatus.PAID.value,
    )


def _active_subscription(order_id=7):
    return BillingSubscription(
        id=8,
        user_id=1,
        current_order_id=order_id,
        plan="PRO",
        provider="mock",
        local_subscription_id="sub_test",
        provider_payment_id="mock_payment_pmc_test_order",
        amount_minor=2900,
        currency="CNY",
        status=BillingSubscriptionStatus.ACTIVE.value,
    )


def test_billing_models_expose_required_tables_and_unique_constraints():
    assert BillingOrder.__tablename__ == "billing_orders"
    assert BillingSubscription.__tablename__ == "billing_subscriptions"
    assert BillingProviderEvent.__tablename__ == "billing_provider_events"
    assert BillingRefund.__tablename__ == "billing_refunds"

    order_constraints = {constraint.name for constraint in BillingOrder.__table__.constraints}
    event_constraints = {constraint.name for constraint in BillingProviderEvent.__table__.constraints}
    refund_constraints = {constraint.name for constraint in BillingRefund.__table__.constraints}

    assert "uq_billing_orders_provider_order_id" in order_constraints
    assert "uq_billing_orders_provider_payment_id" in order_constraints
    assert "uq_billing_provider_events_provider_event_id" in event_constraints
    assert "uq_billing_refunds_out_refund_no" in refund_constraints
    assert "uq_billing_refunds_provider_refund_id" in refund_constraints


def test_wechat_pay_and_alipay_adapters_are_fail_closed_placeholders():
    for provider in ("wechat_pay", "alipay"):
        config = Settings(_env_file=None, billing_provider=provider)
        adapter = get_billing_adapter(provider, config=config)
        readiness = adapter.readiness()

        assert readiness.ready is False
        assert "billing_adapter_not_implemented" in readiness.blocking
        assert readiness.adapter_implementation_status == "blocked_placeholder_not_implemented"


@pytest.mark.asyncio
async def test_unready_real_provider_checkout_is_blocked_before_writing_db():
    config = Settings(_env_file=None, billing_provider="wechat_pay")
    db = FakeDb()
    user = User(id=1, phone="13800138000", password_hash="x")

    with pytest.raises(BillingProviderNotReadyError):
        await create_checkout_order(db, user=user, plan=PlanTier.PRO, config=config)

    assert db.added == []
    assert db.flush_count == 0


@pytest.mark.asyncio
async def test_invalid_webhook_signature_does_not_write_db():
    config = _mock_settings()
    db = FakeDb()
    body = json.dumps({"event_id": "evt_1", "event_type": "payment_success"}).encode()

    with pytest.raises(BillingWebhookVerificationError):
        await process_webhook(
            db,
            provider="mock",
            raw_body=body,
            headers={"x-prism-mock-webhook-secret": "wrong"},
            config=config,
        )

    assert db.added == []
    assert db.flush_count == 0


@pytest.mark.asyncio
async def test_duplicate_webhook_event_is_idempotent_without_repeat_side_effects():
    config = _mock_settings()
    existing = BillingProviderEvent(provider="mock", event_id="evt_dup", event_type="payment_success")
    db = FakeDb(execute_results=[existing])
    body = json.dumps(
        {
            "event_id": "evt_dup",
            "event_type": "payment_success",
            "provider_order_id": "pmc_test_order",
        }
    ).encode()

    result = await process_webhook(
        db,
        provider="mock",
        raw_body=body,
        headers={"x-prism-mock-webhook-secret": "mock-webhook-secret"},
        config=config,
    )

    assert result.status == "duplicate"
    assert result.transition_applied is False
    assert db.added == []


@pytest.mark.asyncio
async def test_verified_webhook_activates_entitlement_once():
    config = _mock_settings()
    order = BillingOrder(
        id=7,
        user_id=1,
        plan="PRO",
        provider="mock",
        local_order_id="pmc_test_order",
        provider_order_id="pmc_test_order",
        amount_minor=2900,
        currency="CNY",
        status=BillingOrderStatus.CHECKOUT_PENDING.value,
    )
    subscription = BillingSubscription(
        id=8,
        user_id=1,
        current_order_id=7,
        plan="PRO",
        provider="mock",
        local_subscription_id="sub_test",
        amount_minor=2900,
        currency="CNY",
        status=BillingSubscriptionStatus.CHECKOUT_PENDING.value,
    )
    user = User(
        id=1,
        phone="13800138000",
        password_hash="x",
        subscription_plan=SubscriptionPlan.FREE,
        subscription_status=SubscriptionStatus.INACTIVE,
    )
    db = FakeDb(execute_results=[None, order, subscription, user])
    body = json.dumps(
        {
            "event_id": "evt_paid",
            "event_type": "payment_success",
            "provider_order_id": "pmc_test_order",
            "provider_payment_id": "pay_123",
            "occurred_at": "2026-06-01T00:00:00Z",
        }
    ).encode()

    result = await process_webhook(
        db,
        provider="mock",
        raw_body=body,
        headers={"x-prism-mock-webhook-secret": "mock-webhook-secret"},
        config=config,
    )

    assert result.status == "processed"
    assert result.transition_applied is True
    assert order.status == BillingOrderStatus.PAID.value
    assert subscription.status == BillingSubscriptionStatus.ACTIVE.value
    assert user.subscription_status == SubscriptionStatus.ACTIVE
    assert user.subscription_plan == SubscriptionPlan.PRO
    assert any(isinstance(item, BillingProviderEvent) for item in db.added)
    assert any(isinstance(item, SecurityAuditLog) and item.event_type == "billing.webhook" for item in db.added)


def test_out_of_order_payment_success_cannot_revive_terminal_subscription():
    assert billing_service._should_apply_subscription_transition("canceled", "active") is False
    assert billing_service._should_apply_subscription_transition("refunded", "active") is False
    assert billing_service._should_apply_order_transition("refunded", "paid") is False


@pytest.mark.asyncio
async def test_synchronous_checkout_for_ready_real_adapter_stays_pending(monkeypatch):
    monkeypatch.setattr(billing_service, "get_billing_adapter", lambda provider, config: FakeReadyAdapter())
    config = Settings(_env_file=None, billing_provider="wechat_pay")
    db = FakeDb()
    user = User(
        id=1,
        phone="13800138000",
        password_hash="x",
        subscription_plan=SubscriptionPlan.FREE,
        subscription_status=SubscriptionStatus.INACTIVE,
    )

    session = await create_checkout_order(db, user=user, plan=PlanTier.PRO, config=config)
    order = next(item for item in db.added if isinstance(item, BillingOrder))
    subscription = next(item for item in db.added if isinstance(item, BillingSubscription))

    assert session.status == "checkout_pending"
    assert order.status == BillingOrderStatus.CHECKOUT_PENDING.value
    assert subscription.status == BillingSubscriptionStatus.CHECKOUT_PENDING.value
    assert user.subscription_status == SubscriptionStatus.INACTIVE


@pytest.mark.asyncio
async def test_mock_nonproduction_checkout_remains_available_for_internal_testing():
    config = _mock_settings(billing_mock_webhook_secret=None)
    db = FakeDb()
    user = User(id=1, phone="13800138000", password_hash="x")

    session = await create_checkout_order(db, user=user, plan=PlanTier.PRO, config=config)
    order = next(item for item in db.added if isinstance(item, BillingOrder))

    assert session.provider == "mock"
    assert "example.invalid" in session.checkout_url
    assert order.status == BillingOrderStatus.PAID.value
    assert user.subscription_status == SubscriptionStatus.ACTIVE


@pytest.mark.asyncio
async def test_cancel_and_refund_write_structured_audit():
    config = _mock_settings()
    user = User(
        id=1,
        phone="13800138000",
        password_hash="x",
        subscription_plan=SubscriptionPlan.PRO,
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    cancel_db = FakeDb(execute_results=[None])

    cancel_result = await cancel_user_subscription(cancel_db, user=user, config=config)

    assert cancel_result.provider == "mock"
    assert user.subscription_status == SubscriptionStatus.CANCELED
    assert any(
        isinstance(item, SecurityAuditLog) and item.event_type == "billing.subscription.cancel"
        for item in cancel_db.added
    )

    order = _paid_order()
    subscription = _active_subscription()
    refund_db = FakeDb(execute_results=[order, subscription])
    refund_result = await refund_order(
        refund_db,
        user=user,
        order_id=7,
        reason="operator_test_refund",
        config=config,
    )

    assert refund_result.status == "succeeded"
    assert order.status == BillingOrderStatus.REFUNDED.value
    assert subscription.status == BillingSubscriptionStatus.REFUNDED.value
    assert any(isinstance(item, BillingRefund) for item in refund_db.added)
    assert any(isinstance(item, SecurityAuditLog) and item.event_type == "billing.refund" for item in refund_db.added)
