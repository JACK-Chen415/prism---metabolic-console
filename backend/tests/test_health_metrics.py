import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes import health_metrics as route
from app.models.health_metric import HealthMetric, HealthMetricType
from app.schemas.health_metric import HealthMetricCreate, HealthMetricUpdate
from app.services.health_metric_providers import (
    HealthMetricProviderDefinition,
    HealthMetricProviderKind,
    HealthMetricProviderRegistry,
    HealthMetricProviderStatus,
    health_metric_provider_registry,
)

class FakeMetricDb:
    def __init__(self):
        self.added = []
        self.flush_count = 0

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flush_count += 1
        self._hydrate_metrics()

    async def refresh(self, item):
        self._hydrate_metrics()

    def _hydrate_metrics(self):
        now = datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)
        for item in self.added:
            if isinstance(item, HealthMetric):
                item.id = item.id or 100
                item.recorded_at = item.recorded_at or now
                item.created_at = item.created_at or now
                item.updated_at = item.updated_at or now


def test_health_metric_type_enum_uses_persisted_lowercase_values() -> None:
    enum_type = HealthMetric.__table__.c.metric_type.type
    assert enum_type.enums == [member.value for member in HealthMetricType]


def test_health_metric_create_defaults_unit_and_requires_blood_pressure_pair() -> None:
    weight = HealthMetricCreate(metric_type=HealthMetricType.WEIGHT, value=70.5)
    assert weight.unit == "kg"

    with pytest.raises(ValidationError):
        HealthMetricCreate(metric_type=HealthMetricType.BLOOD_PRESSURE, value=128)

    pressure = HealthMetricCreate(
        metric_type=HealthMetricType.BLOOD_PRESSURE,
        value=128,
        value_secondary=82,
    )
    assert pressure.unit == "mmHg"


def test_health_metric_update_rejects_source_and_provider_fields() -> None:
    with pytest.raises(ValidationError):
        HealthMetricUpdate(value=71, source="manual")

    with pytest.raises(ValidationError):
        HealthMetricUpdate(value=71, provider="mock_device")


def test_metric_provider_registry_resolves_only_allowed_manual_create_pairs() -> None:
    assert health_metric_provider_registry.resolve_manual_create(source=None, provider=None) == (
        "manual",
        "manual",
    )
    assert health_metric_provider_registry.resolve_manual_create(source=" MANUAL ", provider="manual") == (
        "manual",
        "manual",
    )

    with pytest.raises(ValueError, match="不允许"):
        health_metric_provider_registry.resolve_manual_create(source="manual", provider="mock_device")

    with pytest.raises(ValueError, match="不允许"):
        health_metric_provider_registry.resolve_manual_create(source="vendor_device", provider="vendor_device")

    with pytest.raises(ValueError, match="不匹配"):
        health_metric_provider_registry.resolve_manual_create(source="mock_device", provider="manual")

    with pytest.raises(ValueError, match="未知"):
        health_metric_provider_registry.resolve_manual_create(source="manual", provider="unknown_device")


def test_metric_provider_registry_allows_manual_create_only_when_flagged() -> None:
    registry = HealthMetricProviderRegistry(
        [
            HealthMetricProviderDefinition(
                provider="partner_device",
                display_name="Partner Device",
                kind=HealthMetricProviderKind.DEVICE,
                status=HealthMetricProviderStatus.MOCK,
                description="Contract test provider.",
                supports_import=True,
                supports_realtime=False,
                supports_history=True,
                allowed_sources=("partner_upload",),
                manual_create_allowed=True,
            )
        ]
    )

    assert registry.resolve_manual_create(source="partner_upload", provider="partner-device") == (
        "partner_upload",
        "partner_device",
    )


@pytest.mark.asyncio
async def test_create_health_metric_canonicalizes_manual_gray_release_flow() -> None:
    db = FakeMetricDb()
    user = SimpleNamespace(id=1)
    data = HealthMetricCreate(metric_type=HealthMetricType.WEIGHT, value=70.5, source="manual")

    response = await route.create_health_metric(data, None, user, db)
    persisted_metrics = [item for item in db.added if isinstance(item, HealthMetric)]

    assert response.source == "manual"
    assert response.provider == "manual"
    assert persisted_metrics[0].source == "manual"
    assert persisted_metrics[0].provider == "manual"
    assert db.flush_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["mock_device", "vendor_device"])
async def test_create_health_metric_rejects_device_provider_spoofing_before_persist(provider: str) -> None:
    db = FakeMetricDb()
    user = SimpleNamespace(id=1)
    data = HealthMetricCreate(
        metric_type=HealthMetricType.WEIGHT,
        value=70.5,
        source="manual",
        provider=provider,
    )

    with pytest.raises(HTTPException) as exc_info:
        await route.create_health_metric(data, None, user, db)

    assert exc_info.value.status_code == 400
    assert "不允许" in str(exc_info.value.detail)
    assert db.added == []


def test_metric_metadata_allowlist_removes_notes_and_raw_text() -> None:
    metadata = route._safe_metric_metadata(
        {
            "fasting": True,
            "time_of_day": "morning",
            "device_model": "mock-band",
            "note": "头晕、胸闷等健康敏感原文",
            "provider_record_id": "external-123",
        }
    )

    assert metadata == {"fasting": True, "time_of_day": "morning", "device_model": "mock-band"}
    assert "note" not in metadata
    assert "provider_record_id" not in metadata


def test_metric_audit_metadata_does_not_include_measurement_values() -> None:
    item = HealthMetric(
        id=9,
        user_id=1,
        metric_type=HealthMetricType.BLOOD_PRESSURE,
        value=128,
        value_secondary=82,
        unit="mmHg",
        source="manual",
        provider=None,
        metadata_json={"fasting": False},
    )
    item.recorded_at = datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)

    metadata = route._audit_metadata(item)
    serialized = json.dumps(metadata, ensure_ascii=False)

    assert metadata["metric_type"] == "blood_pressure"
    assert metadata["has_secondary_value"] is True
    assert "128" not in serialized
    assert "82" not in serialized
    assert "mmHg" not in serialized


def test_metric_provider_registry_exposes_mock_device_without_real_vendor_secret() -> None:
    providers = {item.provider: item for item in health_metric_provider_registry.list_providers()}

    assert providers["manual"].status == HealthMetricProviderStatus.AVAILABLE
    assert providers["mock_device"].status == HealthMetricProviderStatus.MOCK
    assert providers["mock_device"].supports_import is True
    assert providers["vendor_device"].status == HealthMetricProviderStatus.PLANNED
    assert "secret" not in providers["vendor_device"].description.lower()


@pytest.mark.asyncio
async def test_metric_provider_endpoint_returns_safe_status_surface() -> None:
    response = await route.list_health_metric_providers()
    payload = [item.model_dump(mode="json") for item in response]

    provider_names = {item["provider"] for item in payload}
    serialized = json.dumps(payload, ensure_ascii=False)

    assert {"manual", "mock_device", "vendor_device"}.issubset(provider_names)
    assert "api_key" not in serialized.lower()
    assert "token" not in serialized.lower()
    assert "真实设备 Provider 预留" in serialized
