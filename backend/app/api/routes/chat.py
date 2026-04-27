"""
AI 对话 API 路由
"""

from typing import List

from fastapi import APIRouter, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
import base64

from app.api.deps import DbSession, CurrentUser
from app.models.chat import ChatSession, ChatMessage, MessageRole
from app.models.health_condition import HealthCondition
from app.models.meal import Meal, MealType, FoodCategory, SyncStatus
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
from app.services.ai_service import doubao_service
from app.services.knowledge import KnowledgeService, write_knowledge_audit_log
from app.models.knowledge import FallbackStatus, KnowledgeOrigin, RecommendationLevel
from datetime import date
import uuid

router = APIRouter(prefix="/chat", tags=["AI对话"])
knowledge_service = KnowledgeService()


async def get_user_conditions(user_id: int, db) -> List[HealthCondition]:
    """获取用户健康状况"""
    result = await db.execute(
        select(HealthCondition).where(HealthCondition.user_id == user_id)
    )
    return list(result.scalars().all())


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
    current_user: CurrentUser,
    db: DbSession
):
    """
    发送消息并获取 AI 回复
    """
    # 验证会话存在
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
    
    # 保存用户消息
    user_message = ChatMessage(
        session_id=session_id,
        role=MessageRole.USER,
        content=data.content,
        attachments=data.attachments
    )
    db.add(user_message)
    await db.flush()
    
    # 获取历史消息
    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .limit(20)  # 限制上下文长度
    )
    history = history_result.scalars().all()
    
    # 构建消息列表
    messages = [
        {"role": msg.role.value, "content": msg.content}
        for msg in history
    ]
    
    # 获取用户健康状况
    conditions = await get_user_conditions(current_user.id, db)
    
    summary = await knowledge_service.summarize_query_for_user(
        db,
        user=current_user,
        conditions=conditions,
        query=data.content,
    )

    called_cloud = False
    cloud_call_reason = None
    cloud_blocked_reason = None
    if summary.fallback_status in {FallbackStatus.LOCAL_BLOCKED_NO_CLOUD, FallbackStatus.LOCAL_COMPLETE} and summary.local_decisions:
        ai_response = knowledge_service.render_local_markdown(summary)
        if summary.fallback_status == FallbackStatus.LOCAL_BLOCKED_NO_CLOUD:
            cloud_blocked_reason = "本地命中过敏、AVOID 或 LIMIT 约束，云端不得放宽。"
        else:
            cloud_blocked_reason = "本地知识已足够回答当前问题，无需调用云端。"
        response_origin = summary.origin
    else:
        called_cloud = True
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
        )
        response_origin = KnowledgeOrigin.MIXED if summary.origin != KnowledgeOrigin.CLOUD_SUPPLEMENT else KnowledgeOrigin.CLOUD_SUPPLEMENT

    # 保存 AI 回复
    assistant_message = ChatMessage(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=ai_response,
        attachments={
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
        },
        model="doubao"
    )
    db.add(assistant_message)
    await db.flush()
    await db.refresh(assistant_message)

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
        local_decision_level=(
            max(
                (
                    decision.recommendation_level
                    for decision in summary.local_decisions
                    if decision.recommendation_level is not None
                ),
                key=lambda level: {
                    RecommendationLevel.RECOMMEND: 0,
                    RecommendationLevel.MODERATE: 1,
                    RecommendationLevel.CONDITIONAL: 2,
                    RecommendationLevel.INSUFFICIENT: 3,
                    RecommendationLevel.LIMIT: 4,
                    RecommendationLevel.AVOID: 5,
                }[level],
            )
            if summary.local_decisions
            else None
        ),
        called_cloud=called_cloud,
        cloud_call_reason=cloud_call_reason,
        cloud_blocked_reason=cloud_blocked_reason,
    )
    
    return ChatMessageResponse.model_validate(assistant_message)


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
        conditions=conditions
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
        cloud_call_reason="视觉识别依赖云端模型，本地规则在识别后补充校验。",
    )

    return FoodRecognitionResponse(
        success=len(foods) > 0,
        foods=foods,
        ai_response=ai_response
    )


@router.post("/recognize-food/upload", response_model=FoodRecognitionResponse)
async def recognize_food_upload(
    file: UploadFile = File(...),
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
        conditions=conditions
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
        cloud_call_reason="视觉识别依赖云端模型，本地规则在识别后补充校验。",
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
    meal = Meal(
        user_id=current_user.id,
        client_id=str(uuid.uuid4()),
        name=data.food_item.food_name,
        portion=data.food_item.estimated_portion or "1份",
        calories=nutrition.calories or 0,
        sodium=nutrition.sodium or 0,
        purine=nutrition.purine or 0,
        protein=nutrition.protein,
        carbs=nutrition.carbs,
        fat=nutrition.fat,
        fiber=nutrition.fiber,
        meal_type=meal_type,
        category=category,
        record_date=date.today(),
        ai_recognized=True,
        source="ai_quick_log",
        source_detail="chat_quick_log",
        confidence=0.75,
        estimated_fields_json=["amount", "calories", "sodium", "purine", "protein", "carbs", "fat", "fiber"],
        rule_warnings_json=[],
        recognition_meta_json={"origin": "chat_quick_log"},
        sync_status=SyncStatus.SYNCED
    )
    db.add(meal)
    await db.flush()
    await db.refresh(meal)
    return MealResponse.model_validate(meal)
