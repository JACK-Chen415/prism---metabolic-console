"""Authentication session and security audit helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_session_id,
    hash_sensitive_value,
)
from app.models.security import DeviceSession, SecurityAuditLog
from app.models.user import User


PASSWORD_LOGIN_FAILURE_LIMIT = 5
PASSWORD_LOGIN_LOCKOUT_WINDOW_MINUTES = 15
PASSWORD_LOGIN_FAILURE_STATUSES = {"failure", "failure_locked"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _request_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else None


def _request_user_agent(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    return request.headers.get("user-agent")


def _device_label(request: Optional[Request]) -> str:
    if request is None:
        return "unknown-device"
    explicit = (request.headers.get("x-device-label") or "").strip()
    if explicit:
        return explicit[:120]
    user_agent = (_request_user_agent(request) or "web").strip()
    return user_agent[:120] or "web"


SENSITIVE_AUDIT_METADATA_KEY_MARKERS = (
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "otp",
    "captcha",
    "code",
    "phone",
    "mobile",
    "email",
    "raw",
    "content",
    "image",
    "photo",
    "file",
    "jti",
)

SAFE_AUDIT_TEXT_METADATA_KEYS = {
    "billing_plan",
    "checkout_id",
    "consent_accepted_at",
    "consent_version",
    "end_date",
    "format",
    "plan",
    "previous_plan",
    "previous_status",
    "provider",
    "report_type",
    "request_id",
    "route_name",
    "source",
    "start_date",
    "status",
    "target_status",
    "type",
}


def _is_sensitive_audit_metadata_key(key: str) -> bool:
    lowered = key.strip().lower()
    if lowered in {"request_id", "checkout_id"}:
        return False
    return any(marker in lowered for marker in SENSITIVE_AUDIT_METADATA_KEY_MARKERS)


def _sanitize_audit_string(key: str, value: str) -> str:
    cleaned = value.strip()
    lowered_key = key.strip().lower()
    if _is_sensitive_audit_metadata_key(lowered_key):
        return "[redacted]"
    if re.search(r"(?i)(bearer\s+)?[a-z0-9_-]{24,}\.[a-z0-9_-]{12,}\.[a-z0-9_-]{12,}", cleaned):
        return "[redacted]"
    if re.search(r"(?i)\b(sk|ak|pk|rk|ep)-[a-z0-9_-]{8,}\b", cleaned):
        return "[redacted]"
    if len(cleaned) > 120 and lowered_key not in SAFE_AUDIT_TEXT_METADATA_KEYS:
        return "[redacted-long-text]"
    return cleaned[:180]


def _sanitize_audit_metadata_value(key: str, value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if depth >= 3:
        return "[redacted-depth]"
    if isinstance(value, str):
        return _sanitize_audit_string(key, value)
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            item_key = str(raw_key)[:80]
            sanitized[item_key] = _sanitize_audit_metadata_value(item_key, raw_value, depth + 1)
        return sanitized
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_audit_metadata_value(key, item, depth + 1) for item in list(value)[:50]]
    return _sanitize_audit_string(key, str(value))


def sanitize_audit_metadata(metadata: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Redact caller metadata before writing security audit logs."""
    if not metadata:
        return {}
    return {
        str(key)[:80]: _sanitize_audit_metadata_value(str(key), value)
        for key, value in metadata.items()
    }


async def audit_security_event(
    db: AsyncSession,
    *,
    event_type: str,
    event_status: str,
    user_id: Optional[int] = None,
    request: Optional[Request] = None,
    actor: Optional[str] = None,
    session_id: Optional[str] = None,
    route_name: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Write a sanitized security audit event."""
    db.add(
        SecurityAuditLog(
            user_id=user_id,
            event_type=event_type,
            event_status=event_status,
            route_name=route_name,
            actor_hash=hash_sensitive_value(actor),
            ip_hash=hash_sensitive_value(_request_ip(request)),
            user_agent_hash=hash_sensitive_value(_request_user_agent(request)),
            session_id=session_id,
            metadata_json=sanitize_audit_metadata(metadata),
        )
    )
    await db.flush()


async def is_password_login_locked(
    db: AsyncSession,
    *,
    actor: str,
    now: Optional[datetime] = None,
    failure_limit: int = PASSWORD_LOGIN_FAILURE_LIMIT,
    window_minutes: int = PASSWORD_LOGIN_LOCKOUT_WINDOW_MINUTES,
) -> bool:
    """Return whether a password-login actor is temporarily locked.

    The lookup is driven by sanitized audit rows so the service does not need
    to persist raw phone numbers or introduce a second abuse-tracking table for
    the current gray-release scope.
    """
    actor_hash = hash_sensitive_value(actor)
    if not actor_hash:
        return False

    cutoff = (now or _utcnow()) - timedelta(minutes=window_minutes)
    result = await db.execute(
        select(func.count(SecurityAuditLog.id)).where(
            SecurityAuditLog.event_type == "auth.password_login",
            SecurityAuditLog.event_status.in_(PASSWORD_LOGIN_FAILURE_STATUSES),
            SecurityAuditLog.actor_hash == actor_hash,
            SecurityAuditLog.created_at >= cutoff,
        )
    )
    failure_count = int(result.scalar_one() or 0)
    return failure_count >= failure_limit


async def create_session_token_pair(
    db: AsyncSession,
    *,
    user: User,
    request: Optional[Request] = None,
) -> tuple[str, str, DeviceSession]:
    """Create access/refresh tokens and persist a revocable device session."""
    session_id = create_session_id()
    refresh_token, refresh_jti = create_refresh_token(user.id, session_id=session_id)
    access_token = create_access_token(user.id, session_id=session_id)
    expires_at = _utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days)

    device_session = DeviceSession(
        user_id=user.id,
        session_id=session_id,
        refresh_jti_hash=hash_sensitive_value(refresh_jti) or "",
        device_label=_device_label(request),
        user_agent_hash=hash_sensitive_value(_request_user_agent(request)),
        ip_hash=hash_sensitive_value(_request_ip(request)),
        expires_at=expires_at,
        last_seen_at=_utcnow(),
    )
    db.add(device_session)
    await db.flush()
    return access_token, refresh_token, device_session


async def assert_access_session_active(
    db: AsyncSession,
    *,
    user_id: int,
    token_payload: dict[str, Any],
) -> None:
    """Reject access tokens whose backing device session was revoked."""
    session_id = token_payload.get("sid")
    if not session_id:
        return

    result = await db.execute(
        select(DeviceSession).where(
            DeviceSession.user_id == user_id,
            DeviceSession.session_id == session_id,
        )
    )
    device_session = result.scalar_one_or_none()
    now = _utcnow()
    if (
        device_session is None
        or device_session.revoked_at is not None
        or device_session.expires_at <= now
    ):
        raise ValueError("会话已失效，请重新登录")


async def rotate_refresh_session(
    db: AsyncSession,
    *,
    user: User,
    refresh_payload: dict[str, Any],
    request: Optional[Request] = None,
) -> tuple[str, str, DeviceSession]:
    """Rotate refresh jti for the current device session."""
    session_id = refresh_payload.get("sid")
    refresh_jti = refresh_payload.get("jti")
    if not session_id or not refresh_jti:
        raise ValueError("Refresh Token 缺少会话信息")

    result = await db.execute(
        select(DeviceSession).where(
            DeviceSession.user_id == user.id,
            DeviceSession.session_id == session_id,
        )
    )
    device_session = result.scalar_one_or_none()
    now = _utcnow()
    if device_session is None or device_session.revoked_at is not None or device_session.expires_at <= now:
        raise ValueError("Refresh Token 对应会话已失效")

    expected_hash = hash_sensitive_value(refresh_jti)
    if expected_hash != device_session.refresh_jti_hash:
        device_session.revoked_at = now
        device_session.revoke_reason = "refresh_reuse_detected"
        raise ValueError("Refresh Token 已轮换或被撤销")

    new_refresh_token, new_refresh_jti = create_refresh_token(user.id, session_id=session_id)
    access_token = create_access_token(user.id, session_id=session_id)
    device_session.refresh_jti_hash = hash_sensitive_value(new_refresh_jti) or ""
    device_session.last_seen_at = now
    device_session.expires_at = now + timedelta(days=settings.jwt_refresh_token_expire_days)
    device_session.ip_hash = hash_sensitive_value(_request_ip(request))
    device_session.user_agent_hash = hash_sensitive_value(_request_user_agent(request))
    await db.flush()
    return access_token, new_refresh_token, device_session


async def revoke_device_session(
    db: AsyncSession,
    *,
    user_id: int,
    session_id: Optional[str],
    reason: str,
) -> bool:
    if not session_id:
        return False

    result = await db.execute(
        select(DeviceSession).where(
            DeviceSession.user_id == user_id,
            DeviceSession.session_id == session_id,
            DeviceSession.revoked_at.is_(None),
        )
    )
    device_session = result.scalar_one_or_none()
    if not device_session:
        return False

    device_session.revoked_at = _utcnow()
    device_session.revoke_reason = reason
    await db.flush()
    return True


async def revoke_all_device_sessions(
    db: AsyncSession,
    *,
    user_id: int,
    reason: str,
    except_session_id: Optional[str] = None,
) -> int:
    """Revoke every active device session for a user after credential changes."""
    result = await db.execute(
        select(DeviceSession).where(
            DeviceSession.user_id == user_id,
            DeviceSession.revoked_at.is_(None),
        )
    )
    sessions = list(result.scalars().all())
    now = _utcnow()
    revoked_count = 0
    for device_session in sessions:
        if except_session_id and device_session.session_id == except_session_id:
            continue
        device_session.revoked_at = now
        device_session.revoke_reason = reason
        revoked_count += 1
    if revoked_count:
        await db.flush()
    return revoked_count
