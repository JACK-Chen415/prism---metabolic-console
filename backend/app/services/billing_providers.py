"""Billing provider registry and fail-closed adapter contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Mapping, Protocol

from app.core.config import Settings, settings


class BillingProviderKind(str, Enum):
    MOCK = "mock"
    PAYMENT = "payment"


class BillingProviderStatus(str, Enum):
    ACTIVE = "active"
    MOCK = "mock"
    PLANNED = "planned"
    DISABLED = "disabled"


class BillingProviderError(RuntimeError):
    """Base class for provider-level billing failures."""


class BillingProviderNotReadyError(BillingProviderError):
    """Raised when a provider is selected but cannot safely process billing."""


class BillingWebhookVerificationError(BillingProviderError):
    """Raised when a webhook cannot be verified."""


@dataclass(frozen=True)
class BillingProviderDefinition:
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


@dataclass(frozen=True)
class BillingProviderReadiness:
    provider: str
    mode: str
    configured: bool
    webhook_configured: bool
    adapter_implementation_status: str
    price_mapping_status: str
    ready: bool
    warnings: list[str] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)
    configuration_gaps: list[str] = field(default_factory=list)
    webhook_gaps: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderCheckoutRequest:
    user_id: int
    plan: str
    amount_minor: int
    currency: str
    local_order_id: str
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderCheckoutResult:
    checkout_id: str
    checkout_url: str
    provider_order_id: str | None = None
    provider_request_id: str | None = None
    expires_at: datetime | None = None
    status: str = "checkout_pending"
    message: str = "Checkout created. Await verified provider webhook before activating entitlement."


@dataclass(frozen=True)
class VerifiedBillingEvent:
    provider: str
    event_id: str
    event_type: str
    resource_type: str | None = None
    provider_order_id: str | None = None
    provider_payment_id: str | None = None
    provider_refund_id: str | None = None
    provider_request_id: str | None = None
    plan: str | None = None
    amount_minor: int | None = None
    occurred_at: datetime | None = None
    raw_body_sha256: str | None = None
    signature_algorithm: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BillingTransition:
    order_status: str | None = None
    subscription_status: str | None = None
    refund_status: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ProviderRefundRequest:
    provider_payment_id: str
    out_refund_no: str
    amount_minor: int
    currency: str
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderRefundResult:
    out_refund_no: str
    provider_refund_id: str | None = None
    provider_request_id: str | None = None
    status: str = "processing"
    message: str = "Refund request accepted by provider placeholder."


@dataclass(frozen=True)
class ProviderQueryResult:
    provider_order_id: str
    event: VerifiedBillingEvent | None = None
    provider_request_id: str | None = None
    status: str = "unknown"


class BillingAdapter(Protocol):
    provider_name: str

    def readiness(self) -> BillingProviderReadiness:
        ...

    async def create_checkout(self, request: ProviderCheckoutRequest) -> ProviderCheckoutResult:
        ...

    async def verify_webhook(self, raw_body: bytes, headers: Mapping[str, str]) -> VerifiedBillingEvent:
        ...

    def map_event_to_transition(self, event: VerifiedBillingEvent) -> BillingTransition:
        ...

    async def cancel_order(self, provider_order_id: str, *, reason: str | None = None) -> ProviderQueryResult:
        ...

    async def refund(self, request: ProviderRefundRequest) -> ProviderRefundResult:
        ...

    async def query(self, provider_order_id: str) -> ProviderQueryResult:
        ...


class BillingProviderRegistry:
    """Registry of payment providers exposed to API/UI status surfaces."""

    def __init__(self, providers: list[BillingProviderDefinition] | None = None):
        self._providers = providers or [
            BillingProviderDefinition(
                provider="mock",
                display_name="Mock Billing Provider",
                kind=BillingProviderKind.MOCK,
                status=BillingProviderStatus.MOCK,
                description="灰度内测使用的模拟支付 provider；不会创建真实支付、发票或扣款。",
                supports_checkout=True,
                supports_cancel=True,
                supports_webhook=True,
                supports_refund=True,
                requires_secret=False,
            ),
            BillingProviderDefinition(
                provider="wechat_pay",
                display_name="微信支付",
                kind=BillingProviderKind.PAYMENT,
                status=BillingProviderStatus.PLANNED,
                description="微信支付安全占位 adapter；凭据和真实 API 实现缺失时所有调用 fail-closed。",
                supports_checkout=True,
                supports_cancel=True,
                supports_webhook=True,
                supports_refund=True,
                requires_secret=True,
            ),
            BillingProviderDefinition(
                provider="alipay",
                display_name="支付宝",
                kind=BillingProviderKind.PAYMENT,
                status=BillingProviderStatus.PLANNED,
                description="支付宝安全占位 adapter；凭据和真实 API 实现缺失时所有调用 fail-closed。",
                supports_checkout=True,
                supports_cancel=True,
                supports_webhook=True,
                supports_refund=True,
                requires_secret=True,
            ),
        ]

    def list_providers(self) -> list[BillingProviderDefinition]:
        return list(self._providers)

    def get(self, provider: str) -> BillingProviderDefinition | None:
        clean = normalize_billing_provider(provider)
        for item in self._providers:
            if item.provider == clean:
                return item
        return None

    def active_provider_names(self) -> set[str]:
        return {
            item.provider
            for item in self._providers
            if item.status in {BillingProviderStatus.ACTIVE, BillingProviderStatus.MOCK}
        }


def normalize_billing_provider(provider: str | None) -> str:
    return (provider or "mock").strip().lower().replace("-", "_") or "mock"


def _readiness_from_settings(config: Settings, provider: str) -> BillingProviderReadiness:
    snapshot = config.billing_readiness_snapshot(provider)
    return BillingProviderReadiness(
        provider=snapshot["provider"],
        mode=snapshot["mode"],
        configured=snapshot["configured"],
        webhook_configured=snapshot["webhook_configured"],
        adapter_implementation_status=snapshot["adapter_implementation_status"],
        price_mapping_status=snapshot["price_mapping_status"],
        ready=snapshot["ready"],
        warnings=list(snapshot["warnings"]),
        blocking=list(snapshot["blocking"]),
        configuration_gaps=list(snapshot["configuration_gaps"]),
        webhook_gaps=list(snapshot["webhook_gaps"]),
    )


def _ensure_ready(readiness: BillingProviderReadiness, *, require_webhook: bool = False) -> None:
    if not readiness.ready:
        detail = ", ".join(readiness.blocking) or "provider_not_ready"
        raise BillingProviderNotReadyError(f"{readiness.provider} billing provider is blocked: {detail}")
    if require_webhook and not readiness.webhook_configured:
        detail = ", ".join(readiness.webhook_gaps) or "webhook_not_configured"
        raise BillingProviderNotReadyError(f"{readiness.provider} webhook is blocked: {detail}")


def _parse_event_occurred_at(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


class MockBillingAdapter:
    """Internal-only adapter for non-production smoke tests."""

    provider_name = "mock"

    def __init__(self, config: Settings = settings):
        self.config = config

    def readiness(self) -> BillingProviderReadiness:
        return _readiness_from_settings(self.config, self.provider_name)

    async def create_checkout(self, request: ProviderCheckoutRequest) -> ProviderCheckoutResult:
        readiness = self.readiness()
        _ensure_ready(readiness)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        return ProviderCheckoutResult(
            checkout_id=request.local_order_id,
            checkout_url=f"https://billing.example.invalid/prism/mock-checkout/{request.local_order_id}",
            provider_order_id=request.local_order_id,
            expires_at=expires_at,
            status="mock_created",
            message="Mock checkout created. No real payment was initiated.",
        )

    async def verify_webhook(self, raw_body: bytes, headers: Mapping[str, str]) -> VerifiedBillingEvent:
        readiness = self.readiness()
        _ensure_ready(readiness, require_webhook=True)
        expected = (self.config.billing_mock_webhook_secret or "").strip()
        provided = (
            headers.get("x-prism-mock-webhook-secret")
            or headers.get("X-Prism-Mock-Webhook-Secret")
            or ""
        ).strip()
        if provided != expected:
            raise BillingWebhookVerificationError("mock billing webhook signature mismatch")
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BillingWebhookVerificationError("mock billing webhook body is not valid JSON") from exc

        event_id = str(payload.get("event_id") or "").strip()
        event_type = str(payload.get("event_type") or "").strip()
        if not event_id or not event_type:
            raise BillingWebhookVerificationError("mock billing webhook missing event_id or event_type")

        return VerifiedBillingEvent(
            provider=self.provider_name,
            event_id=event_id,
            event_type=event_type,
            resource_type=payload.get("resource_type") or "order",
            provider_order_id=payload.get("provider_order_id") or payload.get("out_trade_no"),
            provider_payment_id=payload.get("provider_payment_id") or payload.get("transaction_id"),
            provider_refund_id=payload.get("provider_refund_id") or payload.get("refund_id"),
            provider_request_id=payload.get("provider_request_id"),
            plan=payload.get("plan"),
            amount_minor=payload.get("amount_minor"),
            occurred_at=_parse_event_occurred_at(payload.get("occurred_at")),
            raw_body_sha256=hashlib.sha256(raw_body).hexdigest(),
            signature_algorithm="mock-shared-secret",
            metadata={
                "mock": True,
                "resource_type": payload.get("resource_type") or "order",
            },
        )

    def map_event_to_transition(self, event: VerifiedBillingEvent) -> BillingTransition:
        event_type = event.event_type.lower().replace(".", "_").replace("-", "_")
        if event_type in {"payment_success", "trade_success", "transaction_success"}:
            return BillingTransition(
                order_status="paid",
                subscription_status="active",
                reason="provider_payment_success",
            )
        if event_type in {"payment_failed", "trade_failed", "transaction_failed"}:
            return BillingTransition(
                order_status="payment_failed",
                subscription_status="payment_failed",
                reason="provider_payment_failed",
            )
        if event_type in {"order_closed", "order_canceled", "trade_closed"}:
            return BillingTransition(
                order_status="closed",
                subscription_status="canceled",
                reason="provider_order_closed",
            )
        if event_type in {"refund_success", "refund_succeeded"}:
            return BillingTransition(
                order_status="refunded",
                subscription_status="refunded",
                refund_status="succeeded",
                reason="provider_refund_success",
            )
        if event_type in {"subscription_cancel_at_period_end"}:
            return BillingTransition(
                subscription_status="cancel_at_period_end",
                reason="provider_cancel_at_period_end",
            )
        if event_type in {"subscription_canceled"}:
            return BillingTransition(
                order_status="canceled",
                subscription_status="canceled",
                reason="provider_subscription_canceled",
            )
        return BillingTransition(reason="provider_event_ignored")

    async def cancel_order(self, provider_order_id: str, *, reason: str | None = None) -> ProviderQueryResult:
        readiness = self.readiness()
        _ensure_ready(readiness)
        event = VerifiedBillingEvent(
            provider=self.provider_name,
            event_id=f"mock_cancel_{provider_order_id}",
            event_type="order_closed",
            provider_order_id=provider_order_id,
            occurred_at=datetime.now(timezone.utc),
            metadata={"reason": reason or "user_cancel"},
        )
        return ProviderQueryResult(provider_order_id=provider_order_id, event=event, status="closed")

    async def refund(self, request: ProviderRefundRequest) -> ProviderRefundResult:
        readiness = self.readiness()
        _ensure_ready(readiness)
        return ProviderRefundResult(
            out_refund_no=request.out_refund_no,
            provider_refund_id=f"mock_refund_{request.out_refund_no}",
            status="succeeded",
            message="Mock refund recorded. No real payment provider was contacted.",
        )

    async def query(self, provider_order_id: str) -> ProviderQueryResult:
        readiness = self.readiness()
        _ensure_ready(readiness)
        event = VerifiedBillingEvent(
            provider=self.provider_name,
            event_id=f"mock_query_{provider_order_id}",
            event_type="payment_success",
            provider_order_id=provider_order_id,
            provider_payment_id=f"mock_payment_{provider_order_id}",
            occurred_at=datetime.now(timezone.utc),
            metadata={"source": "mock_reconcile"},
        )
        return ProviderQueryResult(provider_order_id=provider_order_id, event=event, status="paid")


class FailClosedPaymentAdapter:
    """Safe placeholder for real payment providers until credentials and API code exist."""

    provider_name: str

    def __init__(self, provider_name: str, config: Settings = settings):
        self.provider_name = provider_name
        self.config = config

    def readiness(self) -> BillingProviderReadiness:
        return _readiness_from_settings(self.config, self.provider_name)

    def _blocked(self) -> BillingProviderNotReadyError:
        readiness = self.readiness()
        detail = ", ".join(readiness.blocking) or "adapter_not_implemented"
        return BillingProviderNotReadyError(f"{self.provider_name} adapter is fail-closed: {detail}")

    async def create_checkout(self, request: ProviderCheckoutRequest) -> ProviderCheckoutResult:
        raise self._blocked()

    async def verify_webhook(self, raw_body: bytes, headers: Mapping[str, str]) -> VerifiedBillingEvent:
        raise self._blocked()

    def map_event_to_transition(self, event: VerifiedBillingEvent) -> BillingTransition:
        return MockBillingAdapter(config=self.config).map_event_to_transition(event)

    async def cancel_order(self, provider_order_id: str, *, reason: str | None = None) -> ProviderQueryResult:
        raise self._blocked()

    async def refund(self, request: ProviderRefundRequest) -> ProviderRefundResult:
        raise self._blocked()

    async def query(self, provider_order_id: str) -> ProviderQueryResult:
        raise self._blocked()


class WechatPayAdapter(FailClosedPaymentAdapter):
    def __init__(self, config: Settings = settings):
        super().__init__("wechat_pay", config=config)


class AlipayAdapter(FailClosedPaymentAdapter):
    def __init__(self, config: Settings = settings):
        super().__init__("alipay", config=config)


def get_billing_adapter(provider: str | None = None, *, config: Settings = settings) -> BillingAdapter:
    clean = normalize_billing_provider(provider or config.billing_provider)
    if clean == "mock":
        return MockBillingAdapter(config=config)
    if clean == "wechat_pay":
        return WechatPayAdapter(config=config)
    if clean == "alipay":
        return AlipayAdapter(config=config)
    raise BillingProviderNotReadyError(f"unsupported billing provider: {clean}")


billing_provider_registry = BillingProviderRegistry()
