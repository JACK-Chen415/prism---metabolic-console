"""Schemas for user health metric time-series records."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.health_metric import HealthMetricType


DEFAULT_UNITS: dict[HealthMetricType, str] = {
    HealthMetricType.WEIGHT: "kg",
    HealthMetricType.BODY_FAT: "%",
    HealthMetricType.BLOOD_PRESSURE: "mmHg",
    HealthMetricType.BLOOD_GLUCOSE: "mmol/L",
    HealthMetricType.URIC_ACID: "umol/L",
    HealthMetricType.BLOOD_LIPID: "mmol/L",
    HealthMetricType.WAIST: "cm",
}


class HealthMetricCreate(BaseModel):
    """Create a manual or provider-backed health metric record."""

    model_config = ConfigDict(extra="forbid")

    metric_type: HealthMetricType
    value: float = Field(..., ge=0)
    value_secondary: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = Field(None, max_length=24)
    recorded_at: Optional[datetime] = None
    source: str = Field("manual", max_length=40)
    provider: Optional[str] = Field(None, max_length=120)
    metadata: Optional[dict[str, Any]] = None

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        clean = (value or "manual").strip().lower().replace(" ", "_")
        return clean[:40] or "manual"

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        clean = value.strip()
        return clean[:120] or None

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        clean = value.strip()
        return clean[:24] or None

    @model_validator(mode="after")
    def validate_metric_shape(self):
        if not self.unit:
            self.unit = DEFAULT_UNITS[self.metric_type]
        if self.metric_type == HealthMetricType.BLOOD_PRESSURE and self.value_secondary is None:
            raise ValueError("血压记录需要同时提供舒张压 value_secondary")
        return self


class HealthMetricUpdate(BaseModel):
    """Update editable fields on a health metric record."""

    model_config = ConfigDict(extra="forbid")

    value: Optional[float] = Field(None, ge=0)
    value_secondary: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = Field(None, max_length=24)
    recorded_at: Optional[datetime] = None
    metadata: Optional[dict[str, Any]] = None

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        clean = value.strip()
        return clean[:24] or None


class HealthMetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    metric_type: HealthMetricType
    value: float
    value_secondary: Optional[float] = None
    unit: str
    source: str
    provider: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    recorded_at: datetime
    created_at: datetime
    updated_at: datetime
