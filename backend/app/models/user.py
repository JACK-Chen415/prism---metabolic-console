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


class UserRole(str, enum.Enum):
    """运营权限角色。"""
    USER = "USER"
    ADMIN = "ADMIN"
    COACH = "COACH"


class SubscriptionPlan(str, enum.Enum):
    """订阅档位。"""
    FREE = "FREE"
    PRO = "PRO"
    COACH = "COACH"


class SubscriptionStatus(str, enum.Enum):
    """订阅状态。"""
    INACTIVE = "inactive"
    ACTIVE = "active"
    CANCELED = "canceled"


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
    consent_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    consent_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_terms_accepted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    consent_privacy_accepted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    consent_ai_use_accepted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    consent_health_disclaimer_accepted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(
            UserRole,
            name="userrole",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=UserRole.USER,
        server_default=UserRole.USER.value,
        nullable=False,
    )
    subscription_plan: Mapped[SubscriptionPlan] = mapped_column(
        SQLEnum(
            SubscriptionPlan,
            name="subscriptionplan",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=SubscriptionPlan.FREE,
        server_default=SubscriptionPlan.FREE.value,
        nullable=False,
    )
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        SQLEnum(
            SubscriptionStatus,
            name="subscriptionstatus",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=SubscriptionStatus.INACTIVE,
        server_default=SubscriptionStatus.INACTIVE.value,
        nullable=False,
    )
    subscription_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

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
    favorite_meals: Mapped[list["FavoriteMeal"]] = relationship(
        "FavoriteMeal",
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
    knowledge_audit_logs: Mapped[list["KnowledgeAuditLog"]] = relationship(
        "KnowledgeAuditLog",
        back_populates="user",
        cascade="save-update, merge"
    )
    device_sessions: Mapped[list["DeviceSession"]] = relationship(
        "DeviceSession",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    security_audit_logs: Mapped[list["SecurityAuditLog"]] = relationship(
        "SecurityAuditLog",
        back_populates="user",
        cascade="save-update, merge"
    )
    health_metrics: Mapped[list["HealthMetric"]] = relationship(
        "HealthMetric",
        back_populates="user",
        cascade="all, delete-orphan"
    )


# 导入关联模型以避免循环导入问题
from app.models.meal import FavoriteMeal, Meal
from app.models.health_condition import HealthCondition
from app.models.message import AppMessage
from app.models.security import DeviceSession, SecurityAuditLog
from app.models.chat import ChatSession
from app.models.health_metric import HealthMetric
