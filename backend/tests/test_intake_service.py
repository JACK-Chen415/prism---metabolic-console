from types import SimpleNamespace

import pytest

from app.models.health_condition import ConditionStatus
from app.models.knowledge import FallbackStatus, KnowledgeOrigin, RecommendationLevel
from app.models.meal import FoodCategory, MealType
from app.schemas.intake import IntakeConfirmItem, IntakeConfirmRequest, IntakeParseStatus, IntakeSource, TextParseRequest
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


@pytest.mark.asyncio
async def test_confirm_rejects_low_confidence_candidate_without_review_confirmation() -> None:
    service = IntakeService(knowledge_service=FakeKnowledgeService())
    item = IntakeConfirmItem(
        draft_id="draft-review-1",
        source=IntakeSource.PHOTO,
        meal_type=MealType.LUNCH,
        category=FoodCategory.MEAT,
        food_name="虾仁",
        food_code="shrimp",
        amount_text="1份",
        normalized_amount=None,
        unit="份",
        ingredients=[],
        cooking_method=None,
        seasonings=[],
        confidence=0.2,
        origin=KnowledgeOrigin.CLOUD_SUPPLEMENT,
        fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
    )

    result = await service.confirm(
        FakeAuditDb(),
        user=SimpleNamespace(id=1, nickname="tester"),
        conditions=[],
        data=IntakeConfirmRequest(
            source=IntakeSource.PHOTO,
            raw_summary="photo candidate",
            candidates=[item],
        ),
    )

    assert result.meals == []
    assert result.meal_ids == []
    assert len(result.failed_items) == 1
    assert result.failed_items[0].draft_id == "draft-review-1"
    assert "候选需要人工复核" in result.failed_items[0].reason
    assert "低置信度" in result.failed_items[0].reason


@pytest.mark.asyncio
async def test_meal_from_confirm_item_persists_review_metadata_when_confirmed() -> None:
    service = IntakeService(knowledge_service=FakeKnowledgeService())
    item = IntakeConfirmItem(
        draft_id="draft-review-2",
        source=IntakeSource.PHOTO,
        meal_type=MealType.LUNCH,
        category=FoodCategory.MEAT,
        food_name="虾仁",
        food_code="shrimp",
        amount_text="120g",
        normalized_amount=120,
        unit="g",
        ingredients=["虾仁"],
        cooking_method="清炒",
        seasonings=["少量盐"],
        confidence=0.2,
        origin=KnowledgeOrigin.CLOUD_SUPPLEMENT,
        fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
        review_confirmed=True,
    )

    meal, candidate = await service._meal_from_confirm_item(
        NoWriteDb(),
        user=SimpleNamespace(id=1, nickname="tester"),
        normalized=NormalizedConditions(disease_codes=["gout"], allergy_terms=["虾"]),
        item=item,
        record_date=__import__("datetime").date(2026, 6, 6),
        raw_input_text="",
        raw_summary="",
    )

    assert candidate.review_required is True
    assert candidate.review_confirmed is True
    assert "low_confidence" in candidate.review_reasons
    assert meal.recognition_meta_json["review_required"] is True
    assert meal.recognition_meta_json["review_confirmed"] is True
    assert "low_confidence" in meal.recognition_meta_json["review_reasons"]
    assert meal.recognition_meta_json["review_threshold"] == 0.55

@pytest.mark.asyncio
async def test_suggest_candidate_alternatives_filters_hard_blocks_without_writing_meals() -> None:
    class AlternativeMatcher:
        def __init__(self):
            self.foods = [
                SimpleNamespace(
                    food_code="shrimp",
                    name_zh="虾仁",
                    category=FoodCategory.MEAT.value,
                    calories_per_100g=90.0,
                    sodium_per_100g=150.0,
                    purine_per_100g=137.0,
                    allergen_tags_json=["虾"],
                    risk_tags_json=["seafood"],
                ),
                SimpleNamespace(
                    food_code="crab",
                    name_zh="螃蟹",
                    category=FoodCategory.MEAT.value,
                    calories_per_100g=97.0,
                    sodium_per_100g=260.0,
                    purine_per_100g=152.0,
                    allergen_tags_json=["蟹"],
                    risk_tags_json=["seafood"],
                ),
                SimpleNamespace(
                    food_code="steamed_chicken",
                    name_zh="清蒸鸡胸肉",
                    category=FoodCategory.MEAT.value,
                    calories_per_100g=165.0,
                    sodium_per_100g=70.0,
                    purine_per_100g=80.0,
                    allergen_tags_json=[],
                    risk_tags_json=[],
                ),
                SimpleNamespace(
                    food_code="tofu",
                    name_zh="北豆腐",
                    category=FoodCategory.MEAT.value,
                    calories_per_100g=82.0,
                    sodium_per_100g=7.0,
                    purine_per_100g=25.0,
                    allergen_tags_json=["soy"],
                    risk_tags_json=[],
                ),
            ]

        async def find_by_name_or_code(self, db, *, food_name=None, food_code=None):
            for food in self.foods:
                if food.food_code == food_code or food.name_zh == food_name:
                    return food
            return None

        async def list_enabled_foods(self, db):
            return self.foods

    class AlternativeKnowledgeService:
        def __init__(self):
            self.matcher = AlternativeMatcher()

        async def normalize_conditions(self, db, conditions):
            return NormalizedConditions(disease_codes=["gout"], allergy_terms=["虾", "蟹"])

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
            if food_code in {"shrimp", "crab"}:
                return LocalDecision(
                    food_code=food_code,
                    food_name="虾蟹",
                    recommendation_level=RecommendationLevel.AVOID,
                    matched_disease_codes=normalized.disease_codes,
                    hard_blocks=["过敏约束命中"],
                    risk_tags=["seafood"],
                    summary="命中过敏或显式忌口，本地规则阻断。",
                    origin=KnowledgeOrigin.LOCAL_RULE,
                    fallback_status=FallbackStatus.LOCAL_BLOCKED_NO_CLOUD,
                )
            return LocalDecision(
                food_code=food_code,
                food_name="替代项",
                recommendation_level=RecommendationLevel.RECOMMEND if food_code == "tofu" else RecommendationLevel.MODERATE,
                matched_disease_codes=normalized.disease_codes,
                hard_blocks=[],
                risk_tags=[],
                summary="本地规则未发现当前档案下的绝对阻断项。",
                origin=KnowledgeOrigin.LOCAL_RULE,
                fallback_status=FallbackStatus.LOCAL_COMPLETE,
            )

    service = IntakeService(knowledge_service=AlternativeKnowledgeService())
    item = IntakeConfirmItem(
        draft_id="draft-alt-1",
        source=IntakeSource.PHOTO,
        meal_type=MealType.LUNCH,
        category=FoodCategory.MEAT,
        food_name="虾仁",
        food_code="shrimp",
        amount_text="100g",
        normalized_amount=100,
        unit="g",
        ingredients=["虾仁"],
        cooking_method="清蒸",
        seasonings=[],
        manual_restrictions=["虾"],
        origin=KnowledgeOrigin.CLOUD_SUPPLEMENT,
        fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
    )

    response = await service.suggest_candidate_alternatives(
        NoWriteDb(),
        user=SimpleNamespace(id=1, nickname="tester"),
        conditions=[],
        item=item,
        limit=3,
    )

    assert response.draft_id == "draft-alt-1"
    names = [item.food_name for item in response.alternatives]
    assert "虾仁" not in names
    assert "螃蟹" not in names
    assert names == ["北豆腐", "清蒸鸡胸肉"]
    assert all(item.recommendation_level in {RecommendationLevel.RECOMMEND, RecommendationLevel.MODERATE} for item in response.alternatives)
    assert any("不作诊断" in note for note in response.notes)
    assert all("本地规则" in item.reason for item in response.alternatives)

@pytest.mark.asyncio
async def test_preview_confirm_impact_projects_targets_without_writing_meals() -> None:
    class FakeSummaryResult:
        def one(self):
            return SimpleNamespace(calories=1000.0, sodium=1200.0, purine=250.0, count=2)

    class PreviewDb(NoWriteDb):
        async def execute(self, *_):
            return FakeSummaryResult()

    service = IntakeService(knowledge_service=FakeKnowledgeService())
    response = await service.preview_confirm_impact(
        PreviewDb(),
        user=SimpleNamespace(id=1, gender="FEMALE", age=35, height=160, weight=60),
        conditions=[
            SimpleNamespace(status=ConditionStatus.ACTIVE, condition_code="hypertension", title="高血压"),
            SimpleNamespace(status=ConditionStatus.ACTIVE, condition_code="gout", title="痛风"),
        ],
        data=__import__("app.schemas.intake", fromlist=["IntakeConfirmPreviewRequest"]).IntakeConfirmPreviewRequest(
            record_date=__import__("datetime").date(2026, 6, 7),
            candidates=[
                IntakeConfirmItem(
                    draft_id="draft-preview-1",
                    source=IntakeSource.PHOTO,
                    meal_type=MealType.LUNCH,
                    category=FoodCategory.MEAT,
                    food_name="牛肉面",
                    amount_text="1碗",
                    normalized_amount=1,
                    unit="碗",
                    calories=700,
                    sodium=500,
                    purine=80,
                    origin=KnowledgeOrigin.CLOUD_SUPPLEMENT,
                    fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
                ),
            ],
        ),
    )

    metrics = {metric.key: metric for metric in response.metrics}
    assert response.will_create_meal is False
    assert response.meal_count == 2
    assert metrics["calories"].projected == 1700.0
    assert metrics["sodium"].target == 1500.0
    assert metrics["sodium"].status == "over_limit"
    assert metrics["purine"].target == 300.0
    assert metrics["purine"].status == "over_limit"
    assert any("不会创建饮食记录" in note for note in response.notes)
    assert any("不作诊断" in note for note in response.notes)
