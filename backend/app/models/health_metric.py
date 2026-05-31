"""User health metric time-series records."""

from datetime import datetime
from typing import Optional
import enum

from sqlalchemy import DateTime, Enum as SQLEnum, Float, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class HealthMetricType(str, enum.Enum):
    WEIGHT = "weight"
    BODY_FAT = "body_fat"
    BLOOD_PRESSURE = "blood_pressure"
    BLOOD_GLUCOSE = "blood_glucose"
    URIC_ACID = "uric_acid"
    BLOOD_LIPID = "blood_lipid"
    WAIST = "waist"


class HealthMetric(Base):
    """Discrete metabolic and body-composition measurement."""

    __tablename__ = "health_metrics"
    __table_args__ = (
        Index("ix_health_metrics_user_type_recorded_at", "user_id", "metric_type", "recorded_at"),
        Index("ix_health_metrics_user_recorded_at", "user_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric_type: Mapped[HealthMetricType] = mapped_column(
        SQLEnum(
            HealthMetricType,
            name="healthmetrictype",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    value_secondary: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="health_metrics")


from app.models.user import User
