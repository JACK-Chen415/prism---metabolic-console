"""User data rights endpoints: export, delete, and account closure."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentTokenPayload, CurrentUser, DbSession
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.chat import ChatMessage, ChatSession
from app.models.feedback import AIFeedback
from app.models.health_condition import HealthCondition
from app.models.health_metric import HealthMetric
from app.models.knowledge import KnowledgeAuditLog
from app.models.meal import Meal
from app.models.message import AppMessage
from app.models.security import DeviceSession
from app.schemas.meal import MealResponse
from app.schemas.user import UserResponse
from app.services.auth_security import audit_security_event, revoke_device_session
from app.services.insights import SMART_INSIGHT_ATTRIBUTION_PREFIX
from app.services.target_service import calculate_daily_targets


router = APIRouter(prefix="/account", tags=["用户数据权利"])

MEDICAL_DISCLAIMER = (
    "Prism 仅用于个人饮食记录、营养估算和代谢风险提示，不提供医疗诊断、治疗、处方或急救服务。"
)


class DataDeleteRequest(BaseModel):
    confirm: Literal["DELETE_DATA"] = Field(description="确认删除云端个人内容")


class AccountDeleteRequest(BaseModel):
    confirm: Literal["DELETE_ACCOUNT"] = Field(description="确认注销账户")


class DataRightsResponse(BaseModel):
    success: bool = True
    status: str = "accepted"
    message: str
    request_id: str


def _json_dt(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else value


def _enum_value(value):
    return getattr(value, "value", value)


def _export_account_state(user) -> dict:
    return {
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "role": _enum_value(getattr(user, "role", None)),
        "subscription_plan": _enum_value(getattr(user, "subscription_plan", None)),
        "subscription_status": _enum_value(getattr(user, "subscription_status", None)),
        "subscription_updated_at": _json_dt(getattr(user, "subscription_updated_at", None)),
        "consent_version": getattr(user, "consent_version", None),
        "consent_accepted_at": _json_dt(getattr(user, "consent_accepted_at", None)),
        "consents": {
            "terms": bool(getattr(user, "consent_terms_accepted", False)),
            "privacy": bool(getattr(user, "consent_privacy_accepted", False)),
            "ai_use": bool(getattr(user, "consent_ai_use_accepted", False)),
            "health_disclaimer": bool(getattr(user, "consent_health_disclaimer_accepted", False)),
        },
        "created_at": _json_dt(getattr(user, "created_at", None)),
        "updated_at": _json_dt(getattr(user, "updated_at", None)),
        "last_login_at": _json_dt(getattr(user, "last_login_at", None)),
        "retention_note": "安全审计记录会按合规需要保留；导出不包含密码、验证码、token、refresh jti、IP hash 或 UA hash。",
    }


def _device_session_export_item(item: DeviceSession) -> dict:
    return {
        "session_id": item.session_id,
        "device_label": item.device_label,
        "is_current": item.is_current,
        "is_revoked": item.revoked_at is not None,
        "expires_at": _json_dt(item.expires_at),
        "created_at": _json_dt(item.created_at),
        "last_seen_at": _json_dt(item.last_seen_at),
        "revoked_at": _json_dt(item.revoked_at),
        "revoke_reason": item.revoke_reason,
    }


async def _export_device_sessions(db: DbSession, user_id: int) -> list[dict]:
    result = await db.execute(
        select(DeviceSession)
        .where(DeviceSession.user_id == user_id)
        .order_by(DeviceSession.last_seen_at.desc(), DeviceSession.id.desc())
    )
    return [_device_session_export_item(item) for item in result.scalars().all()]


async def _export_conditions(db: DbSession, user_id: int) -> list[dict]:
    result = await db.execute(
        select(HealthCondition)
        .where(HealthCondition.user_id == user_id)
        .order_by(HealthCondition.created_at.desc())
    )
    return [
        {
            "id": item.id,
            "condition_code": item.condition_code,
            "title": item.title,
            "icon": item.icon,
            "condition_type": _enum_value(item.condition_type),
            "status": _enum_value(item.status),
            "trend": _enum_value(item.trend),
            "value": item.value,
            "unit": item.unit,
            "dictum": item.dictum,
            "attribution": item.attribution,
            "created_at": _json_dt(item.created_at),
            "updated_at": _json_dt(item.updated_at),
        }
        for item in result.scalars().all()
    ]


async def _export_messages(db: DbSession, user_id: int) -> list[dict]:
    result = await db.execute(
        select(AppMessage)
        .where(AppMessage.user_id == user_id)
        .order_by(AppMessage.created_at.desc())
    )
    return [
        {
            "id": item.id,
            "message_type": _enum_value(item.message_type),
            "title": item.title,
            "content": item.content,
            "attribution": item.attribution,
            "is_read": item.is_read,
            "created_at": _json_dt(item.created_at),
            "read_at": _json_dt(item.read_at),
        }
        for item in result.scalars().all()
    ]


async def _export_insights(db: DbSession, user_id: int) -> list[dict]:
    messages = await _export_messages(db, user_id)
    return [
        message
        for message in messages
        if str(message.get("attribution") or "").startswith(SMART_INSIGHT_ATTRIBUTION_PREFIX)
    ]


async def _export_chat_sessions(db: DbSession, user_id: int) -> list[dict]:
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = []
    for session in result.scalars().all():
        sessions.append(
            {
                "id": session.id,
                "title": session.title,
                "created_at": _json_dt(session.created_at),
                "updated_at": _json_dt(session.updated_at),
                "messages": [
                    {
                        "id": message.id,
                        "role": _enum_value(message.role),
                        "content": message.content,
                        "attachments": message.attachments,
                        "model": message.model,
                        "tokens_used": message.tokens_used,
                        "created_at": _json_dt(message.created_at),
                    }
                    for message in session.messages
                ],
            }
        )
    return sessions


async def _export_ai_feedback(db: DbSession, user_id: int) -> list[dict]:
    result = await db.execute(
        select(AIFeedback)
        .where(AIFeedback.user_id == user_id)
        .order_by(AIFeedback.created_at.desc(), AIFeedback.id.desc())
    )
    return [
        {
            "id": item.id,
            "session_id": item.session_id,
            "message_id": item.message_id,
            "app_message_id": item.app_message_id,
            "feedback_type": _enum_value(item.feedback_type),
            "rating": item.rating,
            "tags": item.tags_json or [],
            "correction_text": item.correction_text,
            "status": _enum_value(item.status),
            "created_at": _json_dt(item.created_at),
            "reviewed_at": _json_dt(item.reviewed_at),
        }
        for item in result.scalars().all()
    ]


async def _export_health_metrics(db: DbSession, user_id: int) -> list[dict]:
    result = await db.execute(
        select(HealthMetric)
        .where(HealthMetric.user_id == user_id)
        .order_by(HealthMetric.recorded_at.desc(), HealthMetric.id.desc())
    )
    return [
        {
            "id": item.id,
            "metric_type": _enum_value(item.metric_type),
            "value": item.value,
            "value_secondary": item.value_secondary,
            "unit": item.unit,
            "source": item.source,
            "provider": item.provider,
            "metadata": item.metadata_json or {},
            "recorded_at": _json_dt(item.recorded_at),
            "created_at": _json_dt(item.created_at),
            "updated_at": _json_dt(item.updated_at),
        }
        for item in result.scalars().all()
    ]


async def _delete_user_generated_content(db: DbSession, user_id: int) -> dict[str, int]:
    chat_ids = (
        select(ChatSession.id)
        .where(ChatSession.user_id == user_id)
        .subquery()
    )
    deleted = {}

    for name, statement in [
        ("ai_feedback", delete(AIFeedback).where(AIFeedback.user_id == user_id)),
        ("health_metrics", delete(HealthMetric).where(HealthMetric.user_id == user_id)),
        ("chat_messages", delete(ChatMessage).where(ChatMessage.session_id.in_(select(chat_ids.c.id)))),
        ("chat_sessions", delete(ChatSession).where(ChatSession.user_id == user_id)),
        ("meals", delete(Meal).where(Meal.user_id == user_id)),
        ("health_conditions", delete(HealthCondition).where(HealthCondition.user_id == user_id)),
        ("app_messages", delete(AppMessage).where(AppMessage.user_id == user_id)),
        ("knowledge_audit_logs", delete(KnowledgeAuditLog).where(KnowledgeAuditLog.user_id == user_id)),
    ]:
        result = await db.execute(statement)
        deleted[name] = result.rowcount or 0

    await db.flush()
    return deleted


@router.get("/export")
async def export_account_data(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    """Export user data as JSON for personal backup and review."""
    request_id = uuid.uuid4().hex
    conditions_result = await db.execute(
        select(HealthCondition).where(HealthCondition.user_id == current_user.id)
    )
    conditions = list(conditions_result.scalars().all())

    meals_result = await db.execute(
        select(Meal)
        .where(Meal.user_id == current_user.id)
        .order_by(Meal.record_date.desc(), Meal.created_at.desc())
    )
    meals = [MealResponse.model_validate(item).model_dump(mode="json") for item in meals_result.scalars().all()]

    export_version = f"{settings.app_name}/{settings.app_version}"
    generated_at = datetime.now(timezone.utc).isoformat()
    export_bundle = {
        "export_version": export_version,
        "generated_at": generated_at,
        "medical_disclaimer": MEDICAL_DISCLAIMER,
        "request_id": request_id,
        "export_manifest": {
            "request_id": request_id,
            "export_version": export_version,
            "generated_at": generated_at,
            "section_count": 11,
            "section_keys": [
                "profile",
                "account_state",
                "device_sessions",
                "daily_targets",
                "meals",
                "conditions",
                "messages",
                "insights",
                "chat_sessions",
                "ai_feedback",
                "health_metrics",
            ],
            "medical_disclaimer": MEDICAL_DISCLAIMER,
        },
        "profile": {"data": UserResponse.model_validate(current_user).model_dump(mode="json")},
        "account_state": {"data": _export_account_state(current_user)},
        "device_sessions": {"data": await _export_device_sessions(db, current_user.id)},
        "daily_targets": {"data": calculate_daily_targets(current_user, conditions).model_dump(mode="json")},
        "meals": {"data": meals},
        "conditions": {"data": await _export_conditions(db, current_user.id)},
        "messages": {"data": await _export_messages(db, current_user.id)},
        "insights": {"data": await _export_insights(db, current_user.id)},
        "chat_sessions": {"data": await _export_chat_sessions(db, current_user.id)},
        "ai_feedback": {"data": await _export_ai_feedback(db, current_user.id)},
        "health_metrics": {"data": await _export_health_metrics(db, current_user.id)},
    }

    await audit_security_event(
        db,
        event_type="data.export",
        event_status="success",
        user_id=current_user.id,
        request=request,
        route_name="/api/account/export",
        metadata={
            "request_id": request_id,
            "section_count": export_bundle["export_manifest"]["section_count"],
            "sections": export_bundle["export_manifest"]["section_keys"],
        },
    )
    return export_bundle


@router.post("/delete-data", response_model=DataRightsResponse)
async def delete_account_data(
    data: DataDeleteRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    """Delete user-generated content while keeping the login account active."""
    request_id = uuid.uuid4().hex
    deleted = await _delete_user_generated_content(db, current_user.id)
    await audit_security_event(
        db,
        event_type="data.delete",
        event_status="success",
        user_id=current_user.id,
        request=request,
        route_name="/api/account/delete-data",
        metadata={"request_id": request_id, "deleted": deleted, "confirm": data.confirm},
    )
    return DataRightsResponse(
        message="云端个人内容删除请求已完成；必要安全审计记录会按合规要求保留。",
        request_id=request_id,
    )


@router.delete("", response_model=DataRightsResponse)
async def delete_account(
    data: AccountDeleteRequest,
    request: Request,
    current_user: CurrentUser,
    token_payload: CurrentTokenPayload,
    db: DbSession,
):
    """Close the account, delete content, anonymize profile, and revoke the session."""
    request_id = uuid.uuid4().hex
    deleted = await _delete_user_generated_content(db, current_user.id)

    current_user.phone = f"del{current_user.id}_{int(datetime.now(timezone.utc).timestamp())}"[:20]
    current_user.password_hash = get_password_hash(uuid.uuid4().hex)
    current_user.nickname = None
    current_user.avatar_url = None
    current_user.gender = None
    current_user.age = None
    current_user.height = None
    current_user.weight = None
    current_user.is_active = False
    current_user.is_verified = False

    await revoke_device_session(
        db,
        user_id=current_user.id,
        session_id=token_payload.get("sid"),
        reason="account_deleted",
    )
    await db.execute(
        delete(DeviceSession).where(DeviceSession.user_id == current_user.id)
    )
    await db.flush()
    await audit_security_event(
        db,
        event_type="account.delete",
        event_status="success",
        user_id=current_user.id,
        request=request,
        session_id=token_payload.get("sid"),
        route_name="/api/account",
        metadata={"request_id": request_id, "deleted": deleted, "confirm": data.confirm},
    )
    return DataRightsResponse(
        message="账户已注销，云端个人内容已清理，当前会话已失效。",
        request_id=request_id,
    )
