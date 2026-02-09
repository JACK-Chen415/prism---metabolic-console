"""
消息通知数据模型
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class MessageType(str, enum.Enum):
    """消息类型"""
    WARNING = "WARNING"  # 预警
    ADVICE = "ADVICE"    # 建议
    BRIEF = "BRIEF"      # 简报


class AppMessage(Base):
    """应用消息表"""
    
    __tablename__ = "app_messages"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # 所属用户
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    
    # 消息内容
    message_type: Mapped[MessageType] = mapped_column(SQLEnum(MessageType), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    attribution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 归因说明
    
    # 状态
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # 关系
    user: Mapped["User"] = relationship("User", back_populates="messages")


from app.models.user import User
