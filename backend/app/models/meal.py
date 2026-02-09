"""
饮食记录数据模型
"""

from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Float, Integer, DateTime, Date, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class MealType(str, enum.Enum):
    """餐次类型"""
    BREAKFAST = "BREAKFAST"
    LUNCH = "LUNCH"
    DINNER = "DINNER"
    SNACK = "SNACK"


class FoodCategory(str, enum.Enum):
    """食物分类"""
    STAPLE = "STAPLE"  # 主食
    MEAT = "MEAT"      # 肉类
    VEG = "VEG"        # 蔬菜
    DRINK = "DRINK"    # 饮品
    SNACK = "SNACK"    # 零食


class SyncStatus(str, enum.Enum):
    """同步状态"""
    PENDING = "PENDING"    # 待同步
    SYNCED = "SYNCED"      # 已同步
    CONFLICT = "CONFLICT"  # 冲突


class Meal(Base):
    """饮食记录表"""
    
    __tablename__ = "meals"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # 所属用户
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    
    # 客户端生成的唯一ID（用于离线同步）
    client_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    
    # 食物信息
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    portion: Mapped[str] = mapped_column(String(50), nullable=False)  # 份量描述
    
    # 营养成分
    calories: Mapped[float] = mapped_column(Float, default=0)   # 热量 kcal
    sodium: Mapped[float] = mapped_column(Float, default=0)     # 钠 mg
    purine: Mapped[float] = mapped_column(Float, default=0)     # 嘌呤 mg
    protein: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 蛋白质 g
    carbs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)     # 碳水化合物 g
    fat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)       # 脂肪 g
    fiber: Mapped[Optional[float]] = mapped_column(Float, nullable=True)     # 膳食纤维 g
    
    # 分类
    meal_type: Mapped[MealType] = mapped_column(SQLEnum(MealType), nullable=False)
    category: Mapped[FoodCategory] = mapped_column(SQLEnum(FoodCategory), nullable=False)
    
    # 记录日期
    record_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    
    # 备注
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # AI 识别来源
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ai_recognized: Mapped[bool] = mapped_column(default=False)
    
    # 同步状态
    sync_status: Mapped[SyncStatus] = mapped_column(
        SQLEnum(SyncStatus),
        default=SyncStatus.SYNCED
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
    
    # 关系
    user: Mapped["User"] = relationship("User", back_populates="meals")


from app.models.user import User
