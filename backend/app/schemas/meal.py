"""
饮食记录相关 Pydantic Schema
"""

from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field

from app.models.meal import MealType, FoodCategory, SyncStatus


# ==================== 请求 Schema ====================

class MealCreate(BaseModel):
    """创建饮食记录请求"""
    client_id: str = Field(..., max_length=36, description="客户端生成的唯一ID")
    name: str = Field(..., max_length=100, description="食物名称")
    portion: str = Field(..., max_length=50, description="份量描述")
    calories: float = Field(0, ge=0, description="热量(kcal)")
    sodium: float = Field(0, ge=0, description="钠(mg)")
    purine: float = Field(0, ge=0, description="嘌呤(mg)")
    protein: Optional[float] = Field(None, ge=0, description="蛋白质(g)")
    carbs: Optional[float] = Field(None, ge=0, description="碳水化合物(g)")
    fat: Optional[float] = Field(None, ge=0, description="脂肪(g)")
    fiber: Optional[float] = Field(None, ge=0, description="膳食纤维(g)")
    meal_type: MealType = Field(..., description="餐次类型")
    category: FoodCategory = Field(..., description="食物分类")
    record_date: date = Field(..., description="记录日期")
    note: Optional[str] = Field(None, max_length=500, description="备注")
    image_url: Optional[str] = Field(None, max_length=500, description="食物图片URL")
    ai_recognized: bool = Field(False, description="是否AI识别")


class MealUpdate(BaseModel):
    """更新饮食记录请求"""
    name: Optional[str] = Field(None, max_length=100)
    portion: Optional[str] = Field(None, max_length=50)
    calories: Optional[float] = Field(None, ge=0)
    sodium: Optional[float] = Field(None, ge=0)
    purine: Optional[float] = Field(None, ge=0)
    protein: Optional[float] = Field(None, ge=0)
    carbs: Optional[float] = Field(None, ge=0)
    fat: Optional[float] = Field(None, ge=0)
    fiber: Optional[float] = Field(None, ge=0)
    meal_type: Optional[MealType] = None
    category: Optional[FoodCategory] = None
    note: Optional[str] = Field(None, max_length=500)


class MealSyncRequest(BaseModel):
    """离线数据同步请求"""
    meals: List[MealCreate]
    last_sync_at: Optional[datetime] = Field(None, description="上次同步时间")


# ==================== 响应 Schema ====================

class MealResponse(BaseModel):
    """饮食记录响应"""
    id: int
    client_id: str
    name: str
    portion: str
    calories: float
    sodium: float
    purine: float
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    fiber: Optional[float] = None
    meal_type: MealType
    category: FoodCategory
    record_date: date
    note: Optional[str] = None
    image_url: Optional[str] = None
    ai_recognized: bool
    sync_status: SyncStatus
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class DailyIntakeSummary(BaseModel):
    """每日摄入汇总"""
    date: date
    total_calories: float
    total_sodium: float
    total_purine: float
    total_protein: float
    total_carbs: float
    total_fat: float
    meal_count: int


class MealSyncResponse(BaseModel):
    """离线数据同步响应"""
    synced_count: int
    conflicts: List[str] = Field(default_factory=list, description="冲突的client_id列表")
    server_meals: List[MealResponse] = Field(description="服务器端新增/更新的记录")
