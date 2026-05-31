import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.routes import insights as insights_route
from app.core.security import hash_sensitive_value
from app.models.feedback import AIFeedback, AIFeedbackType
from app.models.message import AppMessage, MessageType
from app.models.user import User
from app.schemas.chat import AIFeedbackCreate
from app.services.insights import SMART_INSIGHT_ATTRIBUTION_PREFIX


class _FakeScalarList:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeRouteResult:
    def __init__(self, scalar=None, rows=None):
        self.scalar = scalar
        self.rows = rows or []

    def scalar_one_or_none(self):
        return self.scalar

    def scalars(self):
        return _FakeScalarList(self.rows)


class _FakeInsightFeedbackDb:
    def __init__(self, message, feedback_rows=None):
        self.message = message
        self.feedback_rows = feedback_rows or []
        self.added = []
        self.next_feedback_id = 401
        self.execute_count = 0

    async def execute(self, _statement):
        self.execute_count += 1
        if self.execute_count == 1:
            return _FakeRouteResult(scalar=self.message)
        return _FakeRouteResult(rows=self.feedback_rows)

    def add(self, item):
        if isinstance(item, AIFeedback):
            item.id = self.next_feedback_id
            item.created_at = datetime(2026, 5, 30, tzinfo=timezone.utc)
            self.next_feedback_id += 1
            self.feedback_rows.insert(0, item)
        self.added.append(item)

    async def flush(self):
        return None

    async def refresh(self, item):
        if isinstance(item, AIFeedback) and not item.created_at:
            item.created_at = datetime(2026, 5, 30, tzinfo=timezone.utc)
        return None


def _smart_message():
    message = AppMessage(
        id=31,
        user_id=7,
        message_type=MessageType.ADVICE,
        title="智能洞察",
        content="今晚少盐一些。",
        attribution=f"{SMART_INSIGHT_ATTRIBUTION_PREFIX}:2026-05-30:sodium",
    )
    message.created_at = datetime(2026, 5, 30, tzinfo=timezone.utc)
    return message


@pytest.mark.asyncio
async def test_create_insight_feedback_links_app_message_without_raw_audit_text(monkeypatch) -> None:
    message = _smart_message()
    db = _FakeInsightFeedbackDb(message)
    captured_audit = {}
    raw_correction = "这条洞察没有考虑我今天训练量很大。"

    async def fake_audit_security_event(_db, **kwargs):
        captured_audit.update(kwargs)

    monkeypatch.setattr(insights_route, "audit_security_event", fake_audit_security_event)

    response = await insights_route.create_insight_feedback(
        message_id=message.id,
        data=AIFeedbackCreate(
            feedback_type=AIFeedbackType.KNOWLEDGE_GAP,
            rating=3,
            tags=[" insight ", "knowledge gap", "insight"],
            correction_text=raw_correction,
            metadata={
                "source": "home",
                "surface": "latest_insight",
                "context": "ADVICE",
                "raw_note": "should not be copied to metadata",
            },
        ),
        request=None,
        current_user=User(id=7, phone="13800138000", password_hash="x"),
        db=db,
    )

    feedback = db.added[0]
    assert response.app_message_id == message.id
    assert response.message_id is None
    assert feedback.app_message_id == message.id
    assert feedback.correction_text == raw_correction
    assert feedback.correction_text_hash == hash_sensitive_value(raw_correction)
    assert feedback.tags_json == ["insight", "knowledge_gap"]
    assert feedback.metadata_json["source"] == "home"
    assert feedback.metadata_json["app_message_id"] == message.id
    assert "raw_note" not in feedback.metadata_json

    serialized_audit = json.dumps(captured_audit, ensure_ascii=False, default=str)
    assert captured_audit["event_type"] == "insight.feedback.create"
    assert captured_audit["metadata"]["app_message_id"] == message.id
    assert captured_audit["metadata"]["correction_text_hash"] == hash_sensitive_value(raw_correction)
    assert raw_correction not in serialized_audit
    assert message.content not in serialized_audit


@pytest.mark.asyncio
async def test_create_insight_feedback_rejects_non_smart_messages() -> None:
    message = _smart_message()
    message.attribution = "manual"
    db = _FakeInsightFeedbackDb(message)

    with pytest.raises(HTTPException) as exc_info:
        await insights_route.create_insight_feedback(
            message_id=message.id,
            data=AIFeedbackCreate(feedback_type=AIFeedbackType.HELPFUL, rating=5),
            request=None,
            current_user=User(id=7, phone="13800138000", password_hash="x"),
            db=db,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_list_insight_feedback_returns_current_user_app_message_feedback() -> None:
    message = _smart_message()
    feedback = AIFeedback(
        id=9,
        user_id=7,
        app_message_id=message.id,
        feedback_type=AIFeedbackType.HELPFUL,
        rating=5,
        tags_json=["insight", "helpful"],
    )
    feedback.created_at = datetime(2026, 5, 30, tzinfo=timezone.utc)
    db = _FakeInsightFeedbackDb(message, [feedback])

    items = await insights_route.list_insight_feedback(
        message_id=message.id,
        current_user=User(id=7, phone="13800138000", password_hash="x"),
        db=db,
    )

    assert len(items) == 1
    assert items[0].app_message_id == message.id
    assert items[0].feedback_type == AIFeedbackType.HELPFUL
