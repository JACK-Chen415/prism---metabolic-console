"""Smart insight API routes."""

from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.api.routes.messages import MessageResponse
from app.core.security import hash_sensitive_value
from app.models.feedback import AIFeedback, AIFeedbackStatus
from app.models.message import AppMessage
from app.schemas.chat import AIFeedbackCreate, AIFeedbackResponse
from sqlalchemy import select

from app.services.auth_security import audit_security_event
from app.services.insights import SMART_INSIGHT_ATTRIBUTION_PREFIX, SmartInsightMessageService


class InsightRefreshResponse(BaseModel):
    target_date: str
    generated_count: int
    messages: List[MessageResponse]


router = APIRouter(prefix="/insights", tags=["智能洞察"])
insight_message_service = SmartInsightMessageService()


_INSIGHT_FEEDBACK_METADATA_ALLOWLIST = {"source", "surface", "context"}


def _normalize_insight_feedback_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for tag in tags:
        value = str(tag or "").strip().lower().replace(" ", "_")[:40]
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
        if len(normalized) >= 12:
            break
    return normalized


def _safe_insight_feedback_metadata(
    message: AppMessage,
    metadata: Optional[dict[str, Any]],
) -> dict[str, Any]:
    safe: dict[str, Any] = {
        "source": "insight",
        "app_message_id": message.id,
        "message_type": getattr(message.message_type, "value", message.message_type),
    }
    if message.attribution:
        safe["attribution_hash"] = hash_sensitive_value(message.attribution)

    for key, value in (metadata or {}).items():
        if key not in _INSIGHT_FEEDBACK_METADATA_ALLOWLIST:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
    return safe


def _feedback_response(feedback: AIFeedback) -> AIFeedbackResponse:
    return AIFeedbackResponse(
        id=feedback.id,
        session_id=feedback.session_id,
        message_id=feedback.message_id,
        app_message_id=feedback.app_message_id,
        feedback_type=feedback.feedback_type,
        rating=feedback.rating,
        tags=feedback.tags_json or [],
        status=feedback.status or AIFeedbackStatus.OPEN,
        has_correction=bool(feedback.correction_text_hash),
        created_at=feedback.created_at,
    )


def _insight_feedback_audit_metadata(feedback: AIFeedback) -> dict[str, Any]:
    tags = feedback.tags_json or []
    return {
        "feedback_id": feedback.id,
        "app_message_id": feedback.app_message_id,
        "feedback_type": feedback.feedback_type.value,
        "rating": feedback.rating,
        "tags_count": len(tags),
        "has_correction": bool(feedback.correction_text_hash),
        "correction_text_hash": feedback.correction_text_hash,
        "metadata_keys": sorted((feedback.metadata_json or {}).keys()),
    }


async def _load_owned_smart_insight_message(
    db: DbSession,
    *,
    message_id: int,
    user_id: int,
) -> AppMessage:
    result = await db.execute(
        select(AppMessage).where(AppMessage.id == message_id, AppMessage.user_id == user_id)
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="洞察消息不存在")
    if not (message.attribution or "").startswith(SMART_INSIGHT_ATTRIBUTION_PREFIX):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能反馈智能洞察消息")
    return message


@router.post("/refresh", response_model=InsightRefreshResponse)
async def refresh_insights(current_user: CurrentUser, db: DbSession):
    """Regenerate today's smart insight messages for the current user."""
    result = await insight_message_service.refresh_today(db, user=current_user)
    return InsightRefreshResponse(
        target_date=result.target_date.isoformat(),
        generated_count=result.generated_count,
        messages=[MessageResponse.model_validate(message) for message in result.messages],
    )


@router.get("/today", response_model=List[MessageResponse])
async def get_today_insights(current_user: CurrentUser, db: DbSession):
    """Return persisted smart insight messages for today."""
    messages = await insight_message_service.list_today(db, user=current_user)
    return [MessageResponse.model_validate(message) for message in messages]


@router.post("/{message_id}/feedback", response_model=AIFeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_insight_feedback(
    message_id: int,
    data: AIFeedbackCreate,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    """Record feedback for a persisted smart insight without auditing raw correction text."""
    message = await _load_owned_smart_insight_message(db, message_id=message_id, user_id=current_user.id)
    correction_text = (data.correction_text or "").strip() or None
    feedback = AIFeedback(
        user_id=current_user.id,
        app_message_id=message.id,
        feedback_type=data.feedback_type,
        rating=data.rating,
        tags_json=_normalize_insight_feedback_tags(data.tags),
        correction_text=correction_text,
        correction_text_hash=hash_sensitive_value(correction_text),
        metadata_json=_safe_insight_feedback_metadata(message, data.metadata),
        status=AIFeedbackStatus.OPEN,
    )
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)

    await audit_security_event(
        db,
        event_type="insight.feedback.create",
        event_status="success",
        user_id=current_user.id,
        request=request,
        route_name="/api/insights/{message_id}/feedback",
        metadata=_insight_feedback_audit_metadata(feedback),
    )
    return _feedback_response(feedback)


@router.get("/{message_id}/feedback", response_model=list[AIFeedbackResponse])
async def list_insight_feedback(message_id: int, current_user: CurrentUser, db: DbSession):
    """List current user's feedback for one smart insight message."""
    message = await _load_owned_smart_insight_message(db, message_id=message_id, user_id=current_user.id)
    result = await db.execute(
        select(AIFeedback)
        .where(AIFeedback.user_id == current_user.id, AIFeedback.app_message_id == message.id)
        .order_by(AIFeedback.created_at.desc(), AIFeedback.id.desc())
    )
    return [_feedback_response(item) for item in result.scalars().all()]
