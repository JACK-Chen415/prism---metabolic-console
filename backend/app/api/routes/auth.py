"""
用户认证 API 路由
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, CurrentUser
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token
)
from app.core.config import settings
from app.models.user import User
from app.schemas.user import (
    UserRegister,
    UserLogin,
    UserProfileUpdate,
    PasswordChange,
    RefreshTokenRequest,
    UserResponse,
    TokenResponse,
    LoginResponse,
    DailyTargets
)

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: DbSession):
    """
    用户注册
    
    - **phone**: 11位手机号
    - **password**: 密码（6-50位）
    - **nickname**: 可选昵称
    """
    # 检查手机号是否已注册
    result = await db.execute(select(User).where(User.phone == data.phone))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该手机号已注册"
        )
    
    # 创建用户
    user = User(
        phone=data.phone,
        password_hash=get_password_hash(data.password),
        nickname=data.nickname or f"用户{data.phone[-4:]}"
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    
    # 生成 Token
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    return LoginResponse(
        user=UserResponse.model_validate(user),
        tokens=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60
        )
    )


@router.post("/login", response_model=LoginResponse)
async def login(data: UserLogin, db: DbSession):
    """
    用户登录
    
    - **phone**: 手机号
    - **password**: 密码
    """
    # 查询用户
    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="手机号或密码错误"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )
    
    # 更新最后登录时间
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    
    # 生成 Token
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    return LoginResponse(
        user=UserResponse.model_validate(user),
        tokens=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60
        )
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshTokenRequest, db: DbSession):
    """
    刷新 Access Token
    
    使用 Refresh Token 获取新的 Access Token
    """
    payload = decode_token(data.refresh_token)
    
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的Refresh Token"
        )
    
    user_id = payload.get("sub")
    
    # 验证用户是否存在且有效
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用"
        )
    
    # 生成新的 Token
    access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUser):
    """获取当前用户信息"""
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
async def update_profile(
    data: UserProfileUpdate,
    current_user: CurrentUser,
    db: DbSession
):
    """更新用户资料"""
    update_data = data.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    await db.flush()
    await db.refresh(current_user)
    
    return UserResponse.model_validate(current_user)


@router.post("/change-password")
async def change_password(
    data: PasswordChange,
    current_user: CurrentUser,
    db: DbSession
):
    """修改密码"""
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误"
        )
    
    current_user.password_hash = get_password_hash(data.new_password)
    await db.flush()
    
    return {"success": True, "message": "密码修改成功"}


@router.get("/daily-targets", response_model=DailyTargets)
async def get_daily_targets(current_user: CurrentUser, db: DbSession):
    """
    获取每日摄入目标
    
    基于用户身体参数动态计算
    """
    from sqlalchemy import select
    from app.models.health_condition import HealthCondition, ConditionStatus
    
    # 默认值（当用户未设置身体参数时）
    if not all([current_user.gender, current_user.age, current_user.height, current_user.weight]):
        return DailyTargets(calories=2000, sodium=2300, purine=600)
    
    # 计算 BMR (Mifflin-St Jeor 公式)
    s = 5 if current_user.gender.value == "MALE" else -161
    bmr = (10 * current_user.weight) + (6.25 * current_user.height) - (5 * current_user.age) + s
    calories = int(bmr * 1.375)  # 轻度活动系数
    
    # 查询用户健康状况
    result = await db.execute(
        select(HealthCondition).where(
            HealthCondition.user_id == current_user.id,
            HealthCondition.status.in_([ConditionStatus.ACTIVE, ConditionStatus.MONITORING])
        )
    )
    conditions = result.scalars().all()
    condition_codes = [c.condition_code for c in conditions]
    
    # 根据健康状况调整目标
    sodium = 1500 if "hypertension" in condition_codes else 2300
    purine = 300 if "gout" in condition_codes else 600
    
    return DailyTargets(calories=calories, sodium=sodium, purine=purine)
