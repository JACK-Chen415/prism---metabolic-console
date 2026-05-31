"""
Prism Metabolic Console - FastAPI 主应用
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import json
import logging
import time
import uuid

from app.core.config import settings
from app.core.database import init_db, close_db, engine
from app.core.security import hash_sensitive_value
from app.api.routes import auth, meals, chat, conditions, messages, knowledge, intake, insights, reports, billing, admin, health_metrics
from app.api.routes import account


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

logger = logging.getLogger("uvicorn.access")

SECURITY_RESPONSE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cache-Control": "no-store",
}


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        payload = {
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "client_ip_hash": hash_sensitive_value(request.client.host if request.client else None),
        }
        logger.error(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        raise

    response.headers["X-Request-ID"] = request_id
    for header, value in SECURITY_RESPONSE_HEADERS.items():
        response.headers.setdefault(header, value)
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=15552000; includeSubDomains",
        )
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    payload = {
        "event": "http_request",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "client_ip_hash": hash_sensitive_value(request.client.host if request.client else None),
    }
    logger.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return response

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
app.include_router(knowledge.router, prefix="/api")
app.include_router(intake.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(billing.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(account.router, prefix="/api")
app.include_router(health_metrics.router, prefix="/api")


@app.get("/api/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version
    }


@app.get("/api/ready")
async def ready_check(response: Response):
    """Readiness endpoint for deployment and CI smoke checks.

    Returns HTTP 503 when database or blocking config checks fail so deploy
    infrastructure does not treat degraded instances as healthy. Warnings such
    as mock billing remain visible in the body but do not fail readiness.
    """
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("SELECT 1")
        db_status = "ok"
    except Exception as exc:
        db_status = f"error:{exc.__class__.__name__}"
    config_details = settings.readiness_snapshot()
    config_status = config_details["status"]
    is_ready = db_status == "ok" and config_status == "ok"
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if is_ready else "degraded",
        "checks": {
            "database": db_status,
            "config": config_status,
            "config_details": config_details,
        },
    }


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": f"欢迎使用 {settings.app_name}",
        "docs": "/api/docs"
    }
