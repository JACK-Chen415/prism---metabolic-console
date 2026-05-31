import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.routes import chat as chat_route
from app.core.security import hash_sensitive_value
from app.models.chat import ChatMessage, ChatSession, MessageRole
from app.models.feedback import AIFeedback, AIFeedbackStatus, AIFeedbackType
from app.models.knowledge import FallbackStatus, KnowledgeOrigin, RecommendationLevel
from app.models.user import User
from app.schemas.chat import FoodRecognitionResponse, FoodRecognitionResult, NutritionInfo


def test_ai_feedback_enums_use_persisted_lowercase_values() -> None:
    feedback_type = AIFeedback.__table__.c.feedback_type.type
    status_type = AIFeedback.__table__.c.status.type

    assert feedback_type.enums == [member.value for member in AIFeedbackType]
    assert status_type.enums == [member.value for member in AIFeedbackStatus]


def test_feedback_metadata_allowlist_removes_raw_sensitive_text() -> None:
    safe = chat_route._safe_feedback_metadata(
        {
            "source": "chat",
            "surface": "coach",
            "intensity": "high",
            "candidate_id": "cand-123",
            "prompt": "我对虾过敏，能不能吃",
            "reply": "可以放心吃",
            "correction_text": "这条建议有风险",
            "notes": "raw free text",
        }
    )

    assert safe == {"source": "chat", "surface": "coach", "intensity": "high", "candidate_id": "cand-123"}
    assert "prompt" not in safe
    assert "reply" not in safe
    assert "correction_text" not in safe


def test_feedback_audit_metadata_never_contains_raw_correction_text() -> None:
    raw_correction = "虾过敏用户不应被建议放心吃虾。"
    feedback = AIFeedback(
        id=7,
        user_id=1,
        session_id=2,
        message_id=3,
        feedback_type=AIFeedbackType.UNSAFE,
        rating=1,
        tags_json=["allergy", "unsafe"],
        correction_text=raw_correction,
        correction_text_hash=hash_sensitive_value(raw_correction),
        metadata_json={"source": "chat"},
        status=AIFeedbackStatus.OPEN,
    )
    feedback.created_at = datetime(2026, 5, 30, tzinfo=timezone.utc)

    metadata = chat_route._feedback_audit_metadata(feedback)
    serialized = json.dumps(metadata, ensure_ascii=False)

    assert metadata["feedback_type"] == "unsafe"
    assert metadata["has_correction"] is True
    assert metadata["tags_count"] == 2
    assert metadata["correction_text_hash"] == hash_sensitive_value(raw_correction)
    assert raw_correction not in serialized


def test_feedback_tags_are_deduplicated_lowercase_and_bounded() -> None:
    tags = chat_route._normalize_feedback_tags(
        [" Allergy ", "allergy", "Too Broad", "", "x" * 80] + [f"tag{i}" for i in range(20)]
    )

    assert tags[:3] == ["allergy", "too_broad", "x" * 40]
    assert len(tags) == 12


class _FakeRecognitionUploadFile:
    filename = "private-supper.jpg"
    content_type = "image/jpeg"

    async def read(self) -> bytes:
        return b"raw-image-bytes"


class _FakeRouteResult:
    def __init__(self, scalar=None):
        self.scalar = scalar

    def scalar_one_or_none(self):
        return self.scalar


class _FakeRecognitionDb:
    def __init__(self, session: ChatSession):
        self.session = session
        self.added = []
        self.next_message_id = 101
        self.flush_count = 0

    async def execute(self, _statement):
        return _FakeRouteResult(self.session)

    def add(self, item):
        if isinstance(item, ChatMessage):
            item.id = self.next_message_id
            self.next_message_id += 1
        self.added.append(item)

    async def flush(self):
        self.flush_count += 1
        return None

    async def refresh(self, item):
        if isinstance(item, ChatMessage) and not item.id:
            item.id = self.next_message_id
            self.next_message_id += 1
        return None


class _FakeRecognitionDoubaoService:
    def __init__(self):
        self.last_kwargs = None

    async def recognize_food(self, **kwargs):
        self.last_kwargs = kwargs
        return [
            FoodRecognitionResult(
                food_name="番茄鸡蛋面",
                confidence=0.92,
                estimated_portion="半碗",
                nutrition=NutritionInfo(calories=280, sodium=620, purine=45),
                category="STAPLE",
            )
        ], "识别完成"


class _FakeRecognitionKnowledgeService:
    async def evaluate_food_for_user(self, *_args, **kwargs):
        return SimpleNamespace(
            food_name=kwargs["food_name"],
            food_code="tomato_egg_noodle",
            matched_disease_codes=[],
            recommendation_level=RecommendationLevel.RECOMMEND,
            hard_blocks=[],
            summary="本地规则无特殊限制。",
            fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
        )

    def enforce_llm_output_safety(self, ai_response, **_kwargs):
        return ai_response


@pytest.mark.asyncio
async def test_recognition_upload_returns_message_id_without_auditing_raw_image(monkeypatch) -> None:
    db = _FakeRecognitionDb(ChatSession(id=9, user_id=1, title="photo flow"))
    fake_doubao = _FakeRecognitionDoubaoService()
    captured_audit = {}

    async def fake_get_user_conditions(*_args, **_kwargs):
        return []

    async def fake_write_knowledge_audit_log(_db, **kwargs):
        captured_audit.update(kwargs)
        return object()

    monkeypatch.setattr(
        chat_route,
        "sanitize_image_upload",
        lambda *_args, **_kwargs: SimpleNamespace(content=b"safe-jpeg", format="JPEG"),
    )
    monkeypatch.setattr(chat_route, "get_user_conditions", fake_get_user_conditions)
    monkeypatch.setattr(chat_route, "doubao_service", fake_doubao)
    monkeypatch.setattr(chat_route, "knowledge_service", _FakeRecognitionKnowledgeService())
    monkeypatch.setattr(chat_route, "write_knowledge_audit_log", fake_write_knowledge_audit_log)

    response = await chat_route.recognize_food_upload(
        file=_FakeRecognitionUploadFile(),
        prompt="少油",
        session_id=9,
        current_user=User(id=1, phone="13800138000", password_hash="x"),
        db=db,
    )

    assert isinstance(response, FoodRecognitionResponse)
    assert response.message_id == 101
    assert fake_doubao.last_kwargs["image_base64"]
    assert fake_doubao.last_kwargs["user_prompt"] == "少油"

    assistant_message = next(item for item in db.added if isinstance(item, ChatMessage))
    assert assistant_message.id == 101
    assert assistant_message.session_id == 9
    assert assistant_message.role == MessageRole.ASSISTANT
    assert assistant_message.attachments["recognition"]["source"] == "photo_upload"
    assert assistant_message.attachments["recognition"]["food_count"] == 1
    assert assistant_message.attachments["recognition"]["foods"][0]["food_name"] == "番茄鸡蛋面"

    assert captured_audit["query_excerpt"] == "image_upload"
    assert captured_audit["chat_session_id"] == 9
    assert captured_audit["chat_message_id"] == 101
    serialized_audit = json.dumps(captured_audit, ensure_ascii=False, default=str)
    assert "private-supper.jpg" not in serialized_audit
    assert "raw-image-bytes" not in serialized_audit
    assert "safe-jpeg" not in serialized_audit
