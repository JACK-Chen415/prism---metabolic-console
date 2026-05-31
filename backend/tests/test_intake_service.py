from types import SimpleNamespace

import pytest

from app.models.knowledge import FallbackStatus, KnowledgeOrigin, RecommendationLevel
from app.models.meal import FoodCategory, MealType
from app.schemas.intake import IntakeConfirmItem, IntakeParseStatus, IntakeSource, TextParseRequest
from app.services.intake import IntakeService
from app.services.knowledge.contracts import LocalDecision, NormalizedConditions


class NoWriteDb:
    def add(self, *_):
        raise AssertionError("reevaluate_confirm_item must not add meals")

    async def flush(self):
        raise AssertionError("reevaluate_confirm_item must not flush meals")

    async def refresh(self, *_):
        raise AssertionError("reevaluate_confirm_item must not refresh meals")


class FakeAuditDb:
    def add(self, *_):
        return None

    async def flush(self):
        return None


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


def test_extract_amount_supports_fuzzy_small_bowl() -> None:
    service = IntakeService()

    amount_text, normalized_amount, unit, food_name = service._extract_amount("一小碗米饭")

    assert amount_text == "一小碗"
    assert normalized_amount == 0.75
    assert unit == "碗"
    assert food_name == "米饭"


def test_infer_meal_type_and_category() -> None:
    service = IntakeService()

    meal_type = service._infer_meal_type("中午半碗米饭和一份西兰花", None)
    category = service._resolve_category("无糖豆浆", None)

    assert meal_type == MealType.LUNCH
    assert category == FoodCategory.DRINK


@pytest.mark.asyncio
async def test_parse_text_ready_returns_ai_quick_log_candidates() -> None:
    service = IntakeService(knowledge_service=FakeKnowledgeService())

    result = await service.parse_text(
        FakeAuditDb(),
        user=SimpleNamespace(id=1, nickname="tester"),
        conditions=[],
        data=TextParseRequest(text="今天早上吃了一个鸡蛋和一杯无糖豆浆"),
    )

    assert result.status == IntakeParseStatus.READY
    assert result.source == IntakeSource.AI_QUICK_LOG
    assert result.candidates
    assert all(candidate.source == IntakeSource.AI_QUICK_LOG for candidate in result.candidates)


@pytest.mark.asyncio
async def test_parse_text_needs_clarification_when_foods_missing() -> None:
    service = IntakeService(knowledge_service=FakeKnowledgeService())

    result = await service.parse_text(
        FakeAuditDb(),
        user=SimpleNamespace(id=1, nickname="tester"),
        conditions=[],
        data=TextParseRequest(text="帮我记录早餐"),
    )

    assert result.status == IntakeParseStatus.NEEDS_CLARIFICATION
    assert "foods" in result.missing_fields
    assert result.follow_up_prompt


@pytest.mark.asyncio
async def test_parse_text_refuses_non_log_text() -> None:
    service = IntakeService(knowledge_service=FakeKnowledgeService())

    result = await service.parse_text(
        FakeAuditDb(),
        user=SimpleNamespace(id=1, nickname="tester"),
        conditions=[],
        data=TextParseRequest(text="痛风能不能吃排骨？"),
    )

    assert result.status == IntakeParseStatus.REFUSED
    assert result.refusal_reason
    assert result.candidates == []


@pytest.mark.asyncio
async def test_parse_text_context_follow_up_completes_prior_meal_log() -> None:
    service = IntakeService(knowledge_service=FakeKnowledgeService())

    result = await service.parse_text(
        FakeAuditDb(),
        user=SimpleNamespace(id=1, nickname="tester"),
        conditions=[],
        data=TextParseRequest(
            text="一小碗，有点咸",
            context_text="帮我记录午餐，番茄鸡蛋面",
        ),
    )

    assert result.status == IntakeParseStatus.READY
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.food_name == "番茄鸡蛋面"
    assert candidate.amount_text == "一小碗"
    assert candidate.normalized_amount == 0.75
    assert candidate.unit == "碗"
    assert candidate.note == "有点咸"
    assert "amount" in candidate.estimated_fields
    assert any("上下文补全" in note for note in candidate.estimated_notes)


@pytest.mark.asyncio
async def test_parse_text_preserves_taste_note_in_candidate() -> None:
    service = IntakeService(knowledge_service=FakeKnowledgeService())

    result = await service.parse_text(
        FakeAuditDb(),
        user=SimpleNamespace(id=1, nickname="tester"),
        conditions=[],
        data=TextParseRequest(text="晚餐喝了一杯豆浆，清淡"),
    )

    assert result.status == IntakeParseStatus.READY
    assert result.candidates
    candidate = result.candidates[0]
    assert candidate.note == "清淡"
    assert candidate.sodium is not None
    assert not any("mg" in note for note in candidate.estimated_notes)


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
        ingredients=["虾仁"],
        cooking_method="油炸",
        seasonings=["酱油"],
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

    assert candidate.calories == 260.0
    assert candidate.protein == 40.0
    assert candidate.fat == 11.0
    assert candidate.sodium == 650.0
    assert candidate.recommendation_level == RecommendationLevel.AVOID
    assert candidate.fallback_status == FallbackStatus.LOCAL_BLOCKED_NO_CLOUD
    assert candidate.local_rule_hit is True
    assert "过敏约束命中：虾" in candidate.warnings
    assert "显式忌口命中：虾" in candidate.warnings
    assert "配料或调料包含高钠项" in "；".join(candidate.warnings)
    assert "烹饪方式包含高油脂做法" in "；".join(candidate.warnings)
    assert "虾" in candidate.allergen_tags
    assert "soy" in candidate.allergen_tags
    assert "high_sodium" in candidate.risk_tags
    assert "high_fat" in candidate.risk_tags
    assert "soy" in candidate.risk_tags
    assert "local_high_purine" in candidate.risk_tags
    assert candidate.ingredients == ["虾仁"]
    assert candidate.cooking_method == "油炸"
    assert candidate.seasonings == ["酱油"]
    assert knowledge_service.manual_restrictions_seen == ["虾"]


@pytest.mark.asyncio
async def test_reevaluate_confirm_item_marks_prep_allergens_as_local_blocks() -> None:
    class NoMatchMatcher:
        async def find_by_name_or_code(self, db, *, food_name=None, food_code=None):
            return None

    class PrepKnowledgeService:
        def __init__(self):
            self.matcher = NoMatchMatcher()
            self.manual_restrictions_seen = None

        async def normalize_conditions(self, db, conditions):
            return NormalizedConditions(disease_codes=["hypertension"], allergy_terms=["花生"])

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
                food_name=food_name or "未知食物",
                recommendation_level=RecommendationLevel.MODERATE,
                matched_disease_codes=normalized.disease_codes,
                hard_blocks=[],
                risk_tags=[],
                summary="本地规则保守通过。",
                origin=KnowledgeOrigin.LOCAL_KNOWLEDGE,
                fallback_status=FallbackStatus.LOCAL_COMPLETE,
            )

    service = IntakeService(knowledge_service=PrepKnowledgeService())

    item = IntakeConfirmItem(
        draft_id="draft-2",
        source=IntakeSource.MANUAL,
        meal_type=MealType.DINNER,
        category=FoodCategory.MEAT,
        food_name="鸡丁",
        amount_text="100g",
        normalized_amount=100,
        unit="g",
        ingredients=["鸡肉", "花生碎"],
        cooking_method="油炸",
        seasonings=["白糖", "酱油"],
        calories=None,
        protein=None,
        carbs=None,
        fat=None,
        fiber=None,
        sodium=None,
        sugar=None,
        purine=None,
        allergen_tags=[],
        risk_tags=[],
        warnings=[],
        manual_restrictions=[],
        origin=KnowledgeOrigin.LOCAL_KNOWLEDGE,
        fallback_status=FallbackStatus.LOCAL_COMPLETE,
    )

    candidate = await service.reevaluate_confirm_item(
        NoWriteDb(),
        user=SimpleNamespace(id=1, nickname="tester"),
        conditions=[],
        item=item,
    )

    assert candidate.recommendation_level == RecommendationLevel.AVOID
    assert candidate.fallback_status == FallbackStatus.LOCAL_BLOCKED_NO_CLOUD
    assert candidate.local_rule_hit is True
    assert candidate.calories == 285.0
    assert candidate.fat == 16.0
    assert candidate.sodium == 430.0
    assert candidate.sugar == 10.0
    assert "peanut" in candidate.allergen_tags
    assert "soy" in candidate.allergen_tags
    assert "high_sodium" in candidate.risk_tags
    assert "high_sugar" in candidate.risk_tags
    assert "high_fat" in candidate.risk_tags
    assert "过敏约束命中：花生" in candidate.warnings
