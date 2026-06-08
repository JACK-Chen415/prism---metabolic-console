"""Multimodal intake parsing and confirmation APIs."""

import base64
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.security import hash_sensitive_value
from app.models.feedback import AIFeedback, AIFeedbackStatus
from app.models.health_condition import HealthCondition
from app.models.intake_telemetry import IntakeReviewTelemetrySnapshot
from app.schemas.intake import (
    IntakeCandidate,
    IntakeCandidateAlternativesRequest,
    IntakeCandidateAlternativesResponse,
    IntakeCandidateFeedbackRequest,
    IntakeConfirmItem,
    IntakeConfirmPreviewRequest,
    IntakeConfirmPreviewResponse,
    IntakeConfirmRequest,
    IntakeConfirmResponse,
    IntakeDraftSessionResponse,
    IntakeReviewTelemetryRequest,
    IntakeReviewTelemetryResponse,
    PhotoParseRequest,
    TextParseRequest,
    VoiceAutoLogRequest,
    VoiceParseRequest,
)
from app.services.ai_service import doubao_service
from app.services.auth_security import audit_security_event
from app.services.intake import IntakeService
from app.schemas.chat import AIFeedbackResponse
from app.services.upload_security import sanitize_image_upload


router = APIRouter(prefix="/intake", tags=["多模态录入"])
intake_service = IntakeService()


async def get_user_conditions(user_id: int, db: DbSession) -> list[HealthCondition]:
    result = await db.execute(select(HealthCondition).where(HealthCondition.user_id == user_id))
    return list(result.scalars().all())


_INTAKE_FEEDBACK_SAFE_TAGS = {
    "intake_candidate",
    "manual",
    "voice",
    "photo",
    "ai_quick_log",
    "low_confidence",
    "safety_rule",
    "rule_warning",
    "hard_block",
    "high_risk",
    "recognition_error",
    "portion_error",
    "nutrition_error",
    "knowledge_gap",
    "allergy",
    "dietary_restriction",
}
_INTAKE_FEEDBACK_RECOMMENDATION_LEVELS = {
    "RECOMMEND",
    "MODERATE",
    "LIMIT",
    "AVOID",
    "CONDITIONAL",
    "INSUFFICIENT",
}
_INTAKE_FEEDBACK_COUNT_KEYS = {
    "candidate_count",
    "low_confidence_count",
    "high_risk_count",
    "hard_block_count",
    "risk_tag_count",
    "allergen_tag_count",
    "warning_count",
}


def _normalize_intake_feedback_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen = set()
    for tag in ["intake_candidate", *(tags or [])]:
        clean = str(tag).strip().lower().replace(" ", "_")[:40]
        if clean not in _INTAKE_FEEDBACK_SAFE_TAGS or clean in seen:
            continue
        seen.add(clean)
        normalized.append(clean)
        if len(normalized) >= 12:
            break
    return normalized


def _coerce_intake_feedback_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(int(value), 5000))


def _safe_intake_candidate_feedback_metadata(data: IntakeCandidateFeedbackRequest) -> dict[str, Any]:
    raw_metadata = data.metadata if isinstance(data.metadata, dict) else {}
    metadata: dict[str, Any] = {
        "source": data.source.value,
        "surface": "intake_confirmation",
        "draft_id_hash": hash_sensitive_value(data.draft_id),
    }

    recommendation_level = raw_metadata.get("recommendation_level")
    if isinstance(recommendation_level, str) and recommendation_level in _INTAKE_FEEDBACK_RECOMMENDATION_LEVELS:
        metadata["recommendation_level"] = recommendation_level

    for key in _INTAKE_FEEDBACK_COUNT_KEYS:
        count = _coerce_intake_feedback_count(raw_metadata.get(key))
        if count is not None:
            metadata[key] = count

    return metadata


def _intake_feedback_audit_metadata(feedback: AIFeedback) -> dict[str, Any]:
    tags = feedback.tags_json or []
    return {
        "feedback_id": feedback.id,
        "feedback_type": feedback.feedback_type.value,
        "rating": feedback.rating,
        "tags_count": len(tags),
        "has_correction": bool(feedback.correction_text_hash),
        "correction_text_hash": feedback.correction_text_hash,
        "metadata_keys": sorted((feedback.metadata_json or {}).keys()),
    }


def _intake_feedback_response(feedback: AIFeedback) -> AIFeedbackResponse:
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


@router.post("/voice/parse", response_model=IntakeDraftSessionResponse)
async def parse_voice_intake(
    data: VoiceParseRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)
    return await intake_service.parse_voice(
        db,
        user=current_user,
        conditions=conditions,
        data=data,
    )


@router.post("/text/parse", response_model=IntakeDraftSessionResponse)
async def parse_text_intake(
    data: TextParseRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)
    return await intake_service.parse_text(
        db,
        user=current_user,
        conditions=conditions,
        data=data,
    )


@router.post("/voice/auto-log", response_model=IntakeConfirmResponse, status_code=status.HTTP_201_CREATED)
async def auto_log_voice_intake(
    data: VoiceAutoLogRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)

    try:
        return await intake_service.voice_auto_log(
            db,
            user=current_user,
            conditions=conditions,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/candidate/reevaluate", response_model=IntakeCandidate)
async def reevaluate_intake_candidate(
    data: IntakeConfirmItem,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)

    try:
        return await intake_service.reevaluate_confirm_item(
            db,
            user=current_user,
            conditions=conditions,
            item=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/candidate/alternatives", response_model=IntakeCandidateAlternativesResponse)
async def suggest_intake_candidate_alternatives(
    data: IntakeCandidateAlternativesRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)

    try:
        return await intake_service.suggest_candidate_alternatives(
            db,
            user=current_user,
            conditions=conditions,
            item=data.candidate,
            limit=data.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/photo/parse-result", response_model=IntakeDraftSessionResponse)
async def parse_photo_intake(
    data: PhotoParseRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)
    return await intake_service.parse_photo_result(
        db,
        user=current_user,
        conditions=conditions,
        data=data,
    )


@router.post("/confirm/preview", response_model=IntakeConfirmPreviewResponse)
async def preview_intake_confirm_impact(
    data: IntakeConfirmPreviewRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)
    return await intake_service.preview_confirm_impact(
        db,
        user=current_user,
        conditions=conditions,
        data=data,
    )


@router.post("/candidate-feedback", response_model=AIFeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_candidate_feedback(
    data: IntakeCandidateFeedbackRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    """Record user-owned correction feedback for an intake candidate without auditing raw text."""
    correction_text_hash = hash_sensitive_value(data.correction_text.strip())
    feedback = AIFeedback(
        user_id=current_user.id,
        feedback_type=data.feedback_type,
        rating=data.rating,
        tags_json=_normalize_intake_feedback_tags(data.tags),
        correction_text="intake_candidate_correction_submitted",
        correction_text_hash=correction_text_hash,
        metadata_json=_safe_intake_candidate_feedback_metadata(data),
        status=AIFeedbackStatus.OPEN,
    )
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)

    await audit_security_event(
        db,
        event_type="intake.candidate.feedback.create",
        event_status="success",
        user_id=current_user.id,
        request=request,
        actor=current_user.phone,
        route_name="/api/intake/candidate-feedback",
        metadata=_intake_feedback_audit_metadata(feedback),
    )
    return _intake_feedback_response(feedback)


@router.post("/review-telemetry", response_model=IntakeReviewTelemetryResponse, status_code=status.HTTP_201_CREATED)
async def submit_review_telemetry(
    data: IntakeReviewTelemetryRequest,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    """Store privacy-preserving aggregate counts for the local intake review queue."""
    snapshot = IntakeReviewTelemetrySnapshot(
        user_id=current_user.id,
        total_count=data.total_count,
        pending_review_count=data.pending_review_count,
        in_review_count=data.in_review_count,
        low_confidence_count=data.low_confidence_count,
        high_risk_count=data.high_risk_count,
        hard_block_count=data.hard_block_count,
        source_counts_json=dict(data.source_counts),
        status_counts_json=dict(data.status_counts),
    )
    db.add(snapshot)
    await db.flush()
    await db.refresh(snapshot)

    await audit_security_event(
        db,
        event_type="intake.review.telemetry.submit",
        event_status="success",
        user_id=current_user.id,
        request=request,
        actor=current_user.phone,
        route_name="/api/intake/review-telemetry",
        metadata={
            "total_count": snapshot.total_count,
            "pending_review_count": snapshot.pending_review_count,
            "in_review_count": snapshot.in_review_count,
            "low_confidence_count": snapshot.low_confidence_count,
            "high_risk_count": snapshot.high_risk_count,
            "hard_block_count": snapshot.hard_block_count,
            "source_counts": snapshot.source_counts_json or {},
            "status_counts": snapshot.status_counts_json or {},
        },
    )

    return IntakeReviewTelemetryResponse(
        id=snapshot.id,
        received_at=snapshot.created_at,
        total_count=snapshot.total_count,
        pending_review_count=snapshot.pending_review_count,
        in_review_count=snapshot.in_review_count,
        low_confidence_count=snapshot.low_confidence_count,
        high_risk_count=snapshot.high_risk_count,
        hard_block_count=snapshot.hard_block_count,
        source_counts=snapshot.source_counts_json or {},
        status_counts=snapshot.status_counts_json or {},
        notes=[
            "只接收聚合计数，不上传候选食物名、备注、健康文本、图片或客户端草稿内容。",
        ],
    )


@router.post("/photo/recognize-parse-upload", response_model=IntakeDraftSessionResponse)
async def recognize_and_parse_photo_upload(
    file: UploadFile = File(...),
    prompt: Optional[str] = Form(None),
    meal_time_hint: Optional[str] = Form(None),
    record_date: Optional[str] = Form(None),
    fast: bool = Form(True),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    """
    拍照识别 + 结构化候选项的一步式接口。

    优化点：
    1. 前端直接上传压缩后的图片文件，避免 base64 JSON 大包；
    2. 后端只请求一次多模态模型；
    3. 本地知识规则只在 parse 阶段执行一次。
    """
    content = await file.read()
    from app.core.config import settings

    max_size = settings.max_upload_size_mb * 1024 * 1024
    try:
        image = sanitize_image_upload(
            content,
            content_type=file.content_type or "",
            max_size_bytes=max_size,
            max_pixels=settings.max_upload_image_pixels,
        )
    except ValueError as exc:
        status_code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if "大小超过限制" in str(exc) or "像素超过限制" in str(exc)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail=str(exc),
        ) from exc

    conditions = await get_user_conditions(current_user.id, db)
    image_base64 = base64.b64encode(image.content).decode("utf-8")
    image_type = "jpeg" if image.format == "JPEG" else "png"

    foods, ai_response = await doubao_service.recognize_food(
        image_base64=image_base64,
        user=current_user,
        conditions=conditions,
        image_type=image_type,
        user_prompt=prompt,
        fast=fast,
    )

    if not foods:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ai_response or "未识别到可记录的食物，请换个角度重新拍摄",
        )

    parse_request = PhotoParseRequest(
        recognized_foods=foods,
        ai_response=ai_response,
        meal_time_hint=meal_time_hint,
        record_date=record_date,
    )
    return await intake_service.parse_photo_result(
        db,
        user=current_user,
        conditions=conditions,
        data=parse_request,
    )


@router.post("/confirm", response_model=IntakeConfirmResponse, status_code=status.HTTP_201_CREATED)
async def confirm_intake(
    data: IntakeConfirmRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)

    try:
        return await intake_service.confirm(
            db,
            user=current_user,
            conditions=conditions,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
