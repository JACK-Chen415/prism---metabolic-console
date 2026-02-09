"""
Prism Metabolic Console - FastAPI 主应用
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.core.config import settings
from app.core.database import init_db, close_db
from app.api.routes import auth, meals, chat, conditions, messages


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    await init_db()
    
    # 确保上传目录存在
    os.makedirs(settings.upload_dir, exist_ok=True)
    
    yield
    
    # 关闭时
    await close_db()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
# 棱镜代谢控制台 API

一款智能健康饮食管理应用的后端服务。

## 功能模块

- **用户认证** - 注册、登录、Token 管理
- **饮食记录** - 记录每日饮食，支持离线同步
- **AI 对话** - 基于豆包大模型的健康顾问
- **食物识别** - AI 视觉识别食物及营养成分
- **健康档案** - 管理慢性病、过敏史
- **消息通知** - 健康预警、建议推送

## 免责声明

本应用仅提供健康建议，不构成医疗诊断。如有健康问题请咨询专业医生。
    """,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router, prefix="/api")
app.include_router(meals.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(conditions.router, prefix="/api")
app.include_router(messages.router, prefix="/api")


@app.get("/api/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version
    }


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": f"欢迎使用 {settings.app_name}",
        "docs": "/api/docs"
    }
