"""Health metric provider registry.

This keeps wearable/device integrations behind a small provider abstraction.
Current gray-release builds expose only manual entry and a mock device slot; no
real vendor secret or external call is introduced here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


MANUAL_HEALTH_METRIC_PROVIDER = "manual"
MANUAL_HEALTH_METRIC_SOURCE = "manual"


class HealthMetricProviderKind(str, Enum):
    MANUAL = "manual"
    DEVICE = "device"


class HealthMetricProviderStatus(str, Enum):
    AVAILABLE = "available"
    MOCK = "mock"
    PLANNED = "planned"


@dataclass(frozen=True)
class HealthMetricProviderDefinition:
    provider: str
    display_name: str
    kind: HealthMetricProviderKind
    status: HealthMetricProviderStatus
    description: str
    supports_import: bool
    supports_realtime: bool
    supports_history: bool
    allowed_sources: tuple[str, ...] = ()
    manual_create_allowed: bool = False


def _normalize_health_metric_token(value: str | None, *, default: str, max_length: int) -> str:
    clean = (value or default).strip().lower().replace("-", "_").replace(" ", "_")
    return clean[:max_length] or default


def normalize_health_metric_source(source: str | None) -> str:
    return _normalize_health_metric_token(source, default=MANUAL_HEALTH_METRIC_SOURCE, max_length=40)


def normalize_health_metric_provider(provider: str | None) -> str:
    return _normalize_health_metric_token(provider, default=MANUAL_HEALTH_METRIC_PROVIDER, max_length=120)


class HealthMetricProviderRegistry:
    """Registry of metric providers exposed to API/UI surfaces."""

    def __init__(self, providers: list[HealthMetricProviderDefinition] | None = None):
        self._providers = providers or [
            HealthMetricProviderDefinition(
                provider=MANUAL_HEALTH_METRIC_PROVIDER,
                display_name="手动记录",
                kind=HealthMetricProviderKind.MANUAL,
                status=HealthMetricProviderStatus.AVAILABLE,
                description="用户在应用内手动录入健康指标。",
                supports_import=False,
                supports_realtime=False,
                supports_history=True,
                allowed_sources=(MANUAL_HEALTH_METRIC_SOURCE,),
                manual_create_allowed=True,
            ),
            HealthMetricProviderDefinition(
                provider="mock_device",
                display_name="模拟设备 Provider",
                kind=HealthMetricProviderKind.DEVICE,
                status=HealthMetricProviderStatus.MOCK,
                description="用于内测设备导入契约，不连接真实厂商服务。",
                supports_import=True,
                supports_realtime=False,
                supports_history=True,
                allowed_sources=("mock_device",),
                manual_create_allowed=False,
            ),
            HealthMetricProviderDefinition(
                provider="vendor_device",
                display_name="真实设备 Provider 预留",
                kind=HealthMetricProviderKind.DEVICE,
                status=HealthMetricProviderStatus.PLANNED,
                description="预留给未来穿戴设备或健康平台接入；上线前需要签名校验、幂等和审计。",
                supports_import=False,
                supports_realtime=False,
                supports_history=False,
                allowed_sources=("vendor_device",),
                manual_create_allowed=False,
            ),
        ]

    def list_providers(self) -> list[HealthMetricProviderDefinition]:
        return list(self._providers)

    def get(self, provider: str | None) -> HealthMetricProviderDefinition | None:
        clean = normalize_health_metric_provider(provider)
        for item in self._providers:
            if item.provider == clean:
                return item
        return None

    def resolve_manual_create(self, *, source: str | None, provider: str | None) -> tuple[str, str]:
        clean_source = normalize_health_metric_source(source)
        clean_provider = normalize_health_metric_provider(provider)
        definition = self.get(clean_provider)
        if definition is None:
            raise ValueError("未知健康指标 provider")
        if not definition.manual_create_allowed:
            raise ValueError("该健康指标 provider 不允许通过手动录入接口创建")

        allowed_sources = {
            normalize_health_metric_source(item)
            for item in (definition.allowed_sources or (definition.provider,))
        }
        if clean_source not in allowed_sources:
            raise ValueError("健康指标 source 与 provider 不匹配")

        return clean_source, definition.provider


health_metric_provider_registry = HealthMetricProviderRegistry()
