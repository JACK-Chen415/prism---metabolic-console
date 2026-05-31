"""Health metric time-series API routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.api.deps import CurrentUser, DbSession
from app.models.health_metric import HealthMetric, HealthMetricType
from app.schemas.health_metric import HealthMetricCreate, HealthMetricResponse, HealthMetricUpdate
from app.services.auth_security import audit_security_event
from app.services.health_metric_providers import (
    HealthMetricProviderKind,
    HealthMetricProviderStatus,
    health_metric_provider_registry,
)


router = APIRouter(prefix="/health-metrics", tags=["健康指标"])


class HealthMetricProviderResponse(BaseModel):
    provider: str
    display_name: str
    kind: HealthMetricProviderKind
    status: HealthMetricProviderStatus
    description: str
    supports_import: bool
    supports_realtime: bool
    supports_history: bool

_METADATA_ALLOWLIST = {
    "fasting",
    "time_of_day",
    "measurement_site",
    "posture",
    "source_detail",
    "device_model",
}


def _safe_metric_metadata(metadata: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not metadata:
        return {}
    safe: dict[str, Any] = {}
    for key in _METADATA_ALLOWLIST:
        value = metadata.get(key)
        if isinstance(value, bool):
            safe[key] = value
        elif isinstance(value, (int, float)):
            safe[key] = value
        elif isinstance(value, str):
            clean = value.strip()
            if clean:
                safe[key] = clean[:120]
    return safe


def _response(item: HealthMetric) -> HealthMetricResponse:
    return HealthMetricResponse(
        id=item.id,
        metric_type=item.metric_type,
        value=item.value,
        value_secondary=item.value_secondary,
        unit=item.unit,
        source=item.source,
        provider=item.provider,
        metadata=item.metadata_json or {},
        recorded_at=item.recorded_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _audit_metadata(item: HealthMetric) -> dict[str, Any]:
    return {
        "metric_id": item.id,
        "metric_type": item.metric_type.value,
        "source": item.source,
        "provider_present": bool(item.provider),
        "has_secondary_value": item.value_secondary is not None,
        "metadata_keys": sorted((item.metadata_json or {}).keys()),
        "recorded_date": item.recorded_at.date().isoformat() if item.recorded_at else None,
    }


async def _load_owned_metric(db: DbSession, *, user_id: int, metric_id: int) -> Optional[HealthMetric]:
    result = await db.execute(
        select(HealthMetric).where(HealthMetric.id == metric_id, HealthMetric.user_id == user_id)
    )
    return result.scalar_one_or_none()


@router.post("", response_model=HealthMetricResponse, status_code=status.HTTP_201_CREATED)
async def create_health_metric(
    data: HealthMetricCreate,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    """Create a manual health metric record."""
    try:
        source, provider = health_metric_provider_registry.resolve_manual_create(
            source=data.source,
            provider=data.provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    item = HealthMetric(
        user_id=current_user.id,
        metric_type=data.metric_type,
        value=data.value,
        value_secondary=data.value_secondary,
        unit=data.unit or "",
        source=source,
        provider=provider,
        metadata_json=_safe_metric_metadata(data.metadata),
        recorded_at=data.recorded_at or datetime.now(timezone.utc),
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    await audit_security_event(
        db,
        event_type="health_metric.create",
        event_status="success",
        user_id=current_user.id,
        request=request,
        route_name="/api/health-metrics",
        metadata=_audit_metadata(item),
    )
    return _response(item)


@router.get("", response_model=list[HealthMetricResponse])
async def list_health_metrics(
    current_user: CurrentUser,
    db: DbSession,
    metric_type: Optional[HealthMetricType] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """List the current user's metric records, newest first."""
    query = select(HealthMetric).where(HealthMetric.user_id == current_user.id)
    if metric_type is not None:
        query = query.where(HealthMetric.metric_type == metric_type)
    result = await db.execute(
        query.order_by(HealthMetric.recorded_at.desc(), HealthMetric.id.desc()).limit(limit)
    )
    return [_response(item) for item in result.scalars().all()]


@router.get("/latest", response_model=dict[HealthMetricType, HealthMetricResponse])
async def latest_health_metrics(current_user: CurrentUser, db: DbSession):
    """Return the latest record for each metric type."""
    result = await db.execute(
        select(HealthMetric)
        .where(HealthMetric.user_id == current_user.id)
        .order_by(HealthMetric.recorded_at.desc(), HealthMetric.id.desc())
    )
    latest: dict[HealthMetricType, HealthMetricResponse] = {}
    for item in result.scalars().all():
        if item.metric_type not in latest:
            latest[item.metric_type] = _response(item)
    return latest


@router.get("/providers", response_model=list[HealthMetricProviderResponse])
async def list_health_metric_providers():
    """Expose the current provider registry without any secret or device payload."""
    return [
        HealthMetricProviderResponse(
            provider=item.provider,
            display_name=item.display_name,
            kind=item.kind,
            status=item.status,
            description=item.description,
            supports_import=item.supports_import,
            supports_realtime=item.supports_realtime,
            supports_history=item.supports_history,
        )
        for item in health_metric_provider_registry.list_providers()
    ]


@router.put("/{metric_id}", response_model=HealthMetricResponse)
async def update_health_metric(
    metric_id: int,
    data: HealthMetricUpdate,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    """Update a user-owned metric record."""
    item = await _load_owned_metric(db, user_id=current_user.id, metric_id=metric_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="健康指标不存在")

    update_data = data.model_dump(exclude_unset=True)
    if "metadata" in update_data:
        item.metadata_json = _safe_metric_metadata(update_data.pop("metadata"))
    for field, value in update_data.items():
        setattr(item, field, value)
    if item.metric_type == HealthMetricType.BLOOD_PRESSURE and item.value_secondary is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="血压记录需要舒张压")

    await db.flush()
    await db.refresh(item)
    await audit_security_event(
        db,
        event_type="health_metric.update",
        event_status="success",
        user_id=current_user.id,
        request=request,
        route_name="/api/health-metrics/{metric_id}",
        metadata=_audit_metadata(item),
    )
    return _response(item)


@router.delete("/{metric_id}")
async def delete_health_metric(
    metric_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    """Delete one user-owned metric record."""
    item = await _load_owned_metric(db, user_id=current_user.id, metric_id=metric_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="健康指标不存在")

    audit_metadata = _audit_metadata(item)
    await db.execute(delete(HealthMetric).where(HealthMetric.id == item.id))
    await audit_security_event(
        db,
        event_type="health_metric.delete",
        event_status="success",
        user_id=current_user.id,
        request=request,
        route_name="/api/health-metrics/{metric_id}",
        metadata=audit_metadata,
    )
    return {"success": True, "message": "删除成功"}
