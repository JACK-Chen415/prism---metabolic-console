"""
健康档案 API 路由
"""

from typing import List

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, CurrentUser
from app.models.health_condition import (
    HealthCondition,
    ConditionType,
    ConditionStatus,
    TrendType
)
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ========== Schemas ==========

class ConditionCreate(BaseModel):
    """创建健康状况请求"""
    condition_code: str = Field(..., max_length=50)
    title: str = Field(..., max_length=100)
    icon: str = Field("medical_services", max_length=50)
    condition_type: ConditionType
    status: ConditionStatus = ConditionStatus.MONITORING
    trend: TrendType = TrendType.STABLE
    value: Optional[str] = Field(None, max_length=50)
    unit: Optional[str] = Field(None, max_length=20)
    dictum: Optional[str] = None
    attribution: Optional[str] = None


class ConditionUpdate(BaseModel):
    """更新健康状况请求"""
    status: Optional[ConditionStatus] = None
    trend: Optional[TrendType] = None
    value: Optional[str] = Field(None, max_length=50)
    unit: Optional[str] = Field(None, max_length=20)
    dictum: Optional[str] = None
    attribution: Optional[str] = None


class ConditionResponse(BaseModel):
    """健康状况响应"""
    id: int
    condition_code: str
    title: str
    icon: str
    condition_type: ConditionType
    status: ConditionStatus
    trend: TrendType
    value: Optional[str] = None
    unit: Optional[str] = None
    dictum: Optional[str] = None
    attribution: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


router = APIRouter(prefix="/conditions", tags=["健康档案"])


@router.post("", response_model=ConditionResponse, status_code=status.HTTP_201_CREATED)
async def create_condition(
    data: ConditionCreate,
    current_user: CurrentUser,
    db: DbSession
):
    """添加健康状况记录"""
    # 检查是否已存在相同的 condition_code
    result = await db.execute(
        select(HealthCondition).where(
            HealthCondition.user_id == current_user.id,
            HealthCondition.condition_code == data.condition_code
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该健康状况已存在"
        )
    
    condition = HealthCondition(
        user_id=current_user.id,
        **data.model_dump()
    )
    db.add(condition)
    await db.flush()
    await db.refresh(condition)
    
    return ConditionResponse.model_validate(condition)


@router.get("", response_model=List[ConditionResponse])
async def list_conditions(current_user: CurrentUser, db: DbSession):
    """获取健康状况列表"""
    result = await db.execute(
        select(HealthCondition)
        .where(HealthCondition.user_id == current_user.id)
        .order_by(HealthCondition.created_at.desc())
    )
    conditions = result.scalars().all()
    return [ConditionResponse.model_validate(c) for c in conditions]


@router.get("/chronic", response_model=List[ConditionResponse])
async def list_chronic_conditions(current_user: CurrentUser, db: DbSession):
    """获取慢性病列表"""
    result = await db.execute(
        select(HealthCondition).where(
            HealthCondition.user_id == current_user.id,
            HealthCondition.condition_type == ConditionType.CHRONIC
        )
    )
    conditions = result.scalars().all()
    return [ConditionResponse.model_validate(c) for c in conditions]


@router.get("/allergies", response_model=List[ConditionResponse])
async def list_allergies(current_user: CurrentUser, db: DbSession):
    """获取过敏源列表"""
    result = await db.execute(
        select(HealthCondition).where(
            HealthCondition.user_id == current_user.id,
            HealthCondition.condition_type == ConditionType.ALLERGY
        )
    )
    conditions = result.scalars().all()
    return [ConditionResponse.model_validate(c) for c in conditions]


@router.get("/{condition_id}", response_model=ConditionResponse)
async def get_condition(condition_id: int, current_user: CurrentUser, db: DbSession):
    """获取单个健康状况"""
    result = await db.execute(
        select(HealthCondition).where(
            HealthCondition.id == condition_id,
            HealthCondition.user_id == current_user.id
        )
    )
    condition = result.scalar_one_or_none()
    
    if not condition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )
    
    return ConditionResponse.model_validate(condition)


@router.put("/{condition_id}", response_model=ConditionResponse)
async def update_condition(
    condition_id: int,
    data: ConditionUpdate,
    current_user: CurrentUser,
    db: DbSession
):
    """更新健康状况"""
    result = await db.execute(
        select(HealthCondition).where(
            HealthCondition.id == condition_id,
            HealthCondition.user_id == current_user.id
        )
    )
    condition = result.scalar_one_or_none()
    
    if not condition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(condition, field, value)
    
    await db.flush()
    await db.refresh(condition)
    
    return ConditionResponse.model_validate(condition)


@router.delete("/{condition_id}")
async def delete_condition(condition_id: int, current_user: CurrentUser, db: DbSession):
    """删除健康状况"""
    result = await db.execute(
        select(HealthCondition).where(
            HealthCondition.id == condition_id,
            HealthCondition.user_id == current_user.id
        )
    )
    condition = result.scalar_one_or_none()
    
    if not condition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )
    
    await db.delete(condition)
    await db.flush()
    
    return {"success": True, "message": "删除成功"}
