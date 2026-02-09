"""
健康状况数据模型（慢性病与过敏史）
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class ConditionType(str, enum.Enum):
    """病症类型"""
    CHRONIC = "CHRONIC"   # 慢性病
    ALLERGY = "ALLERGY"   # 过敏


class ConditionStatus(str, enum.Enum):
    """状态"""
    ACTIVE = "ACTIVE"         # 活跃/需关注
    MONITORING = "MONITORING" # 监测中
    STABLE = "STABLE"         # 稳定
    ALERT = "ALERT"           # 警戒


class TrendType(str, enum.Enum):
    """趋势"""
    IMPROVED = "IMPROVED"    # 改善
    WORSENING = "WORSENING"  # 恶化
    STABLE = "STABLE"        # 稳定


class HealthCondition(Base):
    """健康状况表"""
    
    __tablename__ = "health_conditions"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # 所属用户
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    
    # 病症识别码（如 gout, hypertension, peanut）
    condition_code: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    
    # 病症信息
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str] = mapped_column(String(50), default="medical_services")
    
    # 类型与状态
    condition_type: Mapped[ConditionType] = mapped_column(SQLEnum(ConditionType), nullable=False)
    status: Mapped[ConditionStatus] = mapped_column(SQLEnum(ConditionStatus), default=ConditionStatus.MONITORING)
    trend: Mapped[TrendType] = mapped_column(SQLEnum(TrendType), default=TrendType.STABLE)
    
    # 数值（如血压、尿酸值等）
    value: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # AI 生成的描述
    dictum: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 箴言
    attribution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 归因分析
    
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
    
    # 关系
    user: Mapped["User"] = relationship("User", back_populates="conditions")


from app.models.user import User
