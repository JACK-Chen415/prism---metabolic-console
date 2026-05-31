import pytest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.api.routes import billing as billing_route
from app.core.config import Settings
from app.models.user import User
from app.models.user import SubscriptionPlan, SubscriptionStatus
from app.services.billing_providers import BillingProviderStatus, billing_provider_registry
from app.services.entitlements import EntitlementKey, EntitlementService, MockBillingProvider, PlanTier, build_plan_catalog


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class FakeBillingDb:
    def __init__(self):
        self.added = []
        self.flush_count = 0
        self.execute_results = []
        self.executed = []

    def add(self, item):
        self.added.append(item)

    async def execute(self, statement):
        self.executed.append(statement)
        if not self.execute_results:
            raise AssertionError("Unexpected billing DB execute")
        return FakeScalarResult(self.execute_results.pop(0))

    async def flush(self):
        self.flush_count += 1


@contextmanager
def billing_client(user: User):
    app = FastAPI()
    app.include_router(billing_route.router, prefix="/api")
    db = FakeBillingDb()

    async def override_get_current_user():
        return user

    async def override_get_db():
        yield db

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client, db


@pytest.mark.asyncio
async def test_default_entitlement_snapshot_keeps_internal_beta_features_available():
    service = EntitlementService(provider=MockBillingProvider())
    user = User(id=1, phone="13800138000", password_hash="x")

    snapshot = await service.snapshot_for_user(user)

    assert snapshot.plan == PlanTier.FREE
    assert snapshot.billing_plan == PlanTier.FREE
    assert snapshot.status == SubscriptionStatus.INACTIVE
    assert snapshot.provider == "mock"
    assert snapshot.enforce_limits is False
    assert snapshot.enforcement_scope == 'observe_only'
    assert snapshot.features[EntitlementKey.DAILY_LOGGING] is True
    assert snapshot.features[EntitlementKey.REPORT_EXPORT] is True
    assert snapshot.features[EntitlementKey.COACH_HANDOFF] is False
    assert snapshot.limits["ai_chat_daily"] == 10
    assert snapshot.upgrade_reasons


@pytest.mark.asyncio
async def test_entitlement_snapshot_reads_active_persisted_subscription():
    service = EntitlementService(provider=MockBillingProvider())
    user = User(
        id=1,
        phone="13800138000",
        password_hash="x",
        subscription_plan=SubscriptionPlan.COACH,
        subscription_status=SubscriptionStatus.ACTIVE,
    )

    snapshot = await service.snapshot_for_user(user)

    assert snapshot.plan == PlanTier.COACH
    assert snapshot.billing_plan == PlanTier.COACH
    assert snapshot.status == SubscriptionStatus.ACTIVE
    assert snapshot.features[EntitlementKey.COACH_HANDOFF] is True
    assert snapshot.limits["coach_review"] is True


@pytest.mark.asyncio
async def test_inactive_subscription_falls_back_to_free_entitlements():
    service = EntitlementService(provider=MockBillingProvider())
    user = User(
        id=1,
        phone="13800138000",
        password_hash="x",
        subscription_plan=SubscriptionPlan.PRO,
        subscription_status=SubscriptionStatus.CANCELED,
    )

    snapshot = await service.snapshot_for_user(user)

    assert snapshot.plan == PlanTier.FREE
    assert snapshot.billing_plan == PlanTier.PRO
    assert snapshot.status == SubscriptionStatus.CANCELED
    assert snapshot.features[EntitlementKey.COACH_HANDOFF] is False


@pytest.mark.asyncio
async def test_entitlement_service_can_run_feature_gate_when_limits_are_enforced():
    service = EntitlementService(provider=MockBillingProvider(), enforce_limits=True)
    user = User(id=1, phone="13800138000", password_hash="x")

    snapshot = await service.snapshot_for_user(user)

    assert snapshot.enforce_limits is True
    assert snapshot.enforcement_scope == "feature_entitlement_gate"
    with pytest.raises(PermissionError, match="COACH_HANDOFF"):
        await service.ensure(user, EntitlementKey.COACH_HANDOFF)


@pytest.mark.asyncio
async def test_mock_checkout_never_uses_real_payment_provider():
    service = EntitlementService(provider=MockBillingProvider())
    user = User(id=1, phone="13800138000", password_hash="x")

    checkout = await service.create_checkout_session(user, PlanTier.PRO)

    assert checkout.provider == "mock"
    assert checkout.plan == PlanTier.PRO
    assert checkout.checkout_id.startswith("mock_")
    assert "example.invalid" in checkout.checkout_url


def test_mock_checkout_applies_persisted_subscription_state():
    user = User(id=1, phone="13800138000", password_hash="x")

    billing_route._apply_mock_checkout_subscription(user, PlanTier.PRO)

    assert user.subscription_plan == SubscriptionPlan.PRO
    assert user.subscription_status == SubscriptionStatus.ACTIVE
    assert user.subscription_updated_at is not None


def test_plan_catalog_exposes_mock_prices_limits_and_recommended_plan():
    catalog = build_plan_catalog()
    by_plan = {item.plan: item for item in catalog}

    assert list(by_plan) == [PlanTier.FREE, PlanTier.PRO, PlanTier.COACH]
    assert by_plan[PlanTier.FREE].monthly_price_cents == 0
    assert by_plan[PlanTier.PRO].recommended is True
    assert by_plan[PlanTier.PRO].limits["photo_recognition_monthly"] > by_plan[PlanTier.FREE].limits["photo_recognition_monthly"]
    assert by_plan[PlanTier.COACH].features[EntitlementKey.COACH_HANDOFF] is True
    assert by_plan[PlanTier.COACH].limits["coach_review"] is True


def test_billing_provider_registry_exposes_mock_and_planned_provider_without_secrets():
    providers = {item.provider: item for item in billing_provider_registry.list_providers()}

    assert providers["mock"].status == BillingProviderStatus.MOCK
    assert providers["mock"].supports_checkout is True
    assert providers["mock"].supports_cancel is True
    assert providers["mock"].requires_secret is False
    assert providers["external_gateway"].status == BillingProviderStatus.PLANNED
    assert providers["external_gateway"].requires_secret is True
    assert "api_key" not in providers["external_gateway"].description.lower()
    assert "token" not in providers["external_gateway"].description.lower()


@pytest.mark.asyncio
async def test_billing_provider_endpoint_returns_safe_configured_status_surface():
    user = User(id=1, phone="13800138000", password_hash="x")

    response = await billing_route.list_billing_providers(user)
    payload = [item.model_dump(mode="json") for item in response]
    by_provider = {item["provider"]: item for item in payload}

    assert by_provider["mock"]["is_configured"] is True
    assert by_provider["mock"]["supports_checkout"] is True
    assert by_provider["external_gateway"]["status"] == "planned"
    serialized = str(payload).lower()
    assert "api_key" not in serialized
    assert "token" not in serialized


def test_settings_reject_unknown_billing_provider_before_real_payment_is_implemented():
    with pytest.raises(ValueError, match="BILLING_PROVIDER=mock"):
        Settings(billing_provider="external_gateway")


def test_mock_subscription_cancel_preserves_paid_plan_for_audit_but_removes_active_status():
    user = User(
        id=1,
        phone="13800138000",
        password_hash="x",
        subscription_plan=SubscriptionPlan.PRO,
        subscription_status=SubscriptionStatus.ACTIVE,
    )

    billing_route._apply_mock_subscription_cancel(user)

    assert user.subscription_plan == SubscriptionPlan.PRO
    assert user.subscription_status == SubscriptionStatus.CANCELED
    assert user.subscription_updated_at is not None


def test_mock_subscription_cancel_keeps_already_canceled_paid_plan():
    user = User(
        id=1,
        phone="13800138000",
        password_hash="x",
        subscription_plan=SubscriptionPlan.COACH,
        subscription_status=SubscriptionStatus.CANCELED,
    )

    billing_route._apply_mock_subscription_cancel(user)

    assert user.subscription_plan == SubscriptionPlan.COACH
    assert user.subscription_status == SubscriptionStatus.CANCELED


def test_mock_subscription_cancel_for_free_account_resets_to_inactive_free():
    user = User(
        id=1,
        phone="13800138000",
        password_hash="x",
        subscription_plan=SubscriptionPlan.FREE,
        subscription_status=SubscriptionStatus.ACTIVE,
    )

    billing_route._apply_mock_subscription_cancel(user)

    assert user.subscription_plan == SubscriptionPlan.FREE
    assert user.subscription_status == SubscriptionStatus.INACTIVE


def test_billing_usage_response_maps_plan_limits_without_sensitive_content():
    generated = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    day_start, day_end, month_start, month_end = billing_route._usage_windows(generated)
    snapshot = billing_route.EntitlementSnapshot(
        provider="mock",
        plan=PlanTier.FREE,
        billing_plan=PlanTier.FREE,
        status=SubscriptionStatus.INACTIVE,
        enforce_limits=False,
        enforcement_scope='observe_only',
        features={},
        limits={
            "ai_chat_daily": 10,
            "photo_recognition_monthly": 20,
            "support_level": "community",
        },
        upgrade_reasons=[],
    )

    response = billing_route._build_usage_response(
        snapshot=snapshot,
        ai_chat_today=9,
        photo_recognition_month=21,
        day_start=day_start,
        day_end=day_end,
        month_start=month_start,
        month_end=month_end,
        generated_at=generated,
    )
    payload = response.model_dump(mode="json")
    by_key = {item.key: item for item in response.usage}
    serialized = str(payload)

    assert by_key["ai_chat_daily"].current == 9
    assert by_key["ai_chat_daily"].limit == 10
    assert by_key["ai_chat_daily"].remaining == 1
    assert by_key["ai_chat_daily"].usage_ratio == 0.9
    assert by_key["ai_chat_daily"].status == "near_limit"
    assert by_key["photo_recognition_monthly"].current == 21
    assert by_key["photo_recognition_monthly"].limit == 20
    assert by_key["photo_recognition_monthly"].remaining == 0
    assert by_key["photo_recognition_monthly"].status == "over_soft_limit"
    assert response.enforce_limits is False
    assert response.enforcement_scope == 'observe_only'
    assert "聊天正文" not in serialized
    assert "餐食名称" not in serialized
    assert "token" not in serialized.lower()


def test_billing_usage_route_serializes_metered_snapshot_and_audits_only_counts():
    user = User(id=1, phone="13800138000", password_hash="x")

    with billing_client(user) as (client, db):
        db.execute_results = [3, 4]
        response = client.get("/api/billing/usage")

    assert response.status_code == 200
    payload = response.json()
    by_key = {item["key"]: item for item in payload["usage"]}

    assert payload["provider"] == "mock"
    assert payload["plan"] == "FREE"
    assert payload["enforcement_scope"] == 'observe_only'
    assert payload["billing_plan"] == "FREE"
    assert by_key["ai_chat_daily"]["current"] == 3
    assert by_key["ai_chat_daily"]["limit"] == 10
    assert by_key["photo_recognition_monthly"]["current"] == 4
    assert by_key["photo_recognition_monthly"]["limit"] == 20
    assert db.flush_count >= 1
    assert db.added[-1].event_type == "billing.usage.list"
    assert db.added[-1].metadata_json["usage_keys"] == ["ai_chat_daily", "photo_recognition_monthly"]
    assert db.added[-1].metadata_json["enforcement_scope"] == "observe_only"
    serialized = str(payload) + str(db.added[-1].metadata_json)
    assert "13800138000" not in serialized
    assert "password" not in serialized.lower()


def test_billing_entitlements_route_serializes_snapshot_response():
    user = User(id=1, phone="13800138000", password_hash="x")

    with billing_client(user) as (client, db):
        response = client.get("/api/billing/entitlements")

    assert response.status_code == 200
    payload = response.json()

    assert payload["provider"] == "mock"
    assert payload["plan"] == "FREE"
    assert payload["enforcement_scope"] == 'observe_only'
    assert payload["billing_plan"] == "FREE"
    assert payload["status"] == "inactive"
    assert payload["features"]["DAILY_LOGGING"] is True
    assert payload["features"]["COACH_HANDOFF"] is False
    assert payload["notes"]


def test_billing_checkout_route_serializes_mock_session_and_updates_user():
    user = User(id=1, phone="13800138000", password_hash="x")

    with billing_client(user) as (client, db):
        response = client.post("/api/billing/checkout", json={"plan": "PRO"})

    assert response.status_code == 200
    payload = response.json()

    assert payload["provider"] == "mock"
    assert payload["plan"] == "PRO"
    assert payload["checkout_id"].startswith("mock_")
    assert "example.invalid" in payload["checkout_url"]
    assert payload["status"] == "mock_created"
    assert "No real payment" in payload["message"]
    assert user.subscription_plan == SubscriptionPlan.PRO
    assert user.subscription_status == SubscriptionStatus.ACTIVE
    assert user.subscription_updated_at is not None
    assert db.flush_count >= 2
    assert db.added[-1].metadata_json["enforcement_scope"] == "observe_only"


def test_billing_cancel_route_serializes_nested_entitlement_and_is_idempotent_for_paid_plan():
    user = User(
        id=1,
        phone="13800138000",
        password_hash="x",
        subscription_plan=SubscriptionPlan.PRO,
        subscription_status=SubscriptionStatus.CANCELED,
    )

    with billing_client(user) as (client, db):
        response = client.post("/api/billing/subscription/cancel", json={"confirm": "CANCEL_SUBSCRIPTION"})
        repeat_response = client.post("/api/billing/subscription/cancel", json={"confirm": "CANCEL_SUBSCRIPTION"})

    assert response.status_code == 200
    payload = response.json()

    assert payload["provider"] == "mock"
    assert payload["plan"] == "FREE"
    assert payload["status"] == "canceled"
    assert payload["entitlement"]["provider"] == "mock"
    assert payload["entitlement"]["plan"] == "FREE"
    assert payload["entitlement"]["billing_plan"] == "PRO"
    assert payload["entitlement"]["status"] == "canceled"
    assert payload["entitlement"]["enforcement_scope"] == "observe_only"

    assert repeat_response.status_code == 200
    repeat_payload = repeat_response.json()
    assert repeat_payload["entitlement"]["billing_plan"] == "PRO"
    assert repeat_payload["entitlement"]["status"] == "canceled"
    assert user.subscription_plan == SubscriptionPlan.PRO
    assert user.subscription_status == SubscriptionStatus.CANCELED
    assert user.subscription_updated_at is not None
    assert db.flush_count >= 4
    assert db.added[-1].metadata_json["enforcement_scope"] == "observe_only"


def test_billing_require_entitlement_route_serializes_entitlement_response():
    user = User(
        id=1,
        phone="13800138000",
        password_hash="x",
        subscription_plan=SubscriptionPlan.COACH,
        subscription_status=SubscriptionStatus.ACTIVE,
    )

    with billing_client(user) as (client, db):
        response = client.post("/api/billing/entitlements/require", json={"feature": "COACH_HANDOFF"})

    assert response.status_code == 200
    payload = response.json()

    assert payload["provider"] == "mock"
    assert payload["plan"] == "COACH"
    assert payload["billing_plan"] == "COACH"
    assert payload["enforcement_scope"] == 'observe_only'
    assert payload["status"] == "active"
    assert payload["features"]["COACH_HANDOFF"] is True
