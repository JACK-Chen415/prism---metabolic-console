"""
应用配置管理
使用 pydantic-settings 从环境变量加载配置
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    
    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000
    
    # 数据库配置
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/prism_db"
    
    # JWT 认证配置
    jwt_secret_key: str = "your-super-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    
    # 豆包 AI 配置 (Volcengine ARK)
    ark_api_key: Optional[str] = None  # ARK API Key
    doubao_endpoint_id: Optional[str] = None  # 豆包对话模型 endpoint
    doubao_vision_endpoint_id: Optional[str] = None  # 豆包视觉模型 endpoint
    
    # 文件存储配置
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 10
    
    # CORS 配置
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://localhost:3004",
        "http://localhost:3005"
    ]


@lru_cache
def get_settings() -> Settings:
    """获取缓存的配置实例"""
    return Settings()


settings = get_settings()
