"""
API 依赖注入
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.services.auth_security import assert_access_session_active


# HTTP Bearer Token 认证方案
security = HTTPBearer()


async def get_current_token_payload(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
):
    token = credentials.credentials

    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的Token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 检查 Token 类型
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请使用Access Token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return payload


async def get_current_user(
    token_payload: Annotated[dict, Depends(get_current_token_payload)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    """
    获取当前登录用户
    
    从 Authorization Header 中提取 JWT Token，验证后返回用户对象
    """
    user_id = token_payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的Token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # 查询用户
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )

    try:
        await assert_access_session_active(db, user_id=user.id, token_payload=token_payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"}
        ) from exc
    
    return user


# 类型别名，简化依赖注入
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentTokenPayload = Annotated[dict, Depends(get_current_token_payload)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
