"""
用户数据模型
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class Gender(str, enum.Enum):
    """性别枚举"""
    MALE = "MALE"
    FEMALE = "FEMALE"


class User(Base):
    """用户表"""
    
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # 认证信息
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    
    # 基本信息
    nickname: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # 身体参数
    gender: Mapped[Optional[Gender]] = mapped_column(SQLEnum(Gender), nullable=True)
    age: Mapped[Optional[int]] = mapped_column(nullable=True)
    height: Mapped[Optional[float]] = mapped_column(nullable=True)  # cm
    weight: Mapped[Optional[float]] = mapped_column(nullable=True)  # kg
    
    # 账户状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # 关系
    meals: Mapped[list["Meal"]] = relationship(
        "Meal",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    conditions: Mapped[list["HealthCondition"]] = relationship(
        "HealthCondition",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    messages: Mapped[list["AppMessage"]] = relationship(
        "AppMessage",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession",
        back_populates="user",
        cascade="all, delete-orphan"
    )


# 导入关联模型以避免循环导入问题
from app.models.meal import Meal
from app.models.health_condition import HealthCondition
from app.models.message import AppMessage
from app.models.chat import ChatSession
