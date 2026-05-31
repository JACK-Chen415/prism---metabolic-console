"""Security, session, and audit models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class DeviceSession(Base):
    """Refresh-token backed device session."""

    __tablename__ = "device_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    refresh_jti_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    device_label: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    user_agent_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="device_sessions")


class SecurityAuditLog(Base):
    """Minimal structured audit log for security and data-rights events."""

    __tablename__ = "security_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    event_status: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    route_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    actor_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    user_agent_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="security_audit_logs")


from app.models.user import User
