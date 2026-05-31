"""User feedback models for AI and recognition quality loops."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import enum

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AIFeedbackType(str, enum.Enum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    UNSAFE = "unsafe"
    CORRECTION = "correction"
    RECOGNITION_CORRECTION = "recognition_correction"
    KNOWLEDGE_GAP = "knowledge_gap"


class AIFeedbackStatus(str, enum.Enum):
    OPEN = "open"
    REVIEWED = "reviewed"
    CLOSED = "closed"


class AIFeedback(Base):
    """Feedback attached to an AI assistant message or recognition result."""

    __tablename__ = "ai_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    message_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    app_message_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_messages.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    feedback_type: Mapped[AIFeedbackType] = mapped_column(
        SQLEnum(
            AIFeedbackType,
            name="aifeedbacktype",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        index=True,
        nullable=False,
    )
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    correction_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correction_text_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[AIFeedbackStatus] = mapped_column(
        SQLEnum(
            AIFeedbackStatus,
            name="aifeedbackstatus",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=AIFeedbackStatus.OPEN,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
