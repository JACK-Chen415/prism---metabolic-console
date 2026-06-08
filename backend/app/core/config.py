"""
应用配置管理
使用 pydantic-settings 从环境变量加载配置
"""

from functools import lru_cache
from typing import Any, Optional
from urllib.parse import urlparse

from pydantic import Field, model_validator
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
ALLOWED_BILLING_PROVIDERS = {"mock", "wechat_pay", "alipay"}
REAL_BILLING_PROVIDERS = {"wechat_pay", "alipay"}
IMPLEMENTED_BILLING_ADAPTERS = {"mock"}
ALLOWED_PACKAGED_FOOD_PROVIDERS = {"mock", "dev", "disabled"}
DEV_PACKAGED_FOOD_PROVIDERS = {"dev"}


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
    billing_currency: str = "CNY"
    billing_price_cny_minor_by_plan: dict[str, int] = Field(
        default_factory=lambda: {
            "FREE": 0,
            "PRO": 2900,
            "COACH": 9900,
        }
    )
    billing_mock_webhook_secret: Optional[str] = None
    wechat_pay_app_id: Optional[str] = None
    wechat_pay_mch_id: Optional[str] = None
    wechat_pay_api_v3_key: Optional[str] = None
    wechat_pay_mch_private_key: Optional[str] = None
    wechat_pay_mch_serial_no: Optional[str] = None
    wechat_pay_platform_cert: Optional[str] = None
    wechat_pay_notify_url: Optional[str] = None
    alipay_app_id: Optional[str] = None
    alipay_private_key: Optional[str] = None
    alipay_public_key: Optional[str] = None
    alipay_notify_url: Optional[str] = None
    # Gray-release entitlement enforcement is off by default so operators can
    # observe pressure before turning on hard gating at the call sites.
    entitlement_enforce_limits: bool = False

    # Packaged food lookup provider
    # mock/dev are for internal contract testing only and must be surfaced as such in UI/readiness.
    packaged_food_provider: str = "mock"

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

    @staticmethod
    def _normalize_billing_provider(value: str | None) -> str:
        return (value or "mock").strip().lower().replace("-", "_") or "mock"

    def _has_real_config_value(self, value: Optional[str]) -> bool:
        return bool((value or "").strip()) and not self._is_placeholder_config(value)

    def _billing_price_mapping_status(self) -> str:
        prices = {str(key).upper(): value for key, value in self.billing_price_cny_minor_by_plan.items()}
        if self.billing_currency.strip().upper() != "CNY":
            return "unsupported_currency"
        if prices.get("FREE", 0) != 0:
            return "invalid_free_price"
        if prices.get("PRO", 0) <= 0 or prices.get("COACH", 0) <= 0:
            return "missing_or_invalid_paid_plan_price"
        return "configured"

    def billing_readiness_snapshot(self, provider: Optional[str] = None) -> dict[str, Any]:
        """Return sanitized billing readiness details for the selected provider."""
        selected_provider = self._normalize_billing_provider(provider or self.billing_provider)
        warnings: list[str] = []
        blocking: list[str] = []
        mode = "production" if self.is_production else "non_production"
        price_mapping_status = self._billing_price_mapping_status()
        implementation_status = (
            "implemented_mock_internal_only"
            if selected_provider == "mock"
            else "blocked_placeholder_not_implemented"
        )

        configured = False
        webhook_configured = False
        configuration_gaps: list[str] = []
        webhook_gaps: list[str] = []

        if selected_provider not in ALLOWED_BILLING_PROVIDERS:
            blocking.append("billing_provider_unsupported")
            implementation_status = "unsupported"
        elif selected_provider == "mock":
            configured = True
            webhook_configured = self._has_real_config_value(self.billing_mock_webhook_secret)
            if self.is_production:
                blocking.append("mock_billing_provider")
            else:
                warnings.append("mock_billing_provider")
            if not webhook_configured:
                warnings.append("mock_billing_webhook_secret_missing")
                webhook_gaps.append("BILLING_MOCK_WEBHOOK_SECRET")
        elif selected_provider == "wechat_pay":
            required = {
                "WECHAT_PAY_APP_ID": self.wechat_pay_app_id,
                "WECHAT_PAY_MCH_ID": self.wechat_pay_mch_id,
                "WECHAT_PAY_API_V3_KEY": self.wechat_pay_api_v3_key,
                "WECHAT_PAY_MCH_PRIVATE_KEY": self.wechat_pay_mch_private_key,
                "WECHAT_PAY_MCH_SERIAL_NO": self.wechat_pay_mch_serial_no,
                "WECHAT_PAY_PLATFORM_CERT": self.wechat_pay_platform_cert,
            }
            configuration_gaps = [key for key, value in required.items() if not self._has_real_config_value(value)]
            webhook_gaps = [] if self._has_real_config_value(self.wechat_pay_notify_url) else ["WECHAT_PAY_NOTIFY_URL"]
            configured = not configuration_gaps
            webhook_configured = not webhook_gaps
            blocking.append("billing_adapter_not_implemented")
            if configuration_gaps:
                blocking.append("wechat_pay_credentials_missing")
            if webhook_gaps:
                blocking.append("wechat_pay_webhook_missing")
        elif selected_provider == "alipay":
            required = {
                "ALIPAY_APP_ID": self.alipay_app_id,
                "ALIPAY_PRIVATE_KEY": self.alipay_private_key,
                "ALIPAY_PUBLIC_KEY": self.alipay_public_key,
            }
            configuration_gaps = [key for key, value in required.items() if not self._has_real_config_value(value)]
            webhook_gaps = [] if self._has_real_config_value(self.alipay_notify_url) else ["ALIPAY_NOTIFY_URL"]
            configured = not configuration_gaps
            webhook_configured = not webhook_gaps
            blocking.append("billing_adapter_not_implemented")
            if configuration_gaps:
                blocking.append("alipay_credentials_missing")
            if webhook_gaps:
                blocking.append("alipay_webhook_missing")

        if price_mapping_status != "configured":
            blocking.append("billing_price_mapping_not_ready")

        return {
            "provider": selected_provider,
            "mode": mode,
            "configured": configured,
            "webhook_configured": webhook_configured,
            "adapter_implementation_status": implementation_status,
            "price_mapping_status": price_mapping_status,
            "ready": not blocking,
            "warnings": warnings,
            "blocking": blocking,
            "configuration_gaps": configuration_gaps,
            "webhook_gaps": webhook_gaps,
        }

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

        billing_readiness = self.billing_readiness_snapshot()
        warnings.extend(billing_readiness["warnings"])
        blocking.extend(billing_readiness["blocking"])

        packaged_food_provider = self.packaged_food_provider.strip().lower().replace("-", "_")
        if packaged_food_provider not in ALLOWED_PACKAGED_FOOD_PROVIDERS:
            target = blocking if self.is_production else warnings
            target.append("packaged_food_provider_unsupported")
        elif packaged_food_provider in DEV_PACKAGED_FOOD_PROVIDERS:
            target = blocking if self.is_production else warnings
            target.append("dev_packaged_food_provider")
        elif packaged_food_provider == "mock":
            warnings.append("mock_packaged_food_provider")
        elif packaged_food_provider == "disabled":
            warnings.append("packaged_food_provider_disabled")

        if not self.entitlement_enforce_limits:
            target = blocking if self.is_production else warnings
            target.append("entitlement_limits_soft_only")

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
            "billing": billing_readiness,
            "packaged_food_provider": self.packaged_food_provider,
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

        billing_provider = self._normalize_billing_provider(self.billing_provider)
        if billing_provider not in ALLOWED_BILLING_PROVIDERS:
            raise ValueError("BILLING_PROVIDER 只能为 mock、wechat_pay 或 alipay")
        self.billing_provider = billing_provider

        packaged_food_provider = self.packaged_food_provider.strip().lower().replace("-", "_")
        if packaged_food_provider not in ALLOWED_PACKAGED_FOOD_PROVIDERS:
            raise ValueError("PACKAGED_FOOD_PROVIDER 只能为 mock、dev 或 disabled；真实条码 provider 接入前必须先完成签名/配额/审计")
        self.packaged_food_provider = packaged_food_provider
        self.billing_currency = self.billing_currency.strip().upper()
        if len(self.billing_currency) != 3:
            raise ValueError("BILLING_CURRENCY 必须使用 3 位 ISO 4217 货币代码")
        self.billing_price_cny_minor_by_plan = {
            str(key).upper(): int(value)
            for key, value in self.billing_price_cny_minor_by_plan.items()
        }
        if any(value < 0 for value in self.billing_price_cny_minor_by_plan.values()):
            raise ValueError("BILLING_PRICE_CNY_MINOR_BY_PLAN 不能包含负数价格")

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
            if not self.entitlement_enforce_limits:
                raise ValueError("生产环境必须开启 ENTITLEMENT_ENFORCE_LIMITS，不能以软限制模式运行")
            if self.billing_provider == "mock":
                raise ValueError("生产环境不能使用 mock billing provider；当前构建未接入真实支付 provider")
            if self.packaged_food_provider in DEV_PACKAGED_FOOD_PROVIDERS:
                raise ValueError("生产环境不能使用 dev packaged food provider")

        return self


@lru_cache
def get_settings() -> Settings:
    """获取缓存的配置实例"""
    return Settings()


settings = get_settings()
