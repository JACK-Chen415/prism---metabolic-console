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
from app.models.meal import Meal, MealType, FoodCategory
from app.schemas.chat import (
    ChatMessageCreate,
    ChatSessionCreate,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSessionDetailResponse,
    FoodRecognitionRequest,
    FoodRecognitionResponse
)
from app.schemas.common import PaginatedResponse
from app.services.ai_service import doubao_service
from datetime import date
import uuid

router = APIRouter(prefix="/chat", tags=["AI对话"])


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
    
    # 调用 AI
    ai_response = await doubao_service.chat(
        messages=messages,
        user=current_user,
        conditions=conditions,
        stream=False
    )
    
    # 保存 AI 回复
    assistant_message = ChatMessage(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=ai_response,
        model="doubao"
    )
    db.add(assistant_message)
    await db.flush()
    await db.refresh(assistant_message)
    
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
    
    return FoodRecognitionResponse(
        success=len(foods) > 0,
        foods=foods,
        ai_response=ai_response
    )


@router.post("/quick-log", response_model=dict)
async def quick_log_from_recognition(
    food_index: int,
    session_id: int,
    meal_type: MealType,
    current_user: CurrentUser,
    db: DbSession
):
    """
    快速从识别结果添加饮食记录
    
    从最近的识别结果中选择一个食物添加到饮食日志
    """
    # 这里需要从会话上下文中获取识别结果
    # 简化实现：直接从消息中解析
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="此功能尚在开发中"
    )
