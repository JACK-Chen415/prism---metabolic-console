"""
用户相关 Pydantic Schema
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re

from app.models.user import Gender


# ==================== 请求 Schema ====================

class UserRegister(BaseModel):
    """用户注册请求"""
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")
    password: str = Field(..., min_length=6, max_length=50, description="密码")
    nickname: Optional[str] = Field(None, max_length=50, description="昵称")
    
    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式不正确")
        return v


class UserLogin(BaseModel):
    """用户登录请求"""
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")
    password: str = Field(..., description="密码")


class UserProfileUpdate(BaseModel):
    """用户资料更新请求"""
    nickname: Optional[str] = Field(None, max_length=50)
    avatar_url: Optional[str] = Field(None, max_length=500)
    gender: Optional[Gender] = None
    age: Optional[int] = Field(None, ge=1, le=150)
    height: Optional[float] = Field(None, ge=50, le=300, description="身高(cm)")
    weight: Optional[float] = Field(None, ge=10, le=500, description="体重(kg)")


class PasswordChange(BaseModel):
    """修改密码请求"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=50, description="新密码")


class RefreshTokenRequest(BaseModel):
    """刷新Token请求"""
    refresh_token: str


# ==================== 响应 Schema ====================

class UserResponse(BaseModel):
    """用户信息响应"""
    id: int
    phone: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    gender: Optional[Gender] = None
    age: Optional[int] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    is_active: bool
    is_verified: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """Token响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access Token 过期时间(秒)")


class LoginResponse(BaseModel):
    """登录响应"""
    user: UserResponse
    tokens: TokenResponse


class DailyTargets(BaseModel):
    """每日目标值（基于用户身体参数计算）"""
    calories: int = Field(description="热量目标(kcal)")
    sodium: int = Field(description="钠摄入上限(mg)")
    purine: int = Field(description="嘌呤摄入上限(mg)")
