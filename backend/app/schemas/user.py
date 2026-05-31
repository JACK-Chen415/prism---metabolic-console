"""
用户相关 Pydantic Schema
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import re

from app.models.user import Gender, SubscriptionPlan, SubscriptionStatus, UserRole


CONSENT_VERSION = "2026-05-30"


# ==================== 请求 Schema ====================

class UserRegister(BaseModel):
    """用户注册请求"""
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")
    password: str = Field(..., min_length=6, max_length=50, description="密码")
    nickname: Optional[str] = Field(None, max_length=50, description="昵称")
    terms_accepted: bool = Field(False, description="已同意用户协议")
    privacy_accepted: bool = Field(False, description="已同意隐私政策")
    ai_use_accepted: bool = Field(False, description="已阅读并同意 AI 使用说明")
    health_disclaimer_accepted: bool = Field(False, description="已阅读并同意健康免责声明")
    consent_version: str = Field(CONSENT_VERSION, min_length=1, max_length=40, description="协议版本")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式不正确")
        return v

    @model_validator(mode="after")
    def validate_required_consents(self) -> "UserRegister":
        if not all([
            self.terms_accepted,
            self.privacy_accepted,
            self.ai_use_accepted,
            self.health_disclaimer_accepted,
        ]):
            raise ValueError("必须同意用户协议、隐私政策、AI 使用说明和健康免责声明")
        self.consent_version = self.consent_version.strip()
        if not self.consent_version:
            raise ValueError("协议版本不能为空")
        return self


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


class SendCodeRequest(BaseModel):
    """发送验证码请求"""
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")
    purpose: str = Field(..., description="用途: login/reset_password")

    @field_validator("phone")
    @classmethod
    def validate_code_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式不正确")
        return v


class CodeLoginRequest(BaseModel):
    """验证码登录请求"""
    phone: str = Field(..., min_length=11, max_length=11, description="手机号")
    code: str = Field(..., min_length=4, max_length=6, description="验证码")

    @field_validator("phone")
    @classmethod
    def validate_login_code_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式不正确")
        return v


class ResetPasswordRequest(BaseModel):
    """重置密码请求"""
    phone: str = Field(..., min_length=11, max_length=11)
    code: str = Field(..., min_length=4, max_length=6)
    new_password: str = Field(..., min_length=6, max_length=50)

    @field_validator("phone")
    @classmethod
    def validate_reset_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("手机号格式不正确")
        return v


class RevokeSessionRequest(BaseModel):
    """撤销设备会话请求。"""
    confirm: str = Field("REVOKE_SESSION", pattern="^REVOKE_SESSION$")


# ==================== 响应 Schema ====================

class UserResponse(BaseModel):
    """用户信息响应"""
    model_config = ConfigDict(from_attributes=True)

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
    role: UserRole = UserRole.USER
    subscription_plan: SubscriptionPlan = SubscriptionPlan.FREE
    subscription_status: SubscriptionStatus = SubscriptionStatus.INACTIVE
    subscription_updated_at: Optional[datetime] = None
    created_at: datetime


class CalorieRange(BaseModel):
    """估算热量范围。"""
    min: int = Field(description="下限(kcal/day)")
    max: int = Field(description="上限(kcal/day)")


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


class DeviceSessionResponse(BaseModel):
    """设备会话响应，不暴露 token 或原始 UA/IP。"""
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    device_label: Optional[str] = None
    is_current: bool
    is_revoked: bool
    expires_at: datetime
    created_at: datetime
    last_seen_at: datetime
    revoked_at: Optional[datetime] = None
    revoke_reason: Optional[str] = None



class DailyTargets(BaseModel):
    """每日目标值（基于用户身体参数计算）。"""
    calories: int = Field(description="推荐摄入热量目标(kcal)，保留给旧前端兼容")
    sodium: int = Field(description="钠摄入上限(mg)")
    purine: int = Field(description="嘌呤摄入上限(mg)")
    bmi: Optional[float] = Field(None, description="BMI")
    bmi_category: Optional[str] = Field(None, description="BMI 分层")
    bmr: Optional[int] = Field(None, description="基础代谢估算(kcal/day)")
    bmr_range: Optional[CalorieRange] = Field(None, description="基础代谢估算范围(kcal/day)")
    activity_factor: float = Field(1.375, description="活动系数")
    estimated_tdee: Optional[int] = Field(None, description="每日总消耗估算(kcal/day)")
    recommended_calorie_target: int = Field(0, description="推荐每日摄入热量目标(kcal/day)")
    target_strategy: str = Field("insufficient_data", description="目标策略")
    target_explanation: str = Field("请先完善身高、体重、年龄、性别，以获得更准确估算。", description="目标解释")
    is_estimated: bool = Field(True, description="是否为估算值")
    has_complete_profile: bool = Field(False, description="是否具备完整目标计算资料")
