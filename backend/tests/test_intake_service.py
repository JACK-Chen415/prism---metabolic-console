from types import SimpleNamespace

import pytest

from app.models.knowledge import FallbackStatus, KnowledgeOrigin, RecommendationLevel
from app.models.meal import FoodCategory, MealType
from app.schemas.intake import IntakeConfirmItem, IntakeSource
from app.services.intake import IntakeService
from app.services.knowledge.contracts import LocalDecision, NormalizedConditions


class NoWriteDb:
    def add(self, *_):
        raise AssertionError("reevaluate_confirm_item must not add meals")

    async def flush(self):
        raise AssertionError("reevaluate_confirm_item must not flush meals")

    async def refresh(self, *_):
        raise AssertionError("reevaluate_confirm_item must not refresh meals")


class FakeMatcher:
    async def find_by_name_or_code(self, db, *, food_name=None, food_code=None):
        return SimpleNamespace(
            food_code="shrimp",
            name_zh="虾仁",
            category=FoodCategory.MEAT.value,
            common_units_json=["120g"],
            calories_per_100g=90.0,
            protein_per_100g=20.0,
            carbs_per_100g=1.0,
            fat_per_100g=1.5,
            fiber_per_100g=0.0,
            sodium_per_100g=150.0,
            purine_per_100g=137.0,
            allergen_tags_json=["虾"],
            risk_tags_json=["seafood"],
        )


class FakeKnowledgeService:
    def __init__(self):
        self.matcher = FakeMatcher()
        self.manual_restrictions_seen = None

    async def normalize_conditions(self, db, conditions):
        return NormalizedConditions(disease_codes=["gout"], allergy_terms=["虾"])

    async def evaluate_food(
        self,
        db,
        *,
        normalized,
        food_name=None,
        food_code=None,
        manual_restrictions=None,
        user=None,
    ):
        self.manual_restrictions_seen = manual_restrictions
        return LocalDecision(
            food_code=food_code,
            food_name="虾仁",
            recommendation_level=RecommendationLevel.AVOID,
            matched_disease_codes=normalized.disease_codes,
            hard_blocks=["过敏约束命中：虾", "显式忌口命中：虾"],
            risk_tags=["local_high_purine"],
            summary="虾仁命中过敏/显式忌口，本地规则直接阻断。",
            origin=KnowledgeOrigin.LOCAL_RULE,
            fallback_status=FallbackStatus.LOCAL_BLOCKED_NO_CLOUD,
            caution_note="存在绝对约束项，云端只能解释原因或提供替代建议。",
        )


def test_split_voice_segments_handles_meal_sentence() -> None:
    service = IntakeService()

    segments = service._split_voice_segments("今天早上吃了一个鸡蛋和一杯无糖豆浆、半根玉米")

    assert segments == ["一个鸡蛋", "一杯无糖豆浆", "半根玉米"]


def test_extract_amount_and_food_name() -> None:
    service = IntakeService()

    amount_text, normalized_amount, unit, food_name = service._extract_amount("半碗米饭")

    assert amount_text == "半碗"
    assert normalized_amount == 0.5
    assert unit == "碗"
    assert food_name == "米饭"


def test_infer_meal_type_and_category() -> None:
    service = IntakeService()

    meal_type = service._infer_meal_type("中午半碗米饭和一份西兰花", None)
    category = service._resolve_category("无糖豆浆", None)

    assert meal_type == MealType.LUNCH
    assert category == FoodCategory.DRINK


@pytest.mark.asyncio
async def test_reevaluate_confirm_item_recomputes_rules_and_nutrition_without_meal_write() -> None:
    knowledge_service = FakeKnowledgeService()
    service = IntakeService(knowledge_service=knowledge_service)

    item = IntakeConfirmItem(
        draft_id="draft-1",
        source=IntakeSource.PHOTO,
        meal_type=MealType.LUNCH,
        category=FoodCategory.MEAT,
        food_name="虾仁",
        food_code="shrimp",
        amount_text="200g",
        normalized_amount=200,
        unit="g",
        calories=1.0,
        allergen_tags=["shellfish"],
        risk_tags=["photo-risk"],
        warnings=["图片识别提示"],
        manual_restrictions=["虾"],
        origin=KnowledgeOrigin.CLOUD_SUPPLEMENT,
        fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
    )

    candidate = await service.reevaluate_confirm_item(
        NoWriteDb(),
        user=SimpleNamespace(id=1, nickname="tester"),
        conditions=[],
        item=item,
    )

    assert candidate.calories == 180.0
    assert candidate.protein == 40.0
    assert candidate.sodium == 300.0
    assert candidate.recommendation_level == RecommendationLevel.AVOID
    assert candidate.fallback_status == FallbackStatus.LOCAL_BLOCKED_NO_CLOUD
    assert candidate.local_rule_hit is True
    assert "过敏约束命中：虾" in candidate.warnings
    assert "显式忌口命中：虾" in candidate.warnings
    assert "图片识别提示" not in candidate.warnings
    assert "虾" in candidate.allergen_tags
    assert "local_high_purine" in candidate.risk_tags
    assert knowledge_service.manual_restrictions_seen == ["虾"]
