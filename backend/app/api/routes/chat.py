"""
AI 对话 API 路由
"""

from typing import Any, AsyncGenerator, List, Optional

from fastapi import APIRouter, HTTPException, Response, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select
import base64
import json
import logging
import time

from app.api.deps import DbSession, CurrentUser
from app.core.config import settings
from app.models.chat import ChatSession, ChatMessage, MessageRole
from app.models.health_condition import HealthCondition
from app.models.meal import MealType, FoodCategory
from app.schemas.chat import (
    ChatMessageCreate,
    ChatSessionCreate,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSessionDetailResponse,
    FoodRecognitionRequest,
    FoodRecognitionResponse,
    QuickLogRequest
)
from app.schemas.common import PaginatedResponse
from app.schemas.meal import MealResponse
from app.schemas.intake import IntakeConfirmItem, IntakeConfirmRequest, IntakeSource
from app.services.ai_service import doubao_service
from app.services.intake import IntakeService
from app.services.knowledge import KnowledgeService, write_knowledge_audit_log
from app.services.knowledge.severity import pick_strictest_recommendation_level
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
    
    # 保存用户消息
    stage_start = time.perf_counter()
    user_message = ChatMessage(
        session_id=session_id,
        role=MessageRole.USER,
        content=data.content,
        attachments=data.attachments
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
            metrics=ai_metrics,
        )
        timings.update(ai_metrics)
        response_origin = KnowledgeOrigin.MIXED if summary.origin != KnowledgeOrigin.CLOUD_SUPPLEMENT else KnowledgeOrigin.CLOUD_SUPPLEMENT
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

            stage_start = time.perf_counter()
            user_message = ChatMessage(
                session_id=session_id,
                role=MessageRole.USER,
                content=data.content,
                attachments=data.attachments,
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
                    metrics=ai_metrics,
                )
                yield _sse_event("status", {"stage": "model_generate", "message": "正在生成回复..."})
                async for chunk in stream:
                    if not chunk:
                        continue
                    response_parts.append(chunk)
                    timings.setdefault("stream_first_chunk_ms", _elapsed_ms(total_start))
                    yield _sse_event("delta", {"content": chunk})
                timings.update(ai_metrics)
                response_origin = KnowledgeOrigin.MIXED if summary.origin != KnowledgeOrigin.CLOUD_SUPPLEMENT else KnowledgeOrigin.CLOUD_SUPPLEMENT

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

            stage_start = time.perf_counter()
            await _commit_if_supported(db)
            timings["assistant_commit_ms"] = _elapsed_ms(stage_start)

            timings["stream_done_ms"] = _elapsed_ms(total_start)
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
    # 获取用户健康状况
    conditions = await get_user_conditions(current_user.id, db)
    
    # 调用 AI 识别
    foods, ai_response = await doubao_service.recognize_food(
        image_base64=data.image_base64,
        user=current_user,
        conditions=conditions,
        image_type=data.image_type,
        user_prompt=data.prompt,
    )
    
    matched_disease_codes: list[str] = []
    matched_food_codes: list[str] = []
    strictest_level = None
    fallback_status = FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD
    local_notes: list[str] = []
    for food in foods:
        decision = await knowledge_service.evaluate_food_for_user(
            db,
            user=current_user,
            conditions=conditions,
            food_name=food.food_name,
        )
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
    current_user: CurrentUser = None,
    db: DbSession = None
):
    """
    上传图片文件进行食物识别
    """
    # 验证文件类型
    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请上传图片文件"
        )
    
    # 读取并编码
    content = await file.read()
    
    # 检查文件大小
    from app.core.config import settings
    max_size = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件大小超过限制（最大 {settings.max_upload_size_mb}MB）"
        )
    
    image_base64 = base64.b64encode(content).decode("utf-8")
    
    # 获取用户健康状况
    conditions = await get_user_conditions(current_user.id, db)
    
    # 调用 AI 识别
    foods, ai_response = await doubao_service.recognize_food(
        image_base64=image_base64,
        user=current_user,
        conditions=conditions,
        image_type=file.content_type.split("/", 1)[1] if file.content_type else "jpeg",
        user_prompt=prompt,
    )
    
    matched_disease_codes: list[str] = []
    matched_food_codes: list[str] = []
    strictest_level = None
    fallback_status = FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD
    local_notes: list[str] = []
    for food in foods:
        decision = await knowledge_service.evaluate_food_for_user(
            db,
            user=current_user,
            conditions=conditions,
            food_name=food.food_name,
        )
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

    await write_knowledge_audit_log(
        db,
        user_id=current_user.id,
        route_name="/api/chat/recognize-food/upload",
        query_excerpt=file.filename,
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
