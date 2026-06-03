"""Subscription and entitlement scaffolding.

The current provider is deliberately mock-only. It keeps the API contract ready
for commercialization without adding a payment secret, external dependency, or
hard production assumption.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.user import SubscriptionPlan, SubscriptionStatus, User


class PlanTier(str, Enum):
    FREE = "FREE"
    PRO = "PRO"
    COACH = "COACH"


class EntitlementKey(str, Enum):
    DAILY_LOGGING = "DAILY_LOGGING"
    AI_CHAT = "AI_CHAT"
    PHOTO_RECOGNITION = "PHOTO_RECOGNITION"
    REPORT_EXPORT = "REPORT_EXPORT"
    HEALTH_METRICS = "HEALTH_METRICS"
    COACH_HANDOFF = "COACH_HANDOFF"


PLAN_FEATURES: dict[PlanTier, set[EntitlementKey]] = {
    PlanTier.FREE: {
        EntitlementKey.DAILY_LOGGING,
        EntitlementKey.AI_CHAT,
        EntitlementKey.PHOTO_RECOGNITION,
        EntitlementKey.HEALTH_METRICS,
    },
    PlanTier.PRO: {
        EntitlementKey.DAILY_LOGGING,
        EntitlementKey.AI_CHAT,
        EntitlementKey.PHOTO_RECOGNITION,
        EntitlementKey.REPORT_EXPORT,
        EntitlementKey.HEALTH_METRICS,
    },
    PlanTier.COACH: {
        EntitlementKey.DAILY_LOGGING,
        EntitlementKey.AI_CHAT,
        EntitlementKey.PHOTO_RECOGNITION,
        EntitlementKey.REPORT_EXPORT,
        EntitlementKey.HEALTH_METRICS,
        EntitlementKey.COACH_HANDOFF,
    },
}

PLAN_LIMITS: dict[PlanTier, dict[str, int | str | bool | None]] = {
    PlanTier.FREE: {
        "ai_chat_daily": 10,
        "photo_recognition_monthly": 20,
        "report_history_months": 1,
        "coach_review": False,
        "support_level": "community",
    },
    PlanTier.PRO: {
        "ai_chat_daily": 200,
        "photo_recognition_monthly": 500,
        "report_history_months": 12,
        "coach_review": False,
        "support_level": "priority",
    },
    PlanTier.COACH: {
        "ai_chat_daily": 500,
        "photo_recognition_monthly": 1000,
        "report_history_months": 24,
        "coach_review": True,
        "support_level": "coach",
    },
}

PLAN_UPGRADE_REASONS: dict[PlanTier, list[str]] = {
    PlanTier.FREE: [
        "适合验证核心记录、AI 问答和健康指标。",
        "报告导出属于付费权益，FREE 计划不包含导出能力。",
    ],
    PlanTier.PRO: [
        "面向高频记录用户，保留更长报告历史和更高识别额度。",
        "适合作为小规模灰度的主套餐。",
    ],
    PlanTier.COACH: [
        "预留真人教练协作和运营后台分层服务。",
        "需要额外的服务协议和人工运营流程后再正式放量。",
    ],
}


class EntitlementSnapshot(BaseModel):
    plan: PlanTier = PlanTier.FREE
    billing_plan: PlanTier = PlanTier.FREE
    status: SubscriptionStatus = SubscriptionStatus.INACTIVE
    provider: str = "mock"
    enforce_limits: bool = False
    enforcement_scope: str = "observe_only"
    features: dict[EntitlementKey, bool]
    limits: dict[str, int | str | bool | None] = Field(default_factory=dict)
    upgrade_reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PlanCatalogItem(BaseModel):
    plan: PlanTier
    title: str
    subtitle: str
    monthly_price_cents: int
    recommended: bool = False
    features: dict[EntitlementKey, bool]
    limits: dict[str, int | str | bool | None] = Field(default_factory=dict)
    upgrade_reasons: list[str] = Field(default_factory=list)


class CheckoutSession(BaseModel):
    provider: str = "mock"
    plan: PlanTier
    checkout_id: str
    checkout_url: str
    status: str = "mock_created"
    message: str
    local_order_id: str | None = None
    provider_order_id: str | None = None
    expires_at: datetime | None = None


class BillingLifecycleResult(BaseModel):
    provider: str = "mock"
    plan: PlanTier
    status: SubscriptionStatus
    message: str


class BillingProvider(Protocol):
    provider_name: str

    async def get_plan_for_user(self, user: User) -> PlanTier:
        ...

    async def create_checkout_session(self, user: User, plan: PlanTier) -> CheckoutSession:
        ...

    async def cancel_subscription(self, user: User) -> BillingLifecycleResult:
        ...


class MockBillingProvider:
    provider_name = "mock"

    async def get_plan_for_user(self, user: User) -> PlanTier:
        return _effective_plan_for_user(user)

    async def create_checkout_session(self, user: User, plan: PlanTier) -> CheckoutSession:
        checkout_id = f"mock_{uuid4().hex[:16]}"
        return CheckoutSession(
            plan=plan,
            checkout_id=checkout_id,
            checkout_url=f"https://billing.example.invalid/prism/mock-checkout/{checkout_id}",
            message="Mock checkout created. No real payment was initiated.",
        )

    async def cancel_subscription(self, user: User) -> BillingLifecycleResult:
        return BillingLifecycleResult(
            plan=PlanTier.FREE,
            status=SubscriptionStatus.CANCELED,
            message="Mock subscription canceled. No real payment provider was contacted.",
        )


class EntitlementService:
    def __init__(self, provider: BillingProvider | None = None, *, enforce_limits: bool | None = None):
        self.provider = provider or MockBillingProvider()
        self.enforce_limits = settings.entitlement_enforce_limits if enforce_limits is None else enforce_limits

    async def plan_catalog(self) -> list[PlanCatalogItem]:
        return build_plan_catalog()

    async def snapshot_for_user(self, user: User) -> EntitlementSnapshot:
        plan = await self.provider.get_plan_for_user(user)
        billing_plan = _persisted_plan_for_user(user)
        status = _subscription_status_from_user(user)
        features = {
            key: key in PLAN_FEATURES.get(plan, set())
            for key in EntitlementKey
        }
        return EntitlementSnapshot(
            plan=plan,
            billing_plan=billing_plan,
            status=status,
            provider=self.provider.provider_name,
            enforce_limits=self.enforce_limits,
            enforcement_scope=_enforcement_scope(self.enforce_limits),
            features=features,
            limits=PLAN_LIMITS.get(plan, {}),
            upgrade_reasons=PLAN_UPGRADE_REASONS.get(plan, []),
            notes=[
                (
                    "当前为 mock 权益模型，权益缺失会被硬拦截。"
                    if self.enforce_limits
                    else "当前为 mock 权益模型，功能权益缺失会被硬拦截，用量限制仍处于观测模式。"
                ),
                "用量限额先返回状态与计数；调用端接入硬拦截前不得宣称真实扣费或医疗服务。",
                "接入真实支付前不得写死支付密钥或真实 provider secret。",
            ],
        )

    async def ensure(self, user: User, feature: EntitlementKey) -> EntitlementSnapshot:
        snapshot = await self.snapshot_for_user(user)
        if not snapshot.features.get(feature, False):
            raise PermissionError(f"当前订阅不包含 {feature.value} 权益")
        return snapshot

    async def create_checkout_session(self, user: User, plan: PlanTier) -> CheckoutSession:
        return await self.provider.create_checkout_session(user, plan)

    async def cancel_subscription(self, user: User) -> BillingLifecycleResult:
        return await self.provider.cancel_subscription(user)


entitlement_service = EntitlementService()


def _enforcement_scope(enforce_limits: bool) -> str:
    return "feature_entitlement_gate" if enforce_limits else "observe_only"


def build_plan_catalog() -> list[PlanCatalogItem]:
    titles = {
        PlanTier.FREE: ("FREE", "基础记录、AI 问答和健康指标"),
        PlanTier.PRO: ("PRO", "小规模灰度主套餐，适合高频记录"),
        PlanTier.COACH: ("COACH", "预留真人教练协作与高触达服务"),
    }
    prices = {
        PlanTier.FREE: 0,
        PlanTier.PRO: 2900,
        PlanTier.COACH: 9900,
    }
    return [
        PlanCatalogItem(
            plan=plan,
            title=titles[plan][0],
            subtitle=titles[plan][1],
            monthly_price_cents=prices[plan],
            recommended=plan == PlanTier.PRO,
            features={key: key in PLAN_FEATURES.get(plan, set()) for key in EntitlementKey},
            limits=PLAN_LIMITS.get(plan, {}),
            upgrade_reasons=PLAN_UPGRADE_REASONS.get(plan, []),
        )
        for plan in (PlanTier.FREE, PlanTier.PRO, PlanTier.COACH)
    ]


def _coerce_subscription_plan(value: object) -> SubscriptionPlan:
    if isinstance(value, SubscriptionPlan):
        return value
    if isinstance(value, str):
        try:
            return SubscriptionPlan(value)
        except ValueError:
            return SubscriptionPlan.FREE
    return SubscriptionPlan.FREE


def _coerce_subscription_status(value: object) -> SubscriptionStatus:
    if isinstance(value, SubscriptionStatus):
        return value
    if isinstance(value, str):
        try:
            return SubscriptionStatus(value)
        except ValueError:
            return SubscriptionStatus.INACTIVE
    return SubscriptionStatus.INACTIVE


def _subscription_status_from_user(user: User) -> SubscriptionStatus:
    return _coerce_subscription_status(getattr(user, "subscription_status", None))


def _persisted_plan_for_user(user: User) -> PlanTier:
    plan = _coerce_subscription_plan(getattr(user, "subscription_plan", None))
    return PlanTier(plan.value)


def _effective_plan_for_user(user: User) -> PlanTier:
    status = _subscription_status_from_user(user)
    if status != SubscriptionStatus.ACTIVE:
        return PlanTier.FREE
    return _persisted_plan_for_user(user)
