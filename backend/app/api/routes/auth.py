"""
用户认证 API 路由
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import CurrentTokenPayload, CurrentUser, DbSession
from app.core.security import (
    verify_password,
    get_password_hash,
    decode_token
)
from app.core.config import settings
from app.models.user import User
from app.schemas.user import (
    UserRegister,
    UserLogin,
    CodeLoginRequest,
    SendCodeRequest,
    ResetPasswordRequest,
    UserProfileUpdate,
    PasswordChange,
    RefreshTokenRequest,
    RevokeSessionRequest,
    UserResponse,
    DeviceSessionResponse,
    TokenResponse,
    LoginResponse,
    DailyTargets
)
from app.services.verification_service import verification_service
from app.services.target_service import calculate_daily_targets
from app.services.auth_security import (
    audit_security_event,
    create_session_token_pair,
    is_password_login_locked,
    revoke_all_device_sessions,
    revoke_device_session,
    rotate_refresh_session,
)
from app.models.health_condition import ConditionStatus
from app.models.security import DeviceSession

router = APIRouter(prefix="/auth", tags=["认证"])

REFRESH_TOKEN_COOKIE_NAME = "prism_refresh_token"
REFRESH_TOKEN_COOKIE_PATH = "/api/auth"
AUTH_MUTATION_CLIENT_HEADER = "x-prism-client"
AUTH_MUTATION_CLIENT_VALUE = "web"
AUTH_MUTATION_X_REQUESTED_WITH_HEADER = "x-requested-with"
AUTH_MUTATION_X_REQUESTED_WITH_VALUE = "xmlhttprequest"


def _refresh_cookie_max_age_seconds() -> int:
    return settings.jwt_refresh_token_expire_days * 24 * 60 * 60


def _refresh_cookie_samesite() -> str:
    return "none" if settings.is_production else "lax"


def _set_refresh_token_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        max_age=_refresh_cookie_max_age_seconds(),
        path=REFRESH_TOKEN_COOKIE_PATH,
        secure=settings.is_production,
        httponly=True,
        samesite=_refresh_cookie_samesite(),
    )


def _delete_refresh_token_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        path=REFRESH_TOKEN_COOKIE_PATH,
        secure=settings.is_production,
        httponly=True,
        samesite=_refresh_cookie_samesite(),
    )


def _delete_refresh_cookie_headers() -> dict[str, str]:
    response = Response()
    _delete_refresh_token_cookie(response)
    set_cookie = response.headers.get("set-cookie")
    return {"Set-Cookie": set_cookie} if set_cookie else {}


def _access_token_response(access_token: str) -> TokenResponse:
    return TokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


def _refresh_auth_exception(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers=_delete_refresh_cookie_headers(),
    )


def _has_auth_mutation_client_header(request: Request) -> bool:
    prism_client = (request.headers.get(AUTH_MUTATION_CLIENT_HEADER) or "").strip().lower()
    requested_with = (request.headers.get(AUTH_MUTATION_X_REQUESTED_WITH_HEADER) or "").strip().lower()
    return (
        prism_client == AUTH_MUTATION_CLIENT_VALUE
        or requested_with == AUTH_MUTATION_X_REQUESTED_WITH_VALUE
    )


async def _reject_auth_mutation_without_client_header(
    *,
    request: Request,
    db: DbSession,
    event_type: str,
    route_name: str,
) -> None:
    if _has_auth_mutation_client_header(request):
        return

    await audit_security_event(
        db,
        event_type=event_type,
        event_status="missing_client_header",
        request=request,
        route_name=route_name,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="缺少有效客户端请求头",
    )


def _decode_logout_payload(request: Request) -> dict | None:
    candidates: list[str] = []
    authorization = (request.headers.get("authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        candidates.append(authorization.split(None, 1)[1].strip())
    cookie_token = request.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
    if cookie_token:
        candidates.append(cookie_token)

    for token in candidates:
        payload = decode_token(token)
        if (
            payload
            and payload.get("type") in {"access", "refresh"}
            and payload.get("sub") is not None
            and payload.get("sid")
        ):
            return payload
    return None


def _device_session_response(row: DeviceSession, *, current_session_id: str | None) -> DeviceSessionResponse:
    return DeviceSessionResponse(
        session_id=row.session_id,
        device_label=row.device_label,
        is_current=bool(current_session_id and row.session_id == current_session_id),
        is_revoked=row.revoked_at is not None,
        expires_at=row.expires_at,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        revoked_at=row.revoked_at,
        revoke_reason=row.revoke_reason,
    )


def _device_session_group_key(row: DeviceSession) -> str:
    if row.user_agent_hash or row.ip_hash:
        return f"{row.user_agent_hash or 'unknown-ua'}:{row.ip_hash or 'unknown-ip'}"
    return f"label:{row.device_label or row.session_id}"


def _dedupe_device_session_rows(rows: list[DeviceSession], *, current_session_id: str | None) -> list[DeviceSession]:
    """Collapse repeated logins from the same browser/device for settings UI."""
    selected_by_device: dict[str, DeviceSession] = {}
    for row in rows:
        if row.revoked_at is not None:
            continue
        key = _device_session_group_key(row)
        selected = selected_by_device.get(key)
        if selected is None or row.session_id == current_session_id:
            selected_by_device[key] = row

    return sorted(
        selected_by_device.values(),
        key=lambda row: (
            row.session_id != current_session_id,
            -(row.last_seen_at.timestamp() if row.last_seen_at else 0),
            -(row.created_at.timestamp() if row.created_at else 0),
        ),
    )


def _send_code_response_payload(result) -> dict:
    payload = {
        "success": True,
        "message": result.message,
        "expires_in": result.expires_in,
    }
    if result.debug_code and settings.is_development:
        payload["debug_code"] = result.debug_code
        payload["message"] = f"{result.message}（开发环境验证码：{result.debug_code}）"
    return payload


@router.post(
    "/register",
    response_model=LoginResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def register(data: UserRegister, request: Request, response: Response, db: DbSession):
    """
    用户注册

    - **phone**: 11位手机号
    - **password**: 密码（6-50位）
    - **nickname**: 可选昵称
    """
    # 检查手机号是否已注册
    result = await db.execute(select(User).where(User.phone == data.phone))
    if result.scalar_one_or_none():
        await audit_security_event(
            db,
            event_type="auth.register",
            event_status="duplicate_phone",
            request=request,
            actor=data.phone,
            route_name="/api/auth/register",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该手机号已注册"
        )

    # 创建用户
    consent_accepted_at = datetime.now(timezone.utc)
    user = User(
        phone=data.phone,
        password_hash=get_password_hash(data.password),
        nickname=data.nickname or f"用户{data.phone[-4:]}",
        consent_version=data.consent_version,
        consent_accepted_at=consent_accepted_at,
        consent_terms_accepted=data.terms_accepted,
        consent_privacy_accepted=data.privacy_accepted,
        consent_ai_use_accepted=data.ai_use_accepted,
        consent_health_disclaimer_accepted=data.health_disclaimer_accepted,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    access_token, refresh_token, device_session = await create_session_token_pair(
        db,
        user=user,
        request=request,
    )
    await audit_security_event(
        db,
        event_type="auth.register",
        event_status="success",
        user_id=user.id,
        request=request,
        actor=data.phone,
        session_id=device_session.session_id,
        route_name="/api/auth/register",
        metadata={
            "consent_version": data.consent_version,
            "consent_document_count": 4,
            "consent_accepted_at": consent_accepted_at.isoformat(),
        },
    )
    _set_refresh_token_cookie(response, refresh_token)

    return LoginResponse(
        user=UserResponse.model_validate(user),
        tokens=_access_token_response(access_token),
    )


@router.post("/login", response_model=LoginResponse, response_model_exclude_none=True)
async def login(data: UserLogin, request: Request, response: Response, db: DbSession):
    """
    用户登录

    - **phone**: 手机号
    - **password**: 密码
    """
    if await is_password_login_locked(db, actor=data.phone):
        await audit_security_event(
            db,
            event_type="auth.password_login",
            event_status="failure_locked",
            request=request,
            actor=data.phone,
            route_name="/api/auth/login",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录失败次数过多，请稍后再试",
            headers={"Retry-After": "900"},
        )

    # 查询用户
    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        await audit_security_event(
            db,
            event_type="auth.password_login",
            event_status="failure",
            user_id=user.id if user else None,
            request=request,
            actor=data.phone,
            route_name="/api/auth/login",
        )
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

    access_token, refresh_token, device_session = await create_session_token_pair(
        db,
        user=user,
        request=request,
    )
    await audit_security_event(
        db,
        event_type="auth.password_login",
        event_status="success",
        user_id=user.id,
        request=request,
        actor=data.phone,
        session_id=device_session.session_id,
        route_name="/api/auth/login",
    )
    _set_refresh_token_cookie(response, refresh_token)

    return LoginResponse(
        user=UserResponse.model_validate(user),
        tokens=_access_token_response(access_token),
    )


@router.post("/send-code")
async def send_code(data: SendCodeRequest, request: Request, db: DbSession):
    """
    发送验证码（开发模式）

    purpose:
    - login
    - reset_password
    """
    if data.purpose not in {"login", "reset_password"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不支持的验证码用途"
        )

    if data.purpose == "reset_password":
        result = await db.execute(select(User).where(User.phone == data.phone))
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="该手机号未注册"
            )

    result = verification_service.send_code(data.phone, data.purpose)
    await audit_security_event(
        db,
        event_type=f"otp.{data.purpose}.send",
        event_status="success" if result.success else "limited",
        request=request,
        actor=data.phone,
        route_name="/api/auth/send-code",
        metadata={
            "provider": result.provider_name,
            "retry_after_seconds": result.retry_after_seconds,
        },
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=result.message,
            headers={"Retry-After": str(result.retry_after_seconds or 60)},
        )

    return _send_code_response_payload(result)


@router.post("/login-code", response_model=LoginResponse, response_model_exclude_none=True)
async def login_with_code(data: CodeLoginRequest, request: Request, response: Response, db: DbSession):
    """验证码登录"""
    if not verification_service.verify(data.phone, "login", data.code):
        locked = verification_service.is_locked(data.phone, "login")
        await audit_security_event(
            db,
            event_type="auth.otp_login",
            event_status="failure_locked" if locked else "failure",
            request=request,
            actor=data.phone,
            route_name="/api/auth/login-code",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="验证码错误次数过多，请稍后再试" if locked else "验证码无效或已过期"
        )

    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该手机号未注册"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )

    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    access_token, refresh_token, device_session = await create_session_token_pair(
        db,
        user=user,
        request=request,
    )
    await audit_security_event(
        db,
        event_type="auth.otp_login",
        event_status="success",
        user_id=user.id,
        request=request,
        actor=data.phone,
        session_id=device_session.session_id,
        route_name="/api/auth/login-code",
    )
    _set_refresh_token_cookie(response, refresh_token)

    return LoginResponse(
        user=UserResponse.model_validate(user),
        tokens=_access_token_response(access_token),
    )


@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest, request: Request, db: DbSession):
    """通过验证码重置密码"""
    if not verification_service.verify(data.phone, "reset_password", data.code):
        locked = verification_service.is_locked(data.phone, "reset_password")
        await audit_security_event(
            db,
            event_type="auth.reset_password",
            event_status="otp_failure_locked" if locked else "otp_failure",
            request=request,
            actor=data.phone,
            route_name="/api/auth/reset-password",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="验证码错误次数过多，请稍后再试" if locked else "验证码无效或已过期"
        )

    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该手机号未注册"
        )

    user.password_hash = get_password_hash(data.new_password)
    revoked_count = await revoke_all_device_sessions(
        db,
        user_id=user.id,
        reason="password_reset",
    )
    await db.flush()
    await audit_security_event(
        db,
        event_type="auth.reset_password",
        event_status="success",
        user_id=user.id,
        request=request,
        actor=data.phone,
        route_name="/api/auth/reset-password",
        metadata={"revoked_sessions": revoked_count},
    )
    return {"success": True, "message": "密码重置成功，请重新登录所有设备"}


@router.post("/refresh", response_model=TokenResponse, response_model_exclude_none=True)
async def refresh_token(
    request: Request,
    response: Response,
    db: DbSession,
    data: RefreshTokenRequest | None = None,
):
    """
    刷新 Access Token

    使用 Refresh Token 获取新的 Access Token
    """
    await _reject_auth_mutation_without_client_header(
        request=request,
        db=db,
        event_type="auth.refresh",
        route_name="/api/auth/refresh",
    )

    refresh_token_value = request.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
    if not refresh_token_value and data is not None:
        refresh_token_value = data.refresh_token

    if not refresh_token_value:
        await audit_security_event(
            db,
            event_type="auth.refresh",
            event_status="missing_token",
            request=request,
            route_name="/api/auth/refresh",
        )
        raise _refresh_auth_exception("缺少Refresh Token")

    payload = decode_token(refresh_token_value)

    if payload is None or payload.get("type") != "refresh":
        await audit_security_event(
            db,
            event_type="auth.refresh",
            event_status="invalid_token",
            request=request,
            route_name="/api/auth/refresh",
        )
        raise _refresh_auth_exception("无效或过期的Refresh Token")

    user_id = payload.get("sub")
    if user_id is None:
        await audit_security_event(
            db,
            event_type="auth.refresh",
            event_status="missing_subject",
            request=request,
            session_id=payload.get("sid"),
            route_name="/api/auth/refresh",
        )
        raise _refresh_auth_exception("无效或过期的Refresh Token")

    try:
        parsed_user_id = int(user_id)
    except (TypeError, ValueError):
        await audit_security_event(
            db,
            event_type="auth.refresh",
            event_status="invalid_subject",
            request=request,
            session_id=payload.get("sid"),
            route_name="/api/auth/refresh",
        )
        raise _refresh_auth_exception("无效或过期的Refresh Token")

    # 验证用户是否存在且有效
    result = await db.execute(select(User).where(User.id == parsed_user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        await audit_security_event(
            db,
            event_type="auth.refresh",
            event_status="user_inactive",
            user_id=parsed_user_id,
            request=request,
            session_id=payload.get("sid"),
            route_name="/api/auth/refresh",
        )
        raise _refresh_auth_exception("用户不存在或已被禁用")

    try:
        access_token, new_refresh_token, device_session = await rotate_refresh_session(
            db,
            user=user,
            refresh_payload=payload,
            request=request,
        )
    except ValueError as exc:
        await audit_security_event(
            db,
            event_type="auth.refresh",
            event_status="revoked_or_reused",
            user_id=user.id,
            request=request,
            session_id=payload.get("sid"),
            route_name="/api/auth/refresh",
        )
        raise _refresh_auth_exception(str(exc)) from exc

    await audit_security_event(
        db,
        event_type="auth.refresh",
        event_status="success",
        user_id=user.id,
        request=request,
        session_id=device_session.session_id,
        route_name="/api/auth/refresh",
    )
    _set_refresh_token_cookie(response, new_refresh_token)

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: DbSession,
):
    """退出登录并撤销当前设备会话。"""
    await _reject_auth_mutation_without_client_header(
        request=request,
        db=db,
        event_type="auth.logout",
        route_name="/api/auth/logout",
    )

    payload = _decode_logout_payload(request)
    if not payload:
        await audit_security_event(
            db,
            event_type="auth.logout",
            event_status="missing_or_invalid_token",
            request=request,
            route_name="/api/auth/logout",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的Token",
            headers=_delete_refresh_cookie_headers(),
        )

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as exc:
        await audit_security_event(
            db,
            event_type="auth.logout",
            event_status="invalid_subject",
            request=request,
            session_id=payload.get("sid"),
            route_name="/api/auth/logout",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的Token",
            headers=_delete_refresh_cookie_headers(),
        ) from exc
    session_id = payload.get("sid")
    revoked = await revoke_device_session(
        db,
        user_id=user_id,
        session_id=session_id,
        reason="user_logout",
    )
    await audit_security_event(
        db,
        event_type="auth.logout",
        event_status="success" if revoked else "legacy_token",
        user_id=user_id,
        request=request,
        session_id=session_id,
        route_name="/api/auth/logout",
    )
    _delete_refresh_token_cookie(response)
    return {"success": True, "message": "已退出登录"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUser):
    """获取当前用户信息"""
    return UserResponse.model_validate(current_user)


@router.get("/sessions", response_model=list[DeviceSessionResponse])
async def list_device_sessions(
    request: Request,
    current_user: CurrentUser,
    token_payload: CurrentTokenPayload,
    db: DbSession,
):
    """列出当前用户的设备会话。"""
    result = await db.execute(
        select(DeviceSession)
        .where(DeviceSession.user_id == current_user.id)
        .order_by(DeviceSession.last_seen_at.desc(), DeviceSession.created_at.desc())
    )
    rows = list(result.scalars().all())
    visible_rows = _dedupe_device_session_rows(rows, current_session_id=token_payload.get("sid"))
    await audit_security_event(
        db,
        event_type="auth.session.list",
        event_status="success",
        user_id=current_user.id,
        request=request,
        session_id=token_payload.get("sid"),
        route_name="/api/auth/sessions",
        metadata={"returned": len(visible_rows), "raw_session_count": len(rows)},
    )
    return [_device_session_response(row, current_session_id=token_payload.get("sid")) for row in visible_rows]


@router.delete("/sessions/{session_id}")
async def revoke_device_session_route(
    session_id: str,
    data: RevokeSessionRequest,
    request: Request,
    current_user: CurrentUser,
    token_payload: CurrentTokenPayload,
    db: DbSession,
):
    """撤销指定设备会话，但不允许撤销当前会话以外的其他用户会话。"""
    if not session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="会话标识不能为空")

    if session_id == token_payload.get("sid"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请使用退出登录关闭当前会话")

    result = await db.execute(
        select(DeviceSession).where(
            DeviceSession.user_id == current_user.id,
            DeviceSession.session_id == session_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        await audit_security_event(
            db,
            event_type="auth.session.revoke",
            event_status="not_found",
            user_id=current_user.id,
            request=request,
            session_id=token_payload.get("sid"),
            route_name="/api/auth/sessions/{session_id}",
            metadata={"target_session_id": session_id},
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    revoked = await revoke_device_session(
        db,
        user_id=current_user.id,
        session_id=session_id,
        reason="user_revocation",
    )
    if not revoked:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="会话无法撤销")

    await audit_security_event(
        db,
        event_type="auth.session.revoke",
        event_status="success",
        user_id=current_user.id,
        request=request,
        session_id=token_payload.get("sid"),
        route_name="/api/auth/sessions/{session_id}",
        metadata={
            "target_session_id": session_id,
            "confirm": data.confirm,
        },
    )
    return {"success": True, "message": "会话已撤销"}


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
    request: Request,
    current_user: CurrentUser,
    token_payload: CurrentTokenPayload,
    db: DbSession,
):
    """修改密码，并撤销所有已登录设备会话。"""
    if not verify_password(data.old_password, current_user.password_hash):
        await audit_security_event(
            db,
            event_type="auth.change_password",
            event_status="failure",
            user_id=current_user.id,
            request=request,
            session_id=token_payload.get("sid"),
            route_name="/api/auth/change-password",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误"
        )

    current_user.password_hash = get_password_hash(data.new_password)
    revoked_count = await revoke_all_device_sessions(
        db,
        user_id=current_user.id,
        reason="password_change",
    )
    await db.flush()
    await audit_security_event(
        db,
        event_type="auth.change_password",
        event_status="success",
        user_id=current_user.id,
        request=request,
        session_id=token_payload.get("sid"),
        route_name="/api/auth/change-password",
        metadata={"revoked_sessions": revoked_count},
    )

    return {"success": True, "message": "密码修改成功，请重新登录所有设备"}


@router.get("/daily-targets", response_model=DailyTargets)
async def get_daily_targets(current_user: CurrentUser, db: DbSession):
    """
    获取每日摄入目标

    基于用户身体参数动态计算
    """
    from sqlalchemy import select
    from app.models.health_condition import HealthCondition

    # 查询用户健康状况
    result = await db.execute(
        select(HealthCondition).where(
            HealthCondition.user_id == current_user.id,
            HealthCondition.status.in_([ConditionStatus.ACTIVE, ConditionStatus.MONITORING, ConditionStatus.ALERT])
        )
    )
    conditions = result.scalars().all()
    return calculate_daily_targets(current_user, conditions)
