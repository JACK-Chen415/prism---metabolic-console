"""
应用配置管理
使用 pydantic-settings 从环境变量加载配置
"""

from functools import lru_cache
from typing import Any, Optional
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PLACEHOLDER_CONFIG_VALUES = {
    "",
    "placeholder",
    "ci-placeholder",
    "your_ark_api_key",
    "your-volcengine-api-key",
    "your-multimodal-endpoint-id",
    "ep-xxxxxxxxxx",
}

# Gray-release upload caps. Production must fail closed if operators accidentally
# raise these beyond the reviewed image-safety budget.
PRODUCTION_MAX_UPLOAD_SIZE_MB = 10
PRODUCTION_MAX_UPLOAD_IMAGE_PIXELS = 20_000_000

# Gray-release token caps. Long-lived bearer tokens are easy to forget and hard
# to revoke, so production must stay within a reviewed window.
ALLOWED_JWT_ALGORITHMS = {"HS256", "HS384", "HS512"}
PRODUCTION_MAX_JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60
PRODUCTION_MAX_JWT_REFRESH_TOKEN_EXPIRE_DAYS = 30

# Only implemented OTP providers are allowed. A typo in production should fail
# closed instead of silently falling back to the audit-only mock provider.
ALLOWED_OTP_PROVIDERS = {"dev", "development", "console", "audit_only"}
DEV_OTP_PROVIDERS = {"dev", "development", "console"}


class Settings(BaseSettings):
    """应用全局配置"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # 应用基本信息
    app_name: str = "Prism Metabolic Console"
    app_version: str = "1.0.0"
    debug: bool = False
    app_env: str = "development"
    
    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000
    
    # 数据库配置
    database_url: str = "postgresql+asyncpg://prism:prism123@localhost:5433/prism_metabolic"
    
    # JWT 认证配置
    jwt_secret_key: str = "your-super-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    otp_provider: str = "dev"
    
    # 豆包 AI 配置 (Volcengine ARK)
    ark_api_key: Optional[str] = None  # ARK API Key
    doubao_model: Optional[str] = None  # 主多模态模型 endpoint/model
    doubao_endpoint_id: Optional[str] = None  # Deprecated: use DOUBAO_MODEL
    doubao_timeout_seconds: float = 60.0
    doubao_connect_timeout_seconds: float = 10.0
    doubao_max_retries: int = 1
    doubao_chat_max_tokens: int = 420
    doubao_vision_max_tokens: int = 2000
    doubao_vision_fast_max_tokens: int = 900

    # AI 成本估算（可选，只用于灰度运营 telemetry；不代表真实账单）
    ai_cost_usd_per_1k_tokens: Optional[float] = None
    ai_cost_estimate_chars_per_token: float = 4.0

    # AI 聊天上下文保护
    chat_history_limit: int = 6
    chat_history_message_max_chars: int = 600
    chat_prompt_max_chars: int = 3500

    # Admin console
    admin_phone_hashes: list[str] = []

    # Billing provider
    billing_provider: str = "mock"
    # Gray-release entitlement enforcement is off by default so operators can
    # observe pressure before turning on hard gating at the call sites.
    entitlement_enforce_limits: bool = False
    
    # 文件存储配置
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 10
    max_upload_image_pixels: int = 20_000_000
    
    # CORS 配置
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://localhost:3004",
        "http://localhost:3005",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:3003",
        "http://127.0.0.1:3004",
        "http://127.0.0.1:3005",
        "https://prism-metabolic-console.vercel.app"
    ]

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"prod", "production"}

    @property
    def is_development(self) -> bool:
        return self.app_env.strip().lower() in {"dev", "development"}

    @property
    def main_doubao_model(self) -> str:
        """Return the single multimodal Doubao model used by all AI calls."""
        model = self.doubao_model or self.doubao_endpoint_id
        if not model:
            raise RuntimeError("豆包主模型未配置，请设置 DOUBAO_MODEL 环境变量")
        return model

    @staticmethod
    def _is_placeholder_config(value: Optional[str]) -> bool:
        normalized = (value or "").strip().lower()
        return normalized in PLACEHOLDER_CONFIG_VALUES or normalized.startswith("your-")

    def readiness_snapshot(self) -> dict[str, Any]:
        """Return a sanitized config snapshot for health/readiness surfaces."""
        warnings: list[str] = []
        blocking: list[str] = []
        ai_key_placeholder = self._is_placeholder_config(self.ark_api_key)
        ai_model_placeholder = self._is_placeholder_config(self.doubao_model or self.doubao_endpoint_id)

        if not self.is_production:
            warnings.append("non_production_environment")
        if ai_key_placeholder:
            target = blocking if self.is_production else warnings
            target.append("ai_key_placeholder_or_missing")
        if ai_model_placeholder:
            target = blocking if self.is_production else warnings
            target.append("ai_model_placeholder_or_missing")
        otp_provider = self.otp_provider.strip().lower().replace("-", "_")
        if otp_provider in DEV_OTP_PROVIDERS:
            target = blocking if self.is_production else warnings
            target.append("dev_otp_provider")
        elif otp_provider == "audit_only":
            warnings.append("otp_provider_audit_only")
        elif otp_provider not in ALLOWED_OTP_PROVIDERS:
            target = blocking if self.is_production else warnings
            target.append("otp_provider_unsupported")
        if self.jwt_algorithm.strip().upper() not in ALLOWED_JWT_ALGORITHMS:
            target = blocking if self.is_production else warnings
            target.append("jwt_algorithm_unsupported")
        if self.jwt_access_token_expire_minutes > PRODUCTION_MAX_JWT_ACCESS_TOKEN_EXPIRE_MINUTES:
            target = blocking if self.is_production else warnings
            target.append("jwt_access_token_exceeds_reviewed_cap")
        if self.jwt_refresh_token_expire_days > PRODUCTION_MAX_JWT_REFRESH_TOKEN_EXPIRE_DAYS:
            target = blocking if self.is_production else warnings
            target.append("jwt_refresh_token_exceeds_reviewed_cap")

        if (
            self.max_upload_size_mb > PRODUCTION_MAX_UPLOAD_SIZE_MB
            or self.max_upload_image_pixels > PRODUCTION_MAX_UPLOAD_IMAGE_PIXELS
        ):
            target = blocking if self.is_production else warnings
            target.append("upload_limits_exceed_reviewed_cap")
        if self.is_production and not self.admin_phone_hashes:
            warnings.append("admin_bootstrap_allowlist_missing")

        if self.billing_provider.strip().lower().replace("-", "_") == "mock":
            warnings.append("mock_billing_provider")
        if not self.entitlement_enforce_limits:
            warnings.append("entitlement_limits_soft_only")

        return {
            "status": "blocked" if blocking else "ok",
            "app_env": self.app_env,
            "is_production": self.is_production,
            "warnings": warnings,
            "blocking": blocking,
            "otp_provider": self.otp_provider.strip().lower().replace("-", "_"),
            "jwt_algorithm": self.jwt_algorithm.strip().upper(),
            "jwt_access_token_expire_minutes": self.jwt_access_token_expire_minutes,
            "jwt_refresh_token_expire_days": self.jwt_refresh_token_expire_days,
            "billing_provider": self.billing_provider,
            "entitlement_enforce_limits": self.entitlement_enforce_limits,
            "ai_key_configured": bool((self.ark_api_key or "").strip()) and not ai_key_placeholder,
            "ai_model_configured": bool((self.doubao_model or self.doubao_endpoint_id or "").strip()) and not ai_model_placeholder,
            "ai_cost_estimate_configured": self.ai_cost_usd_per_1k_tokens is not None,
            "cors_origin_count": len(self.cors_origins),
            "admin_bootstrap_allowlist_count": len(self.admin_phone_hashes),
            "max_upload_size_mb": self.max_upload_size_mb,
            "max_upload_image_pixels": self.max_upload_image_pixels,
        }

    @model_validator(mode="after")
    def validate_production_guards(self) -> "Settings":
        if self.max_upload_size_mb < 1:
            raise ValueError("MAX_UPLOAD_SIZE_MB 必须大于 0")
        if self.max_upload_image_pixels < 1:
            raise ValueError("MAX_UPLOAD_IMAGE_PIXELS 必须大于 0")
        if self.ai_cost_usd_per_1k_tokens is not None and self.ai_cost_usd_per_1k_tokens < 0:
            raise ValueError("AI_COST_USD_PER_1K_TOKENS 不能为负数")
        if self.ai_cost_estimate_chars_per_token <= 0:
            raise ValueError("AI_COST_ESTIMATE_CHARS_PER_TOKEN 必须大于 0")
        jwt_algorithm = self.jwt_algorithm.strip().upper()
        if jwt_algorithm not in ALLOWED_JWT_ALGORITHMS:
            raise ValueError("JWT_ALGORITHM 只能使用对称 HMAC 算法")
        self.jwt_algorithm = jwt_algorithm
        if self.jwt_access_token_expire_minutes < 1:
            raise ValueError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES 必须大于 0")
        if self.jwt_refresh_token_expire_days < 1:
            raise ValueError("JWT_REFRESH_TOKEN_EXPIRE_DAYS 必须大于 0")
        otp_provider = self.otp_provider.strip().lower().replace("-", "_")
        if otp_provider not in ALLOWED_OTP_PROVIDERS:
            raise ValueError("当前构建只允许 OTP_PROVIDER=dev、console 或 audit_only；真实短信 provider 接入前必须先完成实现和审计")
        self.otp_provider = otp_provider

        billing_provider = self.billing_provider.strip().lower().replace("-", "_")
        if billing_provider not in {"mock"}:
            raise ValueError("当前构建只允许 BILLING_PROVIDER=mock；真实支付 provider 接入前必须先完成实现和审计")
        self.billing_provider = billing_provider

        if self.is_production:
            if self.max_upload_size_mb > PRODUCTION_MAX_UPLOAD_SIZE_MB:
                raise ValueError("MAX_UPLOAD_SIZE_MB 超过灰度生产审核上限")
            if self.max_upload_image_pixels > PRODUCTION_MAX_UPLOAD_IMAGE_PIXELS:
                raise ValueError("MAX_UPLOAD_IMAGE_PIXELS 超过灰度生产审核上限")
            if self.jwt_access_token_expire_minutes > PRODUCTION_MAX_JWT_ACCESS_TOKEN_EXPIRE_MINUTES:
                raise ValueError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES 超过灰度生产审核上限")
            if self.jwt_refresh_token_expire_days > PRODUCTION_MAX_JWT_REFRESH_TOKEN_EXPIRE_DAYS:
                raise ValueError("JWT_REFRESH_TOKEN_EXPIRE_DAYS 超过灰度生产审核上限")

            secret = self.jwt_secret_key.strip()
            if not secret or self._is_placeholder_config(secret) or len(secret) < 32:
                raise ValueError("生产环境必须配置足够强度的 JWT_SECRET_KEY")

            if self.debug:
                raise ValueError("生产环境不能开启 debug")

            provider = self.otp_provider.strip().lower().replace("-", "_")
            if provider in DEV_OTP_PROVIDERS:
                raise ValueError("生产环境不能使用开发验证码 provider")

            if any(origin == "*" for origin in self.cors_origins):
                raise ValueError("生产环境不能允许通配 CORS")

            invalid_origins = [
                origin for origin in self.cors_origins
                if origin.startswith("http://localhost")
                or origin.startswith("http://127.0.0.1")
                or not origin.startswith("https://")
            ]
            if invalid_origins:
                raise ValueError("生产环境 CORS 只能包含可信 https 来源")

            parsed = urlparse(self.database_url.replace("+asyncpg", "", 1))
            if parsed.scheme not in {"postgresql", "postgres"}:
                raise ValueError("生产环境数据库必须使用 PostgreSQL")
            if not parsed.hostname or parsed.hostname in {"localhost", "127.0.0.1"}:
                raise ValueError("生产环境数据库不能指向本地地址")

            if self._is_placeholder_config(self.ark_api_key):
                raise ValueError("生产环境必须配置真实 ARK_API_KEY，不能使用空值或占位值")
            if self._is_placeholder_config(self.doubao_model or self.doubao_endpoint_id):
                raise ValueError("生产环境必须配置真实 DOUBAO_MODEL，不能使用空值或占位值")

        return self


@lru_cache
def get_settings() -> Settings:
    """获取缓存的配置实例"""
    return Settings()


settings = get_settings()
