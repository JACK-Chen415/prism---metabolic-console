"""Billing provider registry.

Real payment integrations must be added behind this registry so checkout,
cancel, webhook, refund, and invoice behavior can be audited before charging
users. The current gray-release provider is mock-only and never uses secrets.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BillingProviderKind(str, Enum):
    MOCK = "mock"
    PAYMENT = "payment"


class BillingProviderStatus(str, Enum):
    ACTIVE = "active"
    MOCK = "mock"
    PLANNED = "planned"
    DISABLED = "disabled"


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
                supports_webhook=False,
                supports_refund=False,
                requires_secret=False,
            ),
            BillingProviderDefinition(
                provider="external_gateway",
                display_name="真实支付 Provider 预留",
                kind=BillingProviderKind.PAYMENT,
                status=BillingProviderStatus.PLANNED,
                description="预留给未来支付网关；上线前必须完成签名校验、幂等、发票、退款和审计事件。",
                supports_checkout=False,
                supports_cancel=False,
                supports_webhook=False,
                supports_refund=False,
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


billing_provider_registry = BillingProviderRegistry()
