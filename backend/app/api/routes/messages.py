"""
消息通知 API 路由
"""

from typing import List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func

from app.api.deps import DbSession, CurrentUser
from app.models.message import AppMessage, MessageType
from pydantic import BaseModel, Field
from typing import Optional


# ========== Schemas ==========

class MessageCreate(BaseModel):
    """创建消息（内部使用）"""
    message_type: MessageType
    title: str = Field(..., max_length=100)
    content: str
    attribution: Optional[str] = None


class MessageResponse(BaseModel):
    """消息响应"""
    id: int
    message_type: MessageType
    title: str
    content: str
    attribution: Optional[str] = None
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


router = APIRouter(prefix="/messages", tags=["消息通知"])


@router.get("", response_model=List[MessageResponse])
async def list_messages(
    current_user: CurrentUser,
    db: DbSession,
    unread_only: bool = Query(False, description="仅返回未读消息"),
    message_type: Optional[MessageType] = Query(None, description="消息类型筛选"),
    limit: int = Query(50, ge=1, le=100)
):
    """获取消息列表"""
    query = select(AppMessage).where(AppMessage.user_id == current_user.id)
    
    if unread_only:
        query = query.where(AppMessage.is_read == False)
    
    if message_type:
        query = query.where(AppMessage.message_type == message_type)
    
    query = query.order_by(AppMessage.created_at.desc()).limit(limit)
    
    result = await db.execute(query)
    messages = result.scalars().all()
    
    return [MessageResponse.model_validate(m) for m in messages]


@router.get("/unread-count")
async def get_unread_count(current_user: CurrentUser, db: DbSession):
    """获取未读消息数量"""
    result = await db.execute(
        select(func.count(AppMessage.id)).where(
            AppMessage.user_id == current_user.id,
            AppMessage.is_read == False
        )
    )
    count = result.scalar() or 0
    return {"unread_count": count}


@router.get("/{message_id}", response_model=MessageResponse)
async def get_message(message_id: int, current_user: CurrentUser, db: DbSession):
    """获取单条消息"""
    result = await db.execute(
        select(AppMessage).where(
            AppMessage.id == message_id,
            AppMessage.user_id == current_user.id
        )
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="消息不存在"
        )
    
    return MessageResponse.model_validate(message)


@router.post("/{message_id}/read")
async def mark_as_read(message_id: int, current_user: CurrentUser, db: DbSession):
    """标记消息为已读"""
    result = await db.execute(
        select(AppMessage).where(
            AppMessage.id == message_id,
            AppMessage.user_id == current_user.id
        )
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="消息不存在"
        )
    
    if not message.is_read:
        message.is_read = True
        message.read_at = datetime.now(timezone.utc)
        await db.flush()
    
    return {"success": True, "message": "已标记为已读"}


@router.post("/read-all")
async def mark_all_as_read(current_user: CurrentUser, db: DbSession):
    """标记所有消息为已读"""
    result = await db.execute(
        select(AppMessage).where(
            AppMessage.user_id == current_user.id,
            AppMessage.is_read == False
        )
    )
    messages = result.scalars().all()
    
    now = datetime.now(timezone.utc)
    for msg in messages:
        msg.is_read = True
        msg.read_at = now
    
    await db.flush()
    
    return {"success": True, "message": f"已标记 {len(messages)} 条消息为已读"}


@router.delete("/{message_id}")
async def delete_message(message_id: int, current_user: CurrentUser, db: DbSession):
    """删除消息"""
    result = await db.execute(
        select(AppMessage).where(
            AppMessage.id == message_id,
            AppMessage.user_id == current_user.id
        )
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="消息不存在"
        )
    
    await db.delete(message)
    await db.flush()
    
    return {"success": True, "message": "删除成功"}
