"""
AI 对话 API 路由
"""

from typing import Any, AsyncGenerator, List, Optional

from fastapi import APIRouter, HTTPException, Request, Response, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select
import base64
import binascii
import json
import logging
import time

from app.api.deps import DbSession, CurrentUser
from app.core.config import settings
from app.core.security import hash_sensitive_value
from app.models.chat import ChatSession, ChatMessage, MessageRole
from app.models.feedback import AIFeedback
from app.models.health_condition import HealthCondition
from app.models.meal import MealType, FoodCategory
from app.schemas.chat import (
    ChatMessageCreate,
    ChatSessionCreate,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSessionDetailResponse,
    AIFeedbackCreate,
    AIFeedbackResponse,
    FoodRecognitionRequest,
    FoodRecognitionResponse,
    QuickLogRequest
)
from app.schemas.common import PaginatedResponse
from app.schemas.meal import MealResponse
from app.schemas.intake import IntakeConfirmItem, IntakeConfirmRequest, IntakeSource
from app.services.ai_service import doubao_service
from app.services.auth_security import audit_security_event
from app.services.intake import IntakeService
from app.services.knowledge import KnowledgeService, write_knowledge_audit_log
from app.services.knowledge.severity import pick_strictest_recommendation_level
from app.services.upload_security import sanitize_image_upload
from app.models.knowledge import FallbackStatus, KnowledgeOrigin, RecommendationLevel
import uuid

router = APIRouter(prefix="/chat", tags=["AI对话"])
knowledge_service = KnowledgeService()
intake_service = IntakeService()
logger = logging.getLogger(__name__)


async def get_user_conditions(user_id: int, db) -> List[HealthCondition]:
    """获取用户健康状况"""
    result = await db.execute(
        select(HealthCondition).where(HealthCondition.user_id == user_id)
    )
    return list(result.scalars().all())


def _new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


async def _load_recent_history(db, session_id: int) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(settings.chat_history_limit)
    )
    history = list(result.scalars().all())
    history.reverse()
    return history


def _history_to_prompt_messages(history: list[ChatMessage]) -> tuple[list[dict[str, str]], int]:
    max_chars = settings.chat_history_message_max_chars
    messages = []
    history_chars = 0
    for msg in history:
        content = _truncate_text(msg.content or "", max_chars)
        history_chars += len(content)
        messages.append({"role": msg.role.value, "content": content})
    return messages, history_chars


def _is_local_direct_response(summary) -> bool:
    return (
        summary.fallback_status in {FallbackStatus.LOCAL_BLOCKED_NO_CLOUD, FallbackStatus.LOCAL_COMPLETE}
        and bool(summary.local_decisions)
    )


def _knowledge_attachment(
    *,
    response_origin: KnowledgeOrigin,
    summary,
    called_cloud: bool,
    cloud_call_reason: Optional[str],
    cloud_blocked_reason: Optional[str],
) -> dict[str, Any]:
    return {
        "knowledge": {
            "origin": response_origin.value,
            "fallback_status": summary.fallback_status.value,
            "matched_disease_codes": summary.matched_disease_codes,
            "matched_food_codes": summary.matched_food_codes,
            "citations": [citation.model_dump() for citation in summary.citations],
            "unmapped_conditions": summary.unmapped_conditions,
            "called_cloud": called_cloud,
            "cloud_call_reason": cloud_call_reason,
            "cloud_blocked_reason": cloud_blocked_reason,
        }
    }


def _safe_timing_number(timings: dict[str, Any], key: str) -> float:
    value = timings.get(key)
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _chat_cost_attachment(timings: dict[str, Any]) -> dict[str, Any]:
    cloud_called = bool(timings.get("cloud_called"))
    if not cloud_called:
        return {
            "estimated_cost_usd": 0.0,
            "cost_status": "local_only",
            "cost_source": "no_cloud_call",
        }

    rate = getattr(settings, "ai_cost_usd_per_1k_tokens", None)
    chars_per_token = getattr(settings, "ai_cost_estimate_chars_per_token", 4.0) or 4.0
    if rate is None:
        return {
            "estimated_cost_usd": None,
            "cost_status": "unconfigured",
            "cost_source": "ai_cost_usd_per_1k_tokens_not_configured",
        }
    if chars_per_token <= 0:
        return {
            "estimated_cost_usd": None,
            "cost_status": "unconfigured",
            "cost_source": "invalid_estimator_config",
        }

    total_chars = _safe_timing_number(timings, "prompt_chars") + _safe_timing_number(timings, "response_chars")
    if total_chars <= 0:
        return {
            "estimated_cost_usd": None,
            "cost_status": "insufficient_usage_data",
            "cost_source": "missing_prompt_or_response_chars",
        }

    estimated_tokens = round(total_chars / chars_per_token, 2)
    estimated_cost = round((estimated_tokens / 1000.0) * float(rate), 6)
    return {
        "estimated_cost_usd": estimated_cost,
        "cost_status": "estimated",
        "cost_source": "char_based_estimate",
        "estimated_tokens": estimated_tokens,
    }


def _chat_telemetry_attachment(timings: dict[str, Any]) -> dict[str, Any]:
    safe_keys = {
        "request_type",
        "cloud_called",
        "prompt_build_ms",
        "prompt_chars",
        "message_count",
        "history_query_ms",
        "history_message_count",
        "history_chars",
        "conditions_query_ms",
        "knowledge_summary_ms",
        "post_review_ms",
        "doubao_first_chunk_ms",
        "doubao_total_ms",
        "assistant_flush_ms",
        "assistant_commit_ms",
        "audit_flush_ms",
        "audit_commit_ms",
        "stream_first_chunk_ms",
        "stream_done_ms",
        "chat_total_ms",
        "response_chars",
        "fallback_status",
        "origin",
        "error",
        "audit_error",
        "doubao_error",
        "estimated_tokens",
    }
    telemetry: dict[str, Any] = _chat_cost_attachment(timings)
    for key in safe_keys:
        if key in timings:
            value = timings[key]
            if isinstance(value, (bool, int, float)) or value is None or isinstance(value, str):
                telemetry[key] = value
    return telemetry


def _merge_chat_attachments(attachments: Optional[dict[str, Any]], timings: dict[str, Any]) -> dict[str, Any]:
    merged = dict(attachments or {})
    merged["telemetry"] = _chat_telemetry_attachment(timings)
    return merged


def _normalize_chat_mode(value: Optional[str]) -> str:
    normalized = (value or "").strip().upper()
    return "GENTLE" if normalized == "GENTLE" else "STRICT"


def _normalize_intervention_intensity(value: Optional[str]) -> str:
    normalized = (value or "").strip().upper()
    return normalized if normalized in {"LOW", "STANDARD", "HIGH"} else "STANDARD"


def _ui_preferences_payload(data: ChatMessageCreate) -> dict[str, str]:
    return {
        "ai_mode": _normalize_chat_mode(data.ai_mode),
        "intervention_intensity": _normalize_intervention_intensity(data.intervention_intensity),
    }


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _log_chat_timing(request_id: str, timings: dict[str, Any]) -> None:
    safe_timings = {"request_id": request_id, **timings}
    logging.getLogger("uvicorn.error").info(
        "chat_timing %s",
        json.dumps(safe_timings, ensure_ascii=False, sort_keys=True),
    )


async def _commit_if_supported(db) -> None:
    commit = getattr(db, "commit", None)
    if commit:
        await commit()


async def _rollback_if_supported(db) -> None:
    rollback = getattr(db, "rollback", None)
    if rollback:
        await rollback()


_FEEDBACK_METADATA_ALLOWLIST = {
    "source",
    "surface",
    "mode",
    "intensity",
    "reason_code",
    "candidate_id",
    "recognition_id",
}


def _normalize_feedback_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen = set()
    for tag in tags or []:
        clean = str(tag).strip().lower().replace(" ", "_")[:40]
        if not clean or clean in seen:
            continue
        seen.add(clean)
        normalized.append(clean)
        if len(normalized) >= 12:
            break
    return normalized


def _safe_feedback_metadata(metadata: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Keep only small operational fields; never store prompt/reply/raw food text here."""
    if not metadata:
        return {}
    safe: dict[str, Any] = {}
    for key in _FEEDBACK_METADATA_ALLOWLIST:
        value = metadata.get(key)
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            safe[key] = str(value)[:120] if isinstance(value, str) else value
    return safe


def _feedback_audit_metadata(feedback: AIFeedback) -> dict[str, Any]:
    tags = feedback.tags_json or []
    return {
        "feedback_id": feedback.id,
        "message_id": feedback.message_id,
        "app_message_id": feedback.app_message_id,
        "session_id": feedback.session_id,
        "feedback_type": feedback.feedback_type.value,
        "rating": feedback.rating,
        "tags_count": len(tags),
        "has_correction": bool(feedback.correction_text_hash),
        "correction_text_hash": feedback.correction_text_hash,
        "metadata_keys": sorted((feedback.metadata_json or {}).keys()),
    }


def _feedback_response(feedback: AIFeedback) -> AIFeedbackResponse:
    return AIFeedbackResponse(
        id=feedback.id,
        session_id=feedback.session_id,
        message_id=feedback.message_id,
        app_message_id=feedback.app_message_id,
        feedback_type=feedback.feedback_type,
        rating=feedback.rating,
        tags=feedback.tags_json or [],
        status=feedback.status,
        has_correction=bool(feedback.correction_text_hash),
        created_at=feedback.created_at,
    )


def _recognition_message_attachments(
    *,
    foods: list[Any],
    origin: KnowledgeOrigin,
    fallback_status: FallbackStatus,
    matched_disease_codes: list[str],
    matched_food_codes: list[str],
) -> dict[str, Any]:
    return {
        "recognition": {
            "source": "photo_upload",
            "food_count": len(foods),
            "foods": [
                food.model_dump(mode="json") if hasattr(food, "model_dump") else food
                for food in foods
            ],
        },
        "knowledge": {
            "origin": origin.value,
            "fallback_status": fallback_status.value,
            "matched_disease_codes": _dedupe(matched_disease_codes),
            "matched_food_codes": _dedupe(matched_food_codes),
        },
    }


async def _load_owned_chat_session(db, *, user_id: int, session_id: int) -> Optional[ChatSession]:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _load_owned_chat_message(db, *, user_id: int, message_id: int) -> Optional[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatMessage.id == message_id, ChatSession.user_id == user_id)
    )
    return result.scalar_one_or_none()


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: ChatSessionCreate,
    current_user: CurrentUser,
    db: DbSession
):
    """创建新的对话会话"""
    session = ChatSession(
        user_id=current_user.id,
        title=data.title
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    return ChatSessionResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=0
    )


@router.get("/sessions", response_model=PaginatedResponse[ChatSessionResponse])
async def list_sessions(
    current_user: CurrentUser,
    db: DbSession,
    page: int = 1,
    size: int = 20
):
    """获取对话会话列表"""
    # 计算偏移量
    offset = (page - 1) * size

    # 构建查询：联合查询会话和消息计数
    from sqlalchemy import func

    # 基础查询
    query = (
        select(
            ChatSession,
            func.count(ChatMessage.id).label("message_count")
        )
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.user_id == current_user.id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
    )

    # 获取总数
    count_query = select(func.count(ChatSession.id)).where(ChatSession.user_id == current_user.id)
    total = (await db.execute(count_query)).scalar_one()

    # 应用分页
    result = await db.execute(query.offset(offset).limit(size))
    rows = result.all()

    responses = []
    for session, message_count in rows:
        responses.append(ChatSessionResponse(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            message_count=message_count
        ))

    return PaginatedResponse(
        items=responses,
        total=total,
        page=page,
        page_size=size,
        total_pages=(total + size - 1) // size
    )


@router.get("/sessions/{session_id}", response_model=ChatSessionDetailResponse)
async def get_session(session_id: int, current_user: CurrentUser, db: DbSession):
    """获取对话会话详情（含消息列表）"""
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在"
        )

    # 获取消息
    msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    messages = msg_result.scalars().all()

    return ChatSessionDetailResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[ChatMessageResponse.model_validate(m) for m in messages]
    )


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
async def send_message(
    session_id: int,
    data: ChatMessageCreate,
    response: Response,
    current_user: CurrentUser,
    db: DbSession
):
    """
    发送消息并获取 AI 回复
    """
    request_id = _new_request_id()
    response.headers["X-Request-ID"] = request_id
    total_start = time.perf_counter()
    timings: dict[str, Any] = {
        "cloud_called": False,
        "request_type": "json",
    }

    # 验证会话存在
    stage_start = time.perf_counter()
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    timings["session_lookup_ms"] = _elapsed_ms(stage_start)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在"
        )

    ui_preferences = _ui_preferences_payload(data)
    user_attachments = dict(data.attachments or {})
    user_attachments["ui_preferences"] = ui_preferences

    # 保存用户消息
    stage_start = time.perf_counter()
    user_message = ChatMessage(
        session_id=session_id,
        role=MessageRole.USER,
        content=data.content,
        attachments=user_attachments
    )
    db.add(user_message)
    await db.flush()
    timings["user_message_flush_ms"] = _elapsed_ms(stage_start)

    # 获取历史消息
    stage_start = time.perf_counter()
    history = await _load_recent_history(db, session_id)
    timings["history_query_ms"] = _elapsed_ms(stage_start)
    timings["history_message_count"] = len(history)

    # 构建消息列表
    messages, history_chars = _history_to_prompt_messages(history)
    timings["history_chars"] = history_chars

    # 获取用户健康状况
    stage_start = time.perf_counter()
    conditions = await get_user_conditions(current_user.id, db)
    timings["conditions_query_ms"] = _elapsed_ms(stage_start)

    stage_start = time.perf_counter()
    summary = await knowledge_service.summarize_query_for_user(
        db,
        user=current_user,
        conditions=conditions,
        query=data.content,
    )
    timings["knowledge_summary_ms"] = _elapsed_ms(stage_start)

    called_cloud = False
    cloud_call_reason = None
    cloud_blocked_reason = None
    ai_metrics: dict[str, Any] = {}
    if _is_local_direct_response(summary):
        ai_response = knowledge_service.render_local_markdown(summary)
        if summary.fallback_status == FallbackStatus.LOCAL_BLOCKED_NO_CLOUD:
            cloud_blocked_reason = "本地命中过敏、AVOID 或 LIMIT 约束，云端不得放宽。"
        else:
            cloud_blocked_reason = "本地知识已足够回答当前问题，无需调用云端。"
        response_origin = summary.origin
        timings["prompt_build_ms"] = 0
        timings["prompt_chars"] = 0
        timings["message_count"] = len(messages)
        timings["doubao_total_ms"] = 0
        timings["response_chars"] = len(ai_response)
    else:
        called_cloud = True
        timings["cloud_called"] = True
        cloud_call_reason = {
            FallbackStatus.LOCAL_PARTIAL_ALLOW_CLOUD: "本地已命中部分知识，调用云端补充解释与替代建议。",
            FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD: "本地知识未命中，调用云端兜底。",
        }.get(summary.fallback_status, "调用云端补充说明。")
        ai_response = await doubao_service.chat(
            messages=messages,
            user=current_user,
            conditions=conditions,
            stream=False,
            local_guardrail=knowledge_service.build_local_guardrail(summary),
            assistant_preferences=ui_preferences,
            metrics=ai_metrics,
        )
        stage_start = time.perf_counter()
        ai_response, summary = await knowledge_service.post_review_llm_output_for_user(
            db,
            user=current_user,
            conditions=conditions,
            query_summary=summary,
            llm_text=ai_response,
            context_label="AI 回复",
        )
        timings["post_review_ms"] = _elapsed_ms(stage_start)
        timings.update(ai_metrics)
        response_origin = summary.origin
        timings.setdefault("response_chars", len(ai_response or ""))

    # 保存 AI 回复
    stage_start = time.perf_counter()
    attachments = _knowledge_attachment(
        response_origin=response_origin,
        summary=summary,
        called_cloud=called_cloud,
        cloud_call_reason=cloud_call_reason,
        cloud_blocked_reason=cloud_blocked_reason,
    )
    attachments["ui_preferences"] = ui_preferences
    assistant_message = ChatMessage(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=ai_response,
        attachments=attachments,
        model="doubao"
    )
    db.add(assistant_message)
    await db.flush()
    await db.refresh(assistant_message)
    timings["assistant_flush_ms"] = _elapsed_ms(stage_start)

    stage_start = time.perf_counter()
    await write_knowledge_audit_log(
        db,
        user_id=current_user.id,
        route_name="/api/chat/sessions/{session_id}/messages",
        chat_session_id=session_id,
        chat_message_id=assistant_message.id,
        query_excerpt=data.content,
        origin=response_origin,
        fallback_status=summary.fallback_status,
        matched_disease_codes=summary.matched_disease_codes,
        matched_food_codes=summary.matched_food_codes,
        unmapped_conditions=summary.unmapped_conditions,
        local_decision_level=pick_strictest_recommendation_level(summary.local_decisions),
        called_cloud=called_cloud,
        cloud_call_reason=cloud_call_reason,
        cloud_blocked_reason=cloud_blocked_reason,
    )
    timings["audit_flush_ms"] = _elapsed_ms(stage_start)
    timings["fallback_status"] = summary.fallback_status.value
    timings["origin"] = response_origin.value
    timings["chat_total_ms"] = _elapsed_ms(total_start)
    assistant_message.attachments = _merge_chat_attachments(assistant_message.attachments, timings)
    await db.flush()
    _log_chat_timing(request_id, timings)

    return ChatMessageResponse.model_validate(assistant_message)


@router.post("/sessions/{session_id}/messages/stream")
async def send_message_stream(
    session_id: int,
    data: ChatMessageCreate,
    current_user: CurrentUser,
    db: DbSession
):
    """
    流式发送消息并获取 AI 回复。

    使用 SSE-like 事件格式，前端通过 fetch stream 读取。
    """
    request_id = _new_request_id()

    async def event_stream() -> AsyncGenerator[str, None]:
        total_start = time.perf_counter()
        timings: dict[str, Any] = {
            "cloud_called": False,
            "request_type": "stream",
        }
        summary = None
        response_origin = KnowledgeOrigin.CLOUD_SUPPLEMENT
        called_cloud = False
        cloud_call_reason = None
        cloud_blocked_reason = None
        assistant_message = None
        response_parts: list[str] = []

        yield _sse_event("meta", {"request_id": request_id, "session_id": session_id})

        try:
            yield _sse_event("status", {"stage": "session_lookup", "message": "正在确认会话..."})
            stage_start = time.perf_counter()
            result = await db.execute(
                select(ChatSession).where(
                    ChatSession.id == session_id,
                    ChatSession.user_id == current_user.id
                )
            )
            session = result.scalar_one_or_none()
            timings["session_lookup_ms"] = _elapsed_ms(stage_start)
            if not session:
                yield _sse_event("error", {"message": "会话不存在", "request_id": request_id})
                return

            ui_preferences = _ui_preferences_payload(data)
            user_attachments = dict(data.attachments or {})
            user_attachments["ui_preferences"] = ui_preferences

            stage_start = time.perf_counter()
            user_message = ChatMessage(
                session_id=session_id,
                role=MessageRole.USER,
                content=data.content,
                attachments=user_attachments,
            )
            db.add(user_message)
            await db.flush()
            timings["user_message_flush_ms"] = _elapsed_ms(stage_start)

            stage_start = time.perf_counter()
            history = await _load_recent_history(db, session_id)
            timings["history_query_ms"] = _elapsed_ms(stage_start)
            timings["history_message_count"] = len(history)
            messages, history_chars = _history_to_prompt_messages(history)
            timings["history_chars"] = history_chars

            yield _sse_event("status", {"stage": "knowledge_check", "message": "正在检查本地饮食规则..."})
            stage_start = time.perf_counter()
            conditions = await get_user_conditions(current_user.id, db)
            timings["conditions_query_ms"] = _elapsed_ms(stage_start)

            stage_start = time.perf_counter()
            summary = await knowledge_service.summarize_query_for_user(
                db,
                user=current_user,
                conditions=conditions,
                query=data.content,
            )
            timings["knowledge_summary_ms"] = _elapsed_ms(stage_start)

            if _is_local_direct_response(summary):
                ai_response = knowledge_service.render_local_markdown(summary)
                response_parts.append(ai_response)
                if summary.fallback_status == FallbackStatus.LOCAL_BLOCKED_NO_CLOUD:
                    cloud_blocked_reason = "本地命中过敏、AVOID 或 LIMIT 约束，云端不得放宽。"
                else:
                    cloud_blocked_reason = "本地知识已足够回答当前问题，无需调用云端。"
                response_origin = summary.origin
                timings["prompt_build_ms"] = 0
                timings["prompt_chars"] = 0
                timings["message_count"] = len(messages)
                timings["doubao_first_chunk_ms"] = 0
                timings["doubao_total_ms"] = 0
                timings["response_chars"] = len(ai_response)
                yield _sse_event("status", {"stage": "local_answer", "message": "已命中本地规则，正在生成回复..."})
                timings["stream_first_chunk_ms"] = _elapsed_ms(total_start)
                yield _sse_event("delta", {"content": ai_response})
            else:
                called_cloud = True
                timings["cloud_called"] = True
                cloud_call_reason = {
                    FallbackStatus.LOCAL_PARTIAL_ALLOW_CLOUD: "本地已命中部分知识，调用云端补充解释与替代建议。",
                    FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD: "本地知识未命中，调用云端兜底。",
                }.get(summary.fallback_status, "调用云端补充说明。")
                yield _sse_event("status", {"stage": "model_connect", "message": "正在连接模型..."})
                ai_metrics: dict[str, Any] = {}
                stream = await doubao_service.chat(
                    messages=messages,
                    user=current_user,
                    conditions=conditions,
                    stream=True,
                    local_guardrail=knowledge_service.build_local_guardrail(summary),
                    assistant_preferences=ui_preferences,
                    metrics=ai_metrics,
                )
                yield _sse_event("status", {"stage": "model_generate", "message": "正在生成回复..."})
                async for chunk in stream:
                    if not chunk:
                        continue
                    response_parts.append(chunk)
                timings.update(ai_metrics)
                cloud_response = "".join(response_parts)
                yield _sse_event("status", {"stage": "local_post_review", "message": "正在复核本地饮食规则..."})
                stage_start = time.perf_counter()
                cloud_response, summary = await knowledge_service.post_review_llm_output_for_user(
                    db,
                    user=current_user,
                    conditions=conditions,
                    query_summary=summary,
                    llm_text=cloud_response,
                    context_label="AI 回复",
                )
                timings["post_review_ms"] = _elapsed_ms(stage_start)
                response_parts = [cloud_response]
                timings.setdefault("stream_first_chunk_ms", _elapsed_ms(total_start))
                yield _sse_event("delta", {"content": cloud_response})
                response_origin = summary.origin

            ai_response = "".join(response_parts)
            timings.setdefault("stream_first_chunk_ms", None)
            timings.setdefault("response_chars", len(ai_response))

            stage_start = time.perf_counter()
            attachments = _knowledge_attachment(
                response_origin=response_origin,
                summary=summary,
                called_cloud=called_cloud,
                cloud_call_reason=cloud_call_reason,
                cloud_blocked_reason=cloud_blocked_reason,
            )
            attachments["ui_preferences"] = ui_preferences
            assistant_message = ChatMessage(
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                content=ai_response,
                attachments=attachments,
                model="doubao",
            )
            db.add(assistant_message)
            await db.flush()
            await db.refresh(assistant_message)
            timings["assistant_flush_ms"] = _elapsed_ms(stage_start)
            timings["stream_done_ms"] = _elapsed_ms(total_start)
            attachments = _merge_chat_attachments(attachments, timings)
            assistant_message.attachments = attachments
            await db.flush()

            stage_start = time.perf_counter()
            await _commit_if_supported(db)
            timings["assistant_commit_ms"] = _elapsed_ms(stage_start)

            yield _sse_event(
                "done",
                {
                    "request_id": request_id,
                    "message_id": assistant_message.id,
                    "origin": response_origin.value,
                    "fallback_status": summary.fallback_status.value,
                    "attachments": attachments,
                },
            )

            try:
                stage_start = time.perf_counter()
                await write_knowledge_audit_log(
                    db,
                    user_id=current_user.id,
                    route_name="/api/chat/sessions/{session_id}/messages/stream",
                    chat_session_id=session_id,
                    chat_message_id=assistant_message.id,
                    query_excerpt=data.content,
                    origin=response_origin,
                    fallback_status=summary.fallback_status,
                    matched_disease_codes=summary.matched_disease_codes,
                    matched_food_codes=summary.matched_food_codes,
                    unmapped_conditions=summary.unmapped_conditions,
                    local_decision_level=pick_strictest_recommendation_level(summary.local_decisions),
                    called_cloud=called_cloud,
                    cloud_call_reason=cloud_call_reason,
                    cloud_blocked_reason=cloud_blocked_reason,
                )
                timings["audit_flush_ms"] = _elapsed_ms(stage_start)
                stage_start = time.perf_counter()
                await _commit_if_supported(db)
                timings["audit_commit_ms"] = _elapsed_ms(stage_start)
            except Exception as audit_exc:
                await _rollback_if_supported(db)
                timings["audit_flush_ms"] = None
                timings["audit_error"] = audit_exc.__class__.__name__
                logger.warning("Streaming chat audit write failed", extra={"request_id": request_id})
            timings["fallback_status"] = summary.fallback_status.value
            timings["origin"] = response_origin.value
            timings["chat_total_ms"] = _elapsed_ms(total_start)
            _log_chat_timing(request_id, timings)
        except Exception as exc:
            await _rollback_if_supported(db)
            logger.exception("Streaming chat failed", extra={"request_id": request_id})
            timings.setdefault("assistant_flush_ms", 0)
            timings.setdefault("audit_flush_ms", 0)
            timings["fallback_status"] = summary.fallback_status.value if summary else None
            timings["origin"] = response_origin.value if response_origin else None
            timings["chat_total_ms"] = _elapsed_ms(total_start)
            timings["error"] = exc.__class__.__name__
            _log_chat_timing(request_id, timings)
            yield _sse_event(
                "error",
                {
                    "request_id": request_id,
                    "message": str(exc) or "生成失败，请稍后重试。",
                },
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
        },
    )


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, current_user: CurrentUser, db: DbSession):
    """删除对话会话"""
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在"
        )

    await db.delete(session)
    await db.flush()

    return {"success": True, "message": "删除成功"}


@router.post(
    "/messages/{message_id}/feedback",
    response_model=AIFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message_feedback(
    message_id: int,
    data: AIFeedbackCreate,
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
):
    """Record user feedback for an AI response without logging raw correction text."""
    message = await _load_owned_chat_message(db, user_id=current_user.id, message_id=message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息不存在")
    if message.role != MessageRole.ASSISTANT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能反馈 AI 回复消息")

    correction_text = (data.correction_text or "").strip() or None
    feedback = AIFeedback(
        user_id=current_user.id,
        session_id=message.session_id,
        message_id=message.id,
        feedback_type=data.feedback_type,
        rating=data.rating,
        tags_json=_normalize_feedback_tags(data.tags),
        correction_text=correction_text,
        correction_text_hash=hash_sensitive_value(correction_text),
        metadata_json=_safe_feedback_metadata(data.metadata),
    )
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)
    await audit_security_event(
        db,
        event_type="ai.feedback.create",
        event_status="success",
        user_id=current_user.id,
        request=request,
        route_name="/api/chat/messages/{message_id}/feedback",
        metadata=_feedback_audit_metadata(feedback),
    )
    return _feedback_response(feedback)


@router.get("/messages/{message_id}/feedback", response_model=list[AIFeedbackResponse])
async def list_message_feedback(message_id: int, current_user: CurrentUser, db: DbSession):
    """List current user's feedback for one AI message."""
    message = await _load_owned_chat_message(db, user_id=current_user.id, message_id=message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息不存在")

    result = await db.execute(
        select(AIFeedback)
        .where(AIFeedback.user_id == current_user.id, AIFeedback.message_id == message_id)
        .order_by(AIFeedback.created_at.desc(), AIFeedback.id.desc())
    )
    return [_feedback_response(item) for item in result.scalars().all()]


@router.post("/recognize-food", response_model=FoodRecognitionResponse)
async def recognize_food(
    data: FoodRecognitionRequest,
    current_user: CurrentUser,
    db: DbSession
):
    """
    识别食物图片

    上传食物图片，AI 识别并返回营养成分分析
    """
    from app.core.config import settings

    try:
        raw_image, content_type = _decode_image_payload(data.image_base64, data.image_type)
        sanitized = sanitize_image_upload(
            raw_image,
            content_type=content_type,
            max_size_bytes=settings.max_upload_size_mb * 1024 * 1024,
            max_pixels=settings.max_upload_image_pixels,
        )
    except ValueError as exc:
        status_code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if "大小超过限制" in str(exc) or "像素超过限制" in str(exc)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    # 获取用户健康状况
    conditions = await get_user_conditions(current_user.id, db)

    # 调用 AI 识别
    foods, ai_response = await doubao_service.recognize_food(
        image_base64=base64.b64encode(sanitized.content).decode("utf-8"),
        user=current_user,
        conditions=conditions,
        image_type="jpeg" if sanitized.format == "JPEG" else "png",
        user_prompt=data.prompt,
    )

    matched_disease_codes: list[str] = []
    matched_food_codes: list[str] = []
    strictest_level = None
    fallback_status = FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD
    local_notes: list[str] = []
    local_decisions = []
    for food in foods:
        decision = await knowledge_service.evaluate_food_for_user(
            db,
            user=current_user,
            conditions=conditions,
            food_name=food.food_name,
        )
        local_decisions.append(decision)
        matched_disease_codes.extend(decision.matched_disease_codes)
        if decision.food_code:
            matched_food_codes.append(decision.food_code)
        if decision.recommendation_level in {RecommendationLevel.AVOID, RecommendationLevel.LIMIT}:
            food.warnings.append(f"本地规则：{decision.food_name} -> {decision.recommendation_level.value}")
            food.warnings.extend(decision.hard_blocks)
            local_notes.append(f"{decision.food_name}：{decision.recommendation_level.value}，{decision.summary}")
        strictest_level = _pick_stricter_level(strictest_level, decision.recommendation_level)
        fallback_status = decision.fallback_status if decision.fallback_status == FallbackStatus.LOCAL_BLOCKED_NO_CLOUD else fallback_status

    if local_notes:
        ai_response = "本地规则提示：\n- " + "\n- ".join(local_notes) + "\n\n" + ai_response
    ai_response = knowledge_service.enforce_llm_output_safety(
        ai_response,
        local_decisions=local_decisions,
        fallback_status=fallback_status,
        context_label="图片识别回复",
    )

    await write_knowledge_audit_log(
        db,
        user_id=current_user.id,
        route_name="/api/chat/recognize-food",
        query_excerpt="image_base64",
        origin=KnowledgeOrigin.MIXED if foods else KnowledgeOrigin.CLOUD_SUPPLEMENT,
        fallback_status=fallback_status,
        matched_disease_codes=_dedupe(matched_disease_codes),
        matched_food_codes=_dedupe(matched_food_codes),
        local_decision_level=strictest_level,
        called_cloud=True,
        cloud_call_reason="图片识别依赖主多模态模型，本地规则在识别后补充校验。",
    )

    return FoodRecognitionResponse(
        success=len(foods) > 0,
        foods=foods,
        ai_response=ai_response
    )


@router.post("/recognize-food/upload", response_model=FoodRecognitionResponse)
async def recognize_food_upload(
    file: UploadFile = File(...),
    prompt: Optional[str] = Form(None),
    session_id: Optional[int] = Form(None),
    current_user: CurrentUser = None,
    db: DbSession = None
):
    """
    上传图片文件进行食物识别
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

    recognition_session = None
    if session_id is not None:
        recognition_session = await _load_owned_chat_session(
            db,
            user_id=current_user.id,
            session_id=session_id,
        )
        if not recognition_session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    image_base64 = base64.b64encode(image.content).decode("utf-8")

    # 获取用户健康状况
    conditions = await get_user_conditions(current_user.id, db)

    # 调用 AI 识别
    foods, ai_response = await doubao_service.recognize_food(
        image_base64=image_base64,
        user=current_user,
        conditions=conditions,
        image_type="jpeg" if image.format == "JPEG" else "png",
        user_prompt=prompt,
    )

    matched_disease_codes: list[str] = []
    matched_food_codes: list[str] = []
    strictest_level = None
    fallback_status = FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD
    local_notes: list[str] = []
    local_decisions = []
    for food in foods:
        decision = await knowledge_service.evaluate_food_for_user(
            db,
            user=current_user,
            conditions=conditions,
            food_name=food.food_name,
        )
        local_decisions.append(decision)
        matched_disease_codes.extend(decision.matched_disease_codes)
        if decision.food_code:
            matched_food_codes.append(decision.food_code)
        if decision.recommendation_level in {RecommendationLevel.AVOID, RecommendationLevel.LIMIT}:
            food.warnings.append(f"本地规则：{decision.food_name} -> {decision.recommendation_level.value}")
            food.warnings.extend(decision.hard_blocks)
            local_notes.append(f"{decision.food_name}：{decision.recommendation_level.value}，{decision.summary}")
        strictest_level = _pick_stricter_level(strictest_level, decision.recommendation_level)
        fallback_status = decision.fallback_status if decision.fallback_status == FallbackStatus.LOCAL_BLOCKED_NO_CLOUD else fallback_status

    if local_notes:
        ai_response = "本地规则提示：\n- " + "\n- ".join(local_notes) + "\n\n" + ai_response
    ai_response = knowledge_service.enforce_llm_output_safety(
        ai_response,
        local_decisions=local_decisions,
        fallback_status=fallback_status,
        context_label="图片识别回复",
    )

    assistant_message = None
    recognition_origin = KnowledgeOrigin.MIXED if foods else KnowledgeOrigin.CLOUD_SUPPLEMENT
    if recognition_session is not None:
        assistant_message = ChatMessage(
            session_id=recognition_session.id,
            role=MessageRole.ASSISTANT,
            content=ai_response or "已完成图片识别。",
            attachments=_recognition_message_attachments(
                foods=foods,
                origin=recognition_origin,
                fallback_status=fallback_status,
                matched_disease_codes=matched_disease_codes,
                matched_food_codes=matched_food_codes,
            ),
            model="doubao",
        )
        db.add(assistant_message)
        await db.flush()
        await db.refresh(assistant_message)

    await write_knowledge_audit_log(
        db,
        user_id=current_user.id,
        route_name="/api/chat/recognize-food/upload",
        query_excerpt="image_upload",
        chat_session_id=recognition_session.id if recognition_session else None,
        chat_message_id=assistant_message.id if assistant_message else None,
        origin=recognition_origin,
        fallback_status=fallback_status,
        matched_disease_codes=_dedupe(matched_disease_codes),
        matched_food_codes=_dedupe(matched_food_codes),
        local_decision_level=strictest_level,
        called_cloud=True,
        cloud_call_reason="图片识别依赖主多模态模型，本地规则在识别后补充校验。",
    )

    return FoodRecognitionResponse(
        success=len(foods) > 0,
        foods=foods,
        ai_response=ai_response,
        message_id=assistant_message.id if assistant_message else None,
    )


def _pick_stricter_level(current, candidate):
    if candidate is None:
        return current
    if current is None:
        return candidate
    order = {
        RecommendationLevel.RECOMMEND: 0,
        RecommendationLevel.MODERATE: 1,
        RecommendationLevel.CONDITIONAL: 2,
        RecommendationLevel.INSUFFICIENT: 3,
        RecommendationLevel.LIMIT: 4,
        RecommendationLevel.AVOID: 5,
    }
    return candidate if order[candidate] > order[current] else current


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _decode_image_payload(image_base64: str, image_type: str) -> tuple[bytes, str]:
    raw = image_base64.strip()
    content_type = f"image/{(image_type or 'jpeg').lower()}"
    if raw.startswith("data:image/"):
        header, _, payload = raw.partition(",")
        if ";base64" not in header or not payload:
            raise ValueError("图片 data URL 格式无效")
        content_type = header.removeprefix("data:").split(";", 1)[0]
        raw = payload
    try:
        return base64.b64decode(raw, validate=True), content_type
    except (binascii.Error, ValueError) as exc:
        raise ValueError("图片 Base64 格式无效") from exc


@router.post("/quick-log", response_model=MealResponse, status_code=status.HTTP_201_CREATED)
async def quick_log_from_recognition(
    data: QuickLogRequest,
    current_user: CurrentUser,
    db: DbSession
):
    """
    快速从识别结果添加饮食记录（前端传入 food_item）
    """
    if data.session_id is not None:
        session_result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == data.session_id,
                ChatSession.user_id == current_user.id
            )
        )
        if not session_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在"
            )

    try:
        meal_type = MealType(data.meal_type.upper())
    except Exception:
        meal_type = MealType.DINNER

    try:
        category = FoodCategory(data.food_item.category.upper())
    except Exception:
        category = FoodCategory.STAPLE

    nutrition = data.food_item.nutrition
    conditions = await get_user_conditions(current_user.id, db)
    result = await intake_service.confirm(
        db,
        user=current_user,
        conditions=conditions,
        data=IntakeConfirmRequest(
            source=IntakeSource.AI_QUICK_LOG,
            raw_summary="chat quick log",
            candidates=[
                IntakeConfirmItem(
                    draft_id=str(uuid.uuid4()),
                    source=IntakeSource.AI_QUICK_LOG,
                    meal_type=meal_type,
                    category=category,
                    food_name=data.food_item.food_name,
                    amount_text=data.food_item.estimated_portion or "1份",
                    confidence=0.75,
                    calories=nutrition.calories,
                    sodium=nutrition.sodium,
                    purine=nutrition.purine,
                    protein=nutrition.protein,
                    carbs=nutrition.carbs,
                    fat=nutrition.fat,
                    fiber=nutrition.fiber,
                    estimated_fields=[
                        "amount",
                        "calories",
                        "sodium",
                        "purine",
                        "protein",
                        "carbs",
                        "fat",
                        "fiber",
                    ],
                    estimated_notes=["来自聊天图片识别结果，确认时已重新执行本地规则。"],
                    origin=KnowledgeOrigin.CLOUD_SUPPLEMENT,
                    fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
                )
            ],
        ),
    )

    if not result.meals:
        detail = result.failed_items[0].reason if result.failed_items else "快捷记录失败"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    return result.meals[0]
