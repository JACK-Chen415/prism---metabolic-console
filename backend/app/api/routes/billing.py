"""Mock billing and entitlement API routes."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.services.auth_security import audit_security_event
from app.models.chat import ChatMessage, ChatSession, MessageRole
from app.models.meal import Meal, MealSource
from app.models.user import SubscriptionPlan, SubscriptionStatus, User
from app.services.billing_providers import (
    BillingProviderError,
    BillingProviderKind,
    BillingProviderNotReadyError,
    BillingProviderStatus,
    BillingWebhookVerificationError,
    billing_provider_registry,
    get_billing_adapter,
    normalize_billing_provider,
)
from app.services.billing_service import (
    cancel_user_subscription,
    create_checkout_order,
    process_webhook,
    reconcile_order,
    refund_order,
)
from app.services.entitlements import CheckoutSession, EntitlementKey, EntitlementSnapshot, PlanCatalogItem, PlanTier, entitlement_service


router = APIRouter(prefix="/billing", tags=["订阅与权益"])


class CheckoutRequest(BaseModel):
    plan: PlanTier = PlanTier.PRO


class EntitlementRequireRequest(BaseModel):
    feature: EntitlementKey


class CancelSubscriptionRequest(BaseModel):
    confirm: str


class RefundRequest(BaseModel):
    amount_minor: int | None = None
    reason: str | None = None


class CheckoutResponse(BaseModel):
    provider: str
    plan: PlanTier
    checkout_id: str
    checkout_url: str
    status: str
    message: str
    local_order_id: str | None = None
    provider_order_id: str | None = None
    expires_at: datetime | None = None


class EntitlementResponse(BaseModel):
    provider: str
    plan: PlanTier
    billing_plan: PlanTier
    status: SubscriptionStatus
    enforce_limits: bool
    enforcement_scope: str
    features: dict[EntitlementKey, bool]
    limits: dict[str, int | str | bool | None]
    upgrade_reasons: list[str]
    notes: list[str]


class BillingProviderResponse(BaseModel):
    provider: str
    display_name: str
    kind: BillingProviderKind
    status: BillingProviderStatus
    description: str
    supports_checkout: bool
    supports_cancel: bool
    supports_webhook: bool
    supports_refund: bool
    requires_secret: bool
    is_configured: bool
    readiness: dict[str, Any]


class SubscriptionLifecycleResponse(BaseModel):
    provider: str
    plan: PlanTier
    status: SubscriptionStatus
    message: str
    entitlement: EntitlementResponse


class BillingWebhookResponse(BaseModel):
    provider: str
    event_id: str
    status: str
    transition_applied: bool
    message: str


class BillingRefundResponse(BaseModel):
    provider: str
    out_refund_no: str
    status: str
    message: str


class BillingReconcileResponse(BaseModel):
    provider: str
    order_id: int
    status: str
    transition_applied: bool
    message: str


class UsageQuotaItem(BaseModel):
    key: str
    label: str
    current: int
    limit: int | None
    remaining: int | None
    usage_ratio: float | None
    period: str
    period_start: datetime
    period_end: datetime
    enforce_limits: bool
    status: str


class BillingUsageResponse(BaseModel):
    generated_at: datetime
    provider: str
    plan: PlanTier
    billing_plan: PlanTier
    subscription_status: SubscriptionStatus
    enforce_limits: bool
    enforcement_scope: str
    usage: list[UsageQuotaItem]
    notes: list[str]


USAGE_LABELS = {
    "ai_chat_daily": "每日 AI 对话",
    "photo_recognition_monthly": "每月拍照识别",
}


def _entitlement_response(snapshot: EntitlementSnapshot) -> EntitlementResponse:
    return EntitlementResponse.model_validate(snapshot.model_dump())


def _checkout_response(session: CheckoutSession) -> CheckoutResponse:
    return CheckoutResponse.model_validate(session.model_dump())


def _numeric_limit(snapshot: EntitlementSnapshot, key: str) -> int | None:
    value = snapshot.limits.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def _usage_status(*, current: int, limit: int | None, enforce_limits: bool) -> str:
    if limit is None:
        return "unmetered"
    if current >= limit:
        return "blocked" if enforce_limits else "over_soft_limit"
    if current >= max(1, int(limit * 0.8)):
        return "near_limit"
    return "ok"


def _usage_item(
    *,
    snapshot: EntitlementSnapshot,
    key: str,
    current: int,
    period: str,
    period_start: datetime,
    period_end: datetime,
) -> UsageQuotaItem:
    limit = _numeric_limit(snapshot, key)
    remaining = max(0, limit - current) if limit is not None else None
    ratio = round(current / limit, 4) if limit else None
    return UsageQuotaItem(
        key=key,
        label=USAGE_LABELS.get(key, key),
        current=current,
        limit=limit,
        remaining=remaining,
        usage_ratio=ratio,
        period=period,
        period_start=period_start,
        period_end=period_end,
        enforce_limits=snapshot.enforce_limits,
        status=_usage_status(current=current, limit=limit, enforce_limits=snapshot.enforce_limits),
    )


def _build_usage_response(
    *,
    snapshot: EntitlementSnapshot,
    ai_chat_today: int,
    photo_recognition_month: int,
    day_start: datetime,
    day_end: datetime,
    month_start: datetime,
    month_end: datetime,
    generated_at: datetime | None = None,
) -> BillingUsageResponse:
    return BillingUsageResponse(
        generated_at=generated_at or datetime.now(timezone.utc),
        provider=snapshot.provider,
        plan=snapshot.plan,
        billing_plan=snapshot.billing_plan,
        subscription_status=snapshot.status,
        enforce_limits=snapshot.enforce_limits,
        enforcement_scope=snapshot.enforcement_scope,
        usage=[
            _usage_item(
                snapshot=snapshot,
                key="ai_chat_daily",
                current=ai_chat_today,
                period="day",
                period_start=day_start,
                period_end=day_end,
            ),
            _usage_item(
                snapshot=snapshot,
                key="photo_recognition_monthly",
                current=photo_recognition_month,
                period="month",
                period_start=month_start,
                period_end=month_end,
            ),
        ],
        notes=[
            (
                "当前为灰度观测用量快照，默认不强制拦截功能。"
                if not snapshot.enforce_limits
                else "当前为强制限额模式，超额会被调用端拦截。"
            ),
            "仅返回计数、周期和套餐额度，不包含原始内容、文件或凭据。",
        ],
    )


def _usage_windows(now: datetime | None = None) -> tuple[datetime, datetime, datetime, datetime]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    day_start = datetime.combine(current.date(), time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    month_start = datetime(current.year, current.month, 1, tzinfo=timezone.utc)
    month_end = (
        datetime(current.year + 1, 1, 1, tzinfo=timezone.utc)
        if current.month == 12
        else datetime(current.year, current.month + 1, 1, tzinfo=timezone.utc)
    )
    return day_start, day_end, month_start, month_end


def _apply_mock_checkout_subscription(user: User, plan: PlanTier) -> None:
    user.subscription_plan = SubscriptionPlan(plan.value)
    user.subscription_status = SubscriptionStatus.ACTIVE
    user.subscription_updated_at = datetime.now(timezone.utc)


def _apply_mock_subscription_cancel(user: User) -> None:
    persisted_plan = getattr(user.subscription_plan, "value", user.subscription_plan)
    if persisted_plan in {SubscriptionPlan.PRO.value, SubscriptionPlan.COACH.value}:
        user.subscription_status = SubscriptionStatus.CANCELED
    else:
        user.subscription_plan = SubscriptionPlan.FREE
        user.subscription_status = SubscriptionStatus.INACTIVE
    user.subscription_updated_at = datetime.now(timezone.utc)


def _reject_mock_billing_in_production() -> None:
    if settings.is_production and normalize_billing_provider(settings.billing_provider) == "mock":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="生产环境已禁用 mock billing；当前构建未接入真实支付 provider，不能修改订阅状态",
        )


def _raise_billing_http_error(exc: Exception) -> None:
    if isinstance(exc, BillingProviderNotReadyError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    if isinstance(exc, BillingWebhookVerificationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if isinstance(exc, BillingProviderError):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("/plans", response_model=list[PlanCatalogItem])
async def get_plan_catalog(current_user: CurrentUser):
    return await entitlement_service.plan_catalog()


@router.get("/providers", response_model=list[BillingProviderResponse])
async def list_billing_providers(current_user: CurrentUser):
    configured_provider = normalize_billing_provider(settings.billing_provider)
    responses: list[BillingProviderResponse] = []
    for item in billing_provider_registry.list_providers():
        readiness = get_billing_adapter(item.provider, config=settings).readiness()
        responses.append(BillingProviderResponse(
            provider=item.provider,
            display_name=item.display_name,
            kind=item.kind,
            status=item.status,
            description=item.description,
            supports_checkout=item.supports_checkout,
            supports_cancel=item.supports_cancel,
            supports_webhook=item.supports_webhook,
            supports_refund=item.supports_refund,
            requires_secret=item.requires_secret,
            is_configured=item.provider == configured_provider,
            readiness={
                "provider": readiness.provider,
                "mode": readiness.mode,
                "configured": readiness.configured,
                "webhook_configured": readiness.webhook_configured,
                "adapter_implementation_status": readiness.adapter_implementation_status,
                "price_mapping_status": readiness.price_mapping_status,
                "ready": readiness.ready,
                "warnings": readiness.warnings,
                "blocking": readiness.blocking,
                "configuration_gaps": readiness.configuration_gaps,
                "webhook_gaps": readiness.webhook_gaps,
            },
        ))
    return responses


@router.get("/entitlements", response_model=EntitlementResponse)
async def get_entitlements(current_user: CurrentUser):
    snapshot = await entitlement_service.snapshot_for_user(current_user)
    return _entitlement_response(snapshot)


@router.get("/usage", response_model=BillingUsageResponse)
async def get_usage_snapshot(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    snapshot = await entitlement_service.snapshot_for_user(current_user)
    day_start, day_end, month_start, month_end = _usage_windows()

    ai_result = await db.execute(
        select(func.count(ChatMessage.id))
        .select_from(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(
            ChatSession.user_id == current_user.id,
            ChatMessage.role == MessageRole.ASSISTANT,
            ChatMessage.created_at >= day_start,
            ChatMessage.created_at < day_end,
        )
    )
    photo_result = await db.execute(
        select(func.count(Meal.id)).where(
            Meal.user_id == current_user.id,
            Meal.source == MealSource.PHOTO.value,
            Meal.created_at >= month_start,
            Meal.created_at < month_end,
        )
    )
    response = _build_usage_response(
        snapshot=snapshot,
        ai_chat_today=int(ai_result.scalar_one() or 0),
        photo_recognition_month=int(photo_result.scalar_one() or 0),
        day_start=day_start,
        day_end=day_end,
        month_start=month_start,
        month_end=month_end,
    )
    await audit_security_event(
        db,
        event_type="billing.usage.list",
        event_status="success",
        user_id=current_user.id,
        request=request,
        route_name="/api/billing/usage",
        metadata={
            "provider": response.provider,
            "plan": response.plan.value,
            "billing_plan": response.billing_plan.value,
            "status": response.subscription_status.value,
            "usage_keys": [item.key for item in response.usage],
            "enforce_limits": response.enforce_limits,
            "enforcement_scope": response.enforcement_scope,
        },
    )
    return response


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    data: CheckoutRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    try:
        session = await create_checkout_order(
            db,
            user=current_user,
            plan=data.plan,
            request=request,
            config=settings,
            activate_mock_compat=True,
        )
    except Exception as exc:
        _raise_billing_http_error(exc)
    return _checkout_response(session)


@router.post("/subscription/cancel", response_model=SubscriptionLifecycleResponse)
async def cancel_subscription(
    data: CancelSubscriptionRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    if data.confirm != "CANCEL_SUBSCRIPTION":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="需要确认 CANCEL_SUBSCRIPTION",
        )
    try:
        result = await cancel_user_subscription(
            db,
            user=current_user,
            request=request,
            reason="user_cancel",
            config=settings,
        )
    except Exception as exc:
        _raise_billing_http_error(exc)

    snapshot = await entitlement_service.snapshot_for_user(current_user)

    return SubscriptionLifecycleResponse(
        provider=result.provider,
        plan=snapshot.plan,
        status=snapshot.status,
        message=result.message,
        entitlement=_entitlement_response(snapshot),
    )


@router.post("/webhooks/{provider}", response_model=BillingWebhookResponse)
async def billing_webhook(provider: str, request: Request, db: DbSession):
    raw_body = await request.body()
    try:
        result = await process_webhook(
            db,
            provider=provider,
            raw_body=raw_body,
            headers=dict(request.headers),
            request=request,
            config=settings,
        )
    except Exception as exc:
        _raise_billing_http_error(exc)
    return BillingWebhookResponse(**result.__dict__)


@router.post("/orders/{order_id}/refunds", response_model=BillingRefundResponse)
async def refund_billing_order(
    order_id: int,
    data: RefundRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    try:
        result = await refund_order(
            db,
            user=current_user,
            order_id=order_id,
            amount_minor=data.amount_minor,
            reason=data.reason,
            request=request,
            config=settings,
        )
    except Exception as exc:
        _raise_billing_http_error(exc)
    return BillingRefundResponse(**result.__dict__)


@router.post("/orders/{order_id}/reconcile", response_model=BillingReconcileResponse)
async def reconcile_billing_order(
    order_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    try:
        result = await reconcile_order(
            db,
            user=current_user,
            order_id=order_id,
            request=request,
            config=settings,
        )
    except Exception as exc:
        _raise_billing_http_error(exc)
    return BillingReconcileResponse(**result.__dict__)


@router.post("/entitlements/require")
async def require_entitlement(
    data: EntitlementRequireRequest,
    current_user: CurrentUser,
):
    try:
        snapshot = await entitlement_service.ensure(current_user, data.feature)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return _entitlement_response(snapshot)
