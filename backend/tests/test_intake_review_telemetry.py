import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.routes import intake as intake_route
from app.core.security import hash_sensitive_value
from app.models.feedback import AIFeedback, AIFeedbackType
from app.models.intake_telemetry import IntakeReviewTelemetrySnapshot
from app.schemas.intake import IntakeCandidateFeedbackRequest, IntakeReviewTelemetryRequest


def test_intake_review_telemetry_schema_rejects_raw_or_unknown_distribution_keys() -> None:
    with pytest.raises(ValidationError):
        IntakeReviewTelemetryRequest(
            total_count=1,
            pending_review_count=1,
            source_counts={"photo": 1, "raw_food_name": 1},
            status_counts={"PENDING_REVIEW": 1},
        )

    with pytest.raises(ValidationError):
        IntakeReviewTelemetryRequest(
            total_count=1,
            pending_review_count=1,
            source_counts={"photo": 1},
            status_counts={"PENDING_REVIEW": 1, "CONFIRMED": 1},
        )


class _FakeTelemetryDb:
    def __init__(self):
        self.added = []
        self.flush_count = 0
        self.refresh_count = 0

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flush_count += 1
        for item in self.added:
            if isinstance(item, IntakeReviewTelemetrySnapshot):
                item.id = item.id or 11
                item.created_at = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)
                item.generated_at = item.generated_at or item.created_at
            if isinstance(item, AIFeedback):
                item.id = item.id or 21
                item.created_at = item.created_at or datetime(2026, 6, 7, 12, 5, tzinfo=timezone.utc)

    async def refresh(self, item):
        self.refresh_count += 1


@pytest.mark.asyncio
async def test_submit_review_telemetry_stores_only_aggregate_counts_and_audits(monkeypatch) -> None:
    audit_calls = []

    async def fake_audit_security_event(*args, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(intake_route, "audit_security_event", fake_audit_security_event)

    db = _FakeTelemetryDb()
    payload = IntakeReviewTelemetryRequest(
        total_count=3,
        pending_review_count=2,
        in_review_count=1,
        low_confidence_count=2,
        high_risk_count=1,
        hard_block_count=1,
        source_counts={"photo": 2, "voice": 1},
        status_counts={"PENDING_REVIEW": 2, "IN_REVIEW": 1},
    )
    raw_candidate_text = "虾蟹过敏 raw candidate should never appear"

    response = await intake_route.submit_review_telemetry(
        data=payload,
        request=None,
        current_user=SimpleNamespace(id=7, phone="13800138000"),
        db=db,
    )
    serialized = json.dumps(
        {
            "response": response.model_dump(mode="json"),
            "audit": audit_calls,
            "db": [
                {
                    "source_counts": item.source_counts_json,
                    "status_counts": item.status_counts_json,
                }
                for item in db.added
            ],
        },
        ensure_ascii=False,
    )

    assert response.id == 11
    assert response.total_count == 3
    assert response.source_counts == {"photo": 2, "voice": 1}
    assert db.flush_count == 1
    assert db.refresh_count == 1
    assert isinstance(db.added[0], IntakeReviewTelemetrySnapshot)
    assert audit_calls[0]["event_type"] == "intake.review.telemetry.submit"
    assert audit_calls[0]["metadata"]["pending_review_count"] == 2
    assert raw_candidate_text not in serialized
    assert "food_name" not in serialized
    assert "raw candidate" not in serialized

def test_intake_candidate_feedback_schema_only_allows_correction_backlog_types() -> None:
    for allowed in [
        AIFeedbackType.RECOGNITION_CORRECTION,
        AIFeedbackType.CORRECTION,
        AIFeedbackType.KNOWLEDGE_GAP,
    ]:
        payload = IntakeCandidateFeedbackRequest(
            draft_id="draft-1",
            source="photo",
            feedback_type=allowed,
            correction_text="候选估算需要纠正",
        )
        assert payload.feedback_type == allowed

    for rejected in ["helpful", "not_helpful", "unsafe"]:
        with pytest.raises(ValidationError):
            IntakeCandidateFeedbackRequest(
                draft_id="draft-1",
                source="photo",
                feedback_type=rejected,
                correction_text="候选估算需要纠正",
            )


@pytest.mark.asyncio
async def test_submit_candidate_feedback_hashes_raw_text_and_filters_metadata(monkeypatch) -> None:
    audit_calls = []

    async def fake_audit_security_event(*args, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(intake_route, "audit_security_event", fake_audit_security_event)

    db = _FakeTelemetryDb()
    raw_correction = "识别成虾仁炒饭但用户认为不是；这里包含隐私候选内容，不能落库。"
    payload = IntakeCandidateFeedbackRequest(
        draft_id="local-draft-secret-1",
        source="photo",
        feedback_type=AIFeedbackType.RECOGNITION_CORRECTION,
        rating=1,
        tags=[" Recognition Error ", "recognition error", "安全规则"],
        correction_text=raw_correction,
        metadata={
            "source": "photo",
            "surface": "intake_confirmation",
            "recommendation_level": "AVOID",
            "candidate_count": 2,
            "low_confidence_count": 1,
            "high_risk_count": 1,
            "hard_block_count": 1,
            "risk_tag_count": 3,
            "allergen_tag_count": 2,
            "warning_count": 4,
            "food_name": "虾仁炒饭",
            "note": "raw user note",
            "raw_summary": "raw ai summary",
            "image": "base64-private-image",
            "ingredients": ["虾仁"],
            "seasonings": ["酱油"],
            "cooking_method": "炒",
        },
    )

    response = await intake_route.submit_candidate_feedback(
        data=payload,
        request=None,
        current_user=SimpleNamespace(id=7, phone="13800138000"),
        db=db,
    )
    feedback = db.added[0]
    serialized = json.dumps(
        {
            "response": response.model_dump(mode="json"),
            "audit": audit_calls,
            "feedback": {
                "feedback_type": feedback.feedback_type.value,
                "rating": feedback.rating,
                "tags": feedback.tags_json,
                "correction_text": feedback.correction_text,
                "correction_text_hash": feedback.correction_text_hash,
                "metadata": feedback.metadata_json,
            },
        },
        ensure_ascii=False,
    )

    assert response.id == 21
    assert response.feedback_type == AIFeedbackType.RECOGNITION_CORRECTION
    assert response.has_correction is True
    assert isinstance(feedback, AIFeedback)
    assert feedback.correction_text == "intake_candidate_correction_submitted"
    assert feedback.correction_text_hash == hash_sensitive_value(raw_correction)
    assert feedback.tags_json[:2] == ["intake_candidate", "recognition_error"]
    assert feedback.metadata_json["draft_id_hash"] == hash_sensitive_value("local-draft-secret-1")
    assert feedback.metadata_json["recommendation_level"] == "AVOID"
    assert audit_calls[0]["event_type"] == "intake.candidate.feedback.create"
    assert audit_calls[0]["metadata"]["correction_text_hash"] == hash_sensitive_value(raw_correction)
    for forbidden in [
        raw_correction,
        "虾仁炒饭",
        "raw user note",
        "raw ai summary",
        "base64-private-image",
        "food_name",
        "raw_summary",
        "image",
        "ingredients",
        "seasonings",
        "cooking_method",
    ]:
        assert forbidden not in serialized

@pytest.mark.asyncio
async def test_submit_candidate_feedback_drops_raw_values_inside_tags_and_allowlisted_metadata(monkeypatch) -> None:
    audit_calls = []

    async def fake_audit_security_event(*args, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(intake_route, "audit_security_event", fake_audit_security_event)

    db = _FakeTelemetryDb()
    raw_candidate_value = "虾仁炒饭 raw candidate note should not be stored"
    payload = IntakeCandidateFeedbackRequest(
        draft_id="local-draft-secret-2",
        source="photo",
        feedback_type=AIFeedbackType.RECOGNITION_CORRECTION,
        rating=1,
        tags=[raw_candidate_value, "photo", "low_confidence"],
        correction_text=raw_candidate_value,
        metadata={
            "recommendation_level": raw_candidate_value,
            "candidate_count": raw_candidate_value,
            "low_confidence_count": True,
            "high_risk_count": 9999,
            "hard_block_count": 1.8,
        },
    )

    response = await intake_route.submit_candidate_feedback(
        data=payload,
        request=None,
        current_user=SimpleNamespace(id=7, phone="13800138000"),
        db=db,
    )
    feedback = db.added[0]
    serialized = json.dumps(
        {
            "response": response.model_dump(mode="json"),
            "audit": audit_calls,
            "feedback": {
                "tags": feedback.tags_json,
                "correction_text": feedback.correction_text,
                "correction_text_hash": feedback.correction_text_hash,
                "metadata": feedback.metadata_json,
            },
        },
        ensure_ascii=False,
    )

    assert feedback.tags_json == ["intake_candidate", "photo", "low_confidence"]
    assert feedback.metadata_json["draft_id_hash"] == hash_sensitive_value("local-draft-secret-2")
    assert "recommendation_level" not in feedback.metadata_json
    assert "candidate_count" not in feedback.metadata_json
    assert "low_confidence_count" not in feedback.metadata_json
    assert feedback.metadata_json["high_risk_count"] == 5000
    assert feedback.metadata_json["hard_block_count"] == 1
    assert feedback.correction_text_hash == hash_sensitive_value(raw_candidate_value)
    assert raw_candidate_value not in serialized

