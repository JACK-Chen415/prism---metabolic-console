"""Privacy-preserving intake review telemetry models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class IntakeReviewTelemetrySnapshot(Base):
    """Aggregated local intake review queue counts submitted by a user device.

    This table intentionally stores only allowlisted counts. It must not store
    food names, notes, raw candidate text, health profile text, images, or
    client-side draft payloads.
    """

    __tablename__ = "intake_review_telemetry_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    total_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    in_review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    low_confidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_risk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hard_block_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_counts_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=True)
    status_counts_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
