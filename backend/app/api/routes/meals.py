"""
饮食记录 API 路由
"""

from datetime import date, datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, CurrentUser
from app.models.meal import Meal, SyncStatus
from app.schemas.meal import (
    MealCreate,
    MealUpdate,
    MealResponse,
    MealSyncRequest,
    MealSyncResponse,
    DailyIntakeSummary
)
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/meals", tags=["饮食记录"])


@router.post("", response_model=MealResponse, status_code=status.HTTP_201_CREATED)
async def create_meal(
    data: MealCreate,
    current_user: CurrentUser,
    db: DbSession
):
    """创建饮食记录"""
    # 检查 client_id 是否已存在（防止重复提交）
    result = await db.execute(
        select(Meal).where(
            Meal.user_id == current_user.id,
            Meal.client_id == data.client_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return MealResponse.model_validate(existing)
    
    meal = Meal(
        user_id=current_user.id,
        sync_status=SyncStatus.SYNCED,
        **data.model_dump()
    )
    db.add(meal)
    await db.flush()
    await db.refresh(meal)
    
    return MealResponse.model_validate(meal)


@router.get("", response_model=PaginatedResponse[MealResponse])
async def list_meals(
    current_user: CurrentUser,
    db: DbSession,
    record_date: Optional[date] = Query(None, description="按日期筛选"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
):
    """
    获取饮食记录列表
    
    支持按日期范围筛选，分页返回
    """
    query = select(Meal).where(Meal.user_id == current_user.id)
    
    # 日期筛选
    if record_date:
        query = query.where(Meal.record_date == record_date)
    elif start_date and end_date:
        query = query.where(Meal.record_date.between(start_date, end_date))
    elif start_date:
        query = query.where(Meal.record_date >= start_date)
    elif end_date:
        query = query.where(Meal.record_date <= end_date)
    
    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页
    query = query.order_by(Meal.record_date.desc(), Meal.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    meals = result.scalars().all()
    
    return PaginatedResponse(
        items=[MealResponse.model_validate(m) for m in meals],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size
    )


@router.get("/today", response_model=List[MealResponse])
async def get_today_meals(current_user: CurrentUser, db: DbSession):
    """获取今日饮食记录"""
    today = date.today()
    result = await db.execute(
        select(Meal).where(
            Meal.user_id == current_user.id,
            Meal.record_date == today
        ).order_by(Meal.created_at.desc())
    )
    meals = result.scalars().all()
    return [MealResponse.model_validate(m) for m in meals]


@router.get("/summary", response_model=DailyIntakeSummary)
async def get_daily_summary(
    current_user: CurrentUser,
    db: DbSession,
    target_date: date = Query(default_factory=date.today, description="目标日期")
):
    """获取某日摄入汇总"""
    result = await db.execute(
        select(
            func.sum(Meal.calories).label("calories"),
            func.sum(Meal.sodium).label("sodium"),
            func.sum(Meal.purine).label("purine"),
            func.sum(Meal.protein).label("protein"),
            func.sum(Meal.carbs).label("carbs"),
            func.sum(Meal.fat).label("fat"),
            func.count(Meal.id).label("count")
        ).where(
            Meal.user_id == current_user.id,
            Meal.record_date == target_date
        )
    )
    row = result.one()
    
    return DailyIntakeSummary(
        date=target_date,
        total_calories=row.calories or 0,
        total_sodium=row.sodium or 0,
        total_purine=row.purine or 0,
        total_protein=row.protein or 0,
        total_carbs=row.carbs or 0,
        total_fat=row.fat or 0,
        meal_count=row.count or 0
    )


@router.get("/{meal_id}", response_model=MealResponse)
async def get_meal(meal_id: int, current_user: CurrentUser, db: DbSession):
    """获取单条饮食记录"""
    result = await db.execute(
        select(Meal).where(
            Meal.id == meal_id,
            Meal.user_id == current_user.id
        )
    )
    meal = result.scalar_one_or_none()
    
    if not meal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )
    
    return MealResponse.model_validate(meal)


@router.put("/{meal_id}", response_model=MealResponse)
async def update_meal(
    meal_id: int,
    data: MealUpdate,
    current_user: CurrentUser,
    db: DbSession
):
    """更新饮食记录"""
    result = await db.execute(
        select(Meal).where(
            Meal.id == meal_id,
            Meal.user_id == current_user.id
        )
    )
    meal = result.scalar_one_or_none()
    
    if not meal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(meal, field, value)
    
    await db.flush()
    await db.refresh(meal)
    
    return MealResponse.model_validate(meal)


@router.delete("/{meal_id}")
async def delete_meal(meal_id: int, current_user: CurrentUser, db: DbSession):
    """删除饮食记录"""
    result = await db.execute(
        select(Meal).where(
            Meal.id == meal_id,
            Meal.user_id == current_user.id
        )
    )
    meal = result.scalar_one_or_none()
    
    if not meal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )
    
    await db.delete(meal)
    await db.flush()
    
    return {"success": True, "message": "删除成功"}


@router.post("/sync", response_model=MealSyncResponse)
async def sync_meals(
    data: MealSyncRequest,
    current_user: CurrentUser,
    db: DbSession
):
    """
    离线数据同步
    
    客户端上传离线期间产生的记录，服务端返回需要同步到客户端的记录
    """
    synced_count = 0
    conflicts = []
    
    for meal_data in data.meals:
        # 检查是否已存在
        result = await db.execute(
            select(Meal).where(
                Meal.user_id == current_user.id,
                Meal.client_id == meal_data.client_id
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # 冲突处理：以服务器数据为准，记录冲突
            conflicts.append(meal_data.client_id)
        else:
            # 新建记录
            meal = Meal(
                user_id=current_user.id,
                sync_status=SyncStatus.SYNCED,
                **meal_data.model_dump()
            )
            db.add(meal)
            synced_count += 1
    
    await db.flush()
    
    # 获取服务端更新的记录（用于客户端同步）
    server_query = select(Meal).where(Meal.user_id == current_user.id)
    if data.last_sync_at:
        server_query = server_query.where(Meal.updated_at > data.last_sync_at)
    server_query = server_query.order_by(Meal.updated_at.desc()).limit(100)
    
    result = await db.execute(server_query)
    server_meals = result.scalars().all()
    
    return MealSyncResponse(
        synced_count=synced_count,
        conflicts=conflicts,
        server_meals=[MealResponse.model_validate(m) for m in server_meals]
    )
