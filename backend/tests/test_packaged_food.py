from types import SimpleNamespace

import pytest

from app.api.routes import knowledge as knowledge_route
from app.models.knowledge import FallbackStatus, KnowledgeOrigin, RecommendationLevel
from app.schemas.knowledge import PackagedFoodBarcodeLookupRequest
from app.services.knowledge.contracts import LocalDecision, NormalizedConditions
from app.services.packaged_food import (
    MockPackagedFoodProvider,
    PackagedFoodLookupService,
    build_manual_label_candidate,
    normalize_barcode,
)


class _ScalarResult:
    def scalars(self):
        return self

    def all(self):
        return []

    def scalar_one_or_none(self):
        return None


class _FakeDb:
    async def execute(self, _statement):
        return _ScalarResult()


class _FakeKnowledgeService:
    async def normalize_conditions(self, db, conditions, explicit_condition_codes=None):
        del db, conditions, explicit_condition_codes
        return NormalizedConditions(
            disease_codes=[],
            allergy_terms=["dairy", "牛奶"],
            unmapped_conditions=[],
        )

    async def evaluate_food(self, db, *, normalized, food_name=None, food_code=None, manual_restrictions=None, user=None):
        del db, normalized, food_code, manual_restrictions, user
        return LocalDecision(
            food_name=food_name or "未知包装食品",
            summary="本地知识库未命中完整包装食品规则。",
            origin=KnowledgeOrigin.LOCAL_KNOWLEDGE,
            fallback_status=FallbackStatus.LOCAL_PARTIAL_ALLOW_CLOUD,
        )


def test_normalize_barcode_strips_separators_and_rejects_non_numeric():
    assert normalize_barcode(" 6901-2345 67892 ") == "6901234567892"
    with pytest.raises(ValueError):
        normalize_barcode("6901<script>")


def test_manual_label_candidate_infers_risk_and_allergen_tags():
    candidate = build_manual_label_candidate(
        product_name="高钠酱油味饼干",
        brand="Prism Test",
        barcode="6970000000027",
        category="SNACK",
        serving_size="30g",
        serving_size_g=30,
        calories_per_100g=480,
        protein_per_100g=8,
        carbs_per_100g=60,
        fat_per_100g=20,
        fiber_per_100g=2,
        sodium_per_100g=980,
        sugar_per_100g=18,
        purine_per_100g=20,
        ingredients=["小麦粉", "酱油粉", "食用盐"],
        allergen_tags=[],
        risk_tags=[],
    )

    assert candidate.barcode_last4 == "0027"
    assert "wheat" in candidate.allergen_tags
    assert "soy" in candidate.allergen_tags
    assert "high_sodium" in candidate.risk_tags
    assert "high_sugar" in candidate.risk_tags
    assert "high_fat" in candidate.risk_tags
    assert candidate.nutrition_review_status == "NEEDS_USER_REVIEW"


@pytest.mark.asyncio
async def test_packaged_food_service_blocks_allergy_before_cloud_relaxation():
    service = PackagedFoodLookupService(
        provider=MockPackagedFoodProvider(),
        knowledge_service=_FakeKnowledgeService(),
    )
    candidate = (await service.provider.lookup_barcode("6901234567892"))[0]

    decision = await service.evaluate_candidate(
        _FakeDb(),
        user=SimpleNamespace(id=1),
        conditions=[],
        candidate=candidate,
    )

    assert decision.recommendation_level == RecommendationLevel.AVOID
    assert decision.fallback_status == FallbackStatus.LOCAL_BLOCKED_NO_CLOUD
    assert decision.hard_blocks
    assert "云端不能放宽" in (decision.caution_note or "")


@pytest.mark.asyncio
async def test_barcode_route_redacts_full_barcode_and_requires_review(monkeypatch):
    audit_calls = []

    async def fake_write_knowledge_audit_log(db, **kwargs):
        del db
        audit_calls.append(kwargs)
        return SimpleNamespace(id=1)

    monkeypatch.setattr(knowledge_route, "write_knowledge_audit_log", fake_write_knowledge_audit_log)

    response = await knowledge_route.lookup_packaged_food_barcode(
        PackagedFoodBarcodeLookupRequest(barcode="6901234567892"),
        current_user=SimpleNamespace(id=7),
        db=_FakeDb(),
    )

    serialized = response.model_dump_json()
    assert response.matched is True
    assert response.barcode_last4 == "7892"
    assert response.candidates[0].review_required is True
    assert "mock_or_planned_provider" in response.candidates[0].review_reasons
    assert "6901234567892" not in serialized
    assert audit_calls[0]["query_excerpt"] == "barcode_last4:7892"
    assert "6901234567892" not in str(audit_calls[0])
