import re
from datetime import date, datetime, time
from types import SimpleNamespace

import pytest

from app.models.health_condition import ConditionStatus, ConditionType, HealthCondition, TrendType
from app.models.knowledge import RecommendationLevel
from app.models.meal import FoodCategory, MealType
from app.schemas.user import DailyTargets
from app.services.insights import (
    InsightCategory,
    InsightEvaluationContext,
    InsightSeverity,
    MealInsightInput,
    MealKnowledgeCaution,
    SmartInsightEvaluator,
    build_insight_context,
    evaluate_knowledge_cautions_for_meals,
)


TARGET_DATE = date(2026, 5, 24)


def _targets(
    *,
    calories: int = 2000,
    sodium: int = 2300,
    purine: int = 600,
) -> DailyTargets:
    return DailyTargets(
        calories=calories,
        recommended_calorie_target=calories,
        sodium=sodium,
        purine=purine,
    )


def _meal(
    meal_type: MealType,
    *,
    name: str = "test meal",
    meal_id: str = "meal-1",
    calories: float = 450,
    sodium: float = 300,
    purine: float = 50,
    protein: float | None = None,
    carbs: float | None = None,
    fat: float | None = None,
    fiber: float | None = None,
) -> MealInsightInput:
    return MealInsightInput(
        id=meal_id,
        name=name,
        meal_type=meal_type,
        record_date=TARGET_DATE,
        calories=calories,
        sodium=sodium,
        purine=purine,
        protein=protein,
        carbs=carbs,
        fat=fat,
        fiber=fiber,
    )


def _context(**overrides) -> InsightEvaluationContext:
    data = {
        "target_date": TARGET_DATE,
        "now": datetime(2026, 5, 24, 12, 30),
        "meals": [],
        "conditions": [],
        "daily_targets": _targets(),
        "knowledge_cautions": [],
    }
    data.update(overrides)
    return InsightEvaluationContext(**data)


def _evaluate(**overrides):
    return SmartInsightEvaluator().evaluate(_context(**overrides))


def test_missing_lunch_detected_only_inside_default_window() -> None:
    candidates = _evaluate(now=datetime(2026, 5, 24, 12, 30))

    assert [candidate.category for candidate in candidates] == [InsightCategory.MISSING_MEAL]
    assert candidates[0].meal_type == MealType.LUNCH
    assert candidates[0].severity == InsightSeverity.ADVICE
    assert "记录午餐" in candidates[0].title
    assert "现在补充这一餐" in candidates[0].message
    assert candidates[0].signals["window_start"] == "12:00"
    assert candidates[0].signals["window_end"] == "14:00"

    outside_window = _evaluate(now=datetime(2026, 5, 24, 14, 30))
    assert not outside_window

    different_date = _evaluate(
        target_date=TARGET_DATE,
        now=datetime(2026, 5, 25, 12, 30),
    )
    assert not different_date


def test_meal_window_states_use_default_windows_without_overrides() -> None:
    states = SmartInsightEvaluator().meal_window_states(_context(now=datetime(2026, 5, 24, 12, 30)))

    lunch_state = next(state for state in states if state.meal_type == MealType.LUNCH)

    assert lunch_state.starts_at == time(12, 0)
    assert lunch_state.ends_at == time(14, 0)
    assert lunch_state.is_active is True


def test_missing_meal_detection_and_states_use_overridden_windows() -> None:
    meal_windows = {
        MealType.BREAKFAST: (time(6, 0), time(7, 30)),
        MealType.LUNCH: (time(10, 30), time(11, 30)),
        MealType.DINNER: (time(17, 0), time(18, 30)),
    }
    context = _context(
        now=datetime(2026, 5, 24, 11, 0),
        meal_windows=meal_windows,
    )
    evaluator = SmartInsightEvaluator()

    states = evaluator.meal_window_states(context)
    candidates = evaluator.evaluate(context)

    lunch_state = next(state for state in states if state.meal_type == MealType.LUNCH)

    assert lunch_state.starts_at == time(10, 30)
    assert lunch_state.ends_at == time(11, 30)
    assert lunch_state.is_active is True
    assert lunch_state.has_logged_meal is False
    assert [candidate.category for candidate in candidates] == [InsightCategory.MISSING_MEAL]
    assert candidates[0].meal_type == MealType.LUNCH
    assert candidates[0].signals["window_start"] == "10:30"
    assert candidates[0].signals["window_end"] == "11:30"

    after_override_window = evaluator.evaluate(
        _context(
            now=datetime(2026, 5, 24, 12, 30),
            meal_windows=meal_windows,
        )
    )
    assert not after_override_window


def test_calorie_high_and_low_use_meal_type_bands_from_daily_target() -> None:
    candidates = _evaluate(
        now=datetime(2026, 5, 24, 15, 0),
        meals=[
            _meal(MealType.BREAKFAST, meal_id="breakfast", calories=250),
            _meal(MealType.LUNCH, meal_id="lunch", calories=950),
        ],
    )

    calorie_candidates = {candidate.key: candidate for candidate in candidates if candidate.category == InsightCategory.CALORIES}

    assert f"{TARGET_DATE}:calories:breakfast_low" in calorie_candidates
    assert calorie_candidates[f"{TARGET_DATE}:calories:breakfast_low"].severity == InsightSeverity.ADVICE
    assert "早餐可以再补足一些" in calorie_candidates[f"{TARGET_DATE}:calories:breakfast_low"].title
    assert "优质蛋白" in calorie_candidates[f"{TARGET_DATE}:calories:breakfast_low"].message
    assert calorie_candidates[f"{TARGET_DATE}:calories:breakfast_low"].signals["band_min"] == 400

    assert f"{TARGET_DATE}:calories:lunch_high" in calorie_candidates
    assert calorie_candidates[f"{TARGET_DATE}:calories:lunch_high"].severity == InsightSeverity.WARNING
    assert "午餐热量偏高" in calorie_candidates[f"{TARGET_DATE}:calories:lunch_high"].title
    assert "减少一项高热量食物" in calorie_candidates[f"{TARGET_DATE}:calories:lunch_high"].message
    assert calorie_candidates[f"{TARGET_DATE}:calories:lunch_high"].signals["band_max"] == 800


def test_sodium_excess_uses_daily_limit() -> None:
    candidates = _evaluate(
        now=datetime(2026, 5, 24, 15, 0),
        meals=[
            _meal(MealType.BREAKFAST, meal_id="breakfast", sodium=1200),
            _meal(MealType.LUNCH, meal_id="lunch", sodium=1400),
        ],
        daily_targets=_targets(sodium=2300),
    )

    sodium = [candidate for candidate in candidates if candidate.category == InsightCategory.SODIUM]

    assert len(sodium) == 1
    assert sodium[0].severity == InsightSeverity.WARNING
    assert "注意控钠" in sodium[0].title
    assert "低钠食物" in sodium[0].message
    assert sodium[0].signals == {"sodium_mg": 2600, "limit_mg": 2300}


def test_purine_excess_only_emits_for_active_gout_target_users() -> None:
    gout = HealthCondition(
        user_id=1,
        condition_code="cond-1",
        title="痛风",
        icon="monitor_heart",
        condition_type=ConditionType.CHRONIC,
        status=ConditionStatus.ACTIVE,
        trend=TrendType.STABLE,
    )
    meal = _meal(MealType.LUNCH, purine=360)

    with_gout = SmartInsightEvaluator().evaluate(
        build_insight_context(
            target_date=TARGET_DATE,
            now=datetime(2026, 5, 24, 15, 0),
            meals=[meal],
            conditions=[gout],
            daily_targets=_targets(purine=300),
        )
    )
    without_gout = _evaluate(
        now=datetime(2026, 5, 24, 15, 0),
        meals=[meal],
        daily_targets=_targets(purine=300),
    )

    purine = [candidate for candidate in with_gout if candidate.category == InsightCategory.PURINE]

    assert len(purine) == 1
    assert "降低嘌呤" in purine[0].title
    assert "高嘌呤选择" in purine[0].message
    assert purine[0].signals == {"purine_mg": 360, "limit_mg": 300}
    assert not [candidate for candidate in without_gout if candidate.category == InsightCategory.PURINE]


def test_macro_imbalance_emits_strongest_ratio_when_macro_data_is_present() -> None:
    candidates = _evaluate(
        now=datetime(2026, 5, 24, 15, 0),
        meals=[
            _meal(
                MealType.LUNCH,
                calories=650,
                protein=30,
                carbs=160,
                fat=5,
            )
        ],
    )

    macro = [candidate for candidate in candidates if candidate.category == InsightCategory.MACRO_BALANCE]

    assert len(macro) == 1
    assert macro[0].meal_type == MealType.LUNCH
    assert "增加蛋白质" in macro[0].title
    assert "优质蛋白" in macro[0].message
    assert macro[0].signals["imbalance"] == "carb_heavy"
    assert macro[0].signals["carbs_ratio"] > 0.65


def test_macro_imbalance_skips_tiny_macro_energy_intakes() -> None:
    candidates = _evaluate(
        now=datetime(2026, 5, 24, 15, 0),
        meals=[_meal(MealType.SNACK, calories=20, protein=0, carbs=5, fat=0)],
    )

    assert not [candidate for candidate in candidates if candidate.category == InsightCategory.MACRO_BALANCE]


def test_low_fiber_heuristic_only_runs_when_fiber_data_exists() -> None:
    with_fiber = _evaluate(
        now=datetime(2026, 5, 24, 15, 0),
        meals=[_meal(MealType.LUNCH, calories=550, fiber=1.2)],
    )
    without_fiber_data = _evaluate(
        now=datetime(2026, 5, 24, 15, 0),
        meals=[_meal(MealType.LUNCH, calories=550, fiber=None)],
    )

    fiber = [candidate for candidate in with_fiber if candidate.category == InsightCategory.FIBER]

    assert len(fiber) == 1
    assert fiber[0].severity == InsightSeverity.ADVICE
    assert "膳食纤维偏少" in fiber[0].title
    assert "蔬菜、豆类、水果或全谷物" in fiber[0].message
    assert fiber[0].signals["fiber_g"] == 1.2
    assert not [candidate for candidate in without_fiber_data if candidate.category == InsightCategory.FIBER]


def test_same_meal_multiple_advice_items_are_compressed_to_one_candidate() -> None:
    candidates = _evaluate(
        now=datetime(2026, 5, 24, 15, 0),
        meals=[
            _meal(
                MealType.LUNCH,
                calories=200,
                fiber=1.2,
                protein=5,
                carbs=60,
                fat=2,
            )
        ],
    )

    assert len(candidates) == 1
    assert candidates[0].category == InsightCategory.CALORIES
    assert candidates[0].severity == InsightSeverity.ADVICE


def test_same_meal_warning_suppresses_weaker_advice_items() -> None:
    candidates = _evaluate(
        now=datetime(2026, 5, 24, 15, 0),
        meals=[
            _meal(
                MealType.LUNCH,
                calories=950,
                fiber=1.2,
                protein=20,
                carbs=180,
                fat=5,
            )
        ],
    )

    assert len(candidates) == 1
    assert candidates[0].category == InsightCategory.CALORIES
    assert candidates[0].severity == InsightSeverity.WARNING


def test_global_non_severe_cap_keeps_three_highest_priority_candidates() -> None:
    candidates = _evaluate(
        now=datetime(2026, 5, 24, 21, 0),
        meals=[
            _meal(MealType.BREAKFAST, meal_id="breakfast", calories=250),
            _meal(MealType.LUNCH, meal_id="lunch", calories=400),
            _meal(MealType.DINNER, meal_id="dinner", calories=400),
            _meal(MealType.SNACK, meal_id="snack", calories=450),
        ],
    )

    assert [candidate.key for candidate in candidates] == [
        f"{TARGET_DATE}:calories:breakfast_low",
        f"{TARGET_DATE}:calories:dinner_low",
        f"{TARGET_DATE}:calories:lunch_low",
    ]
    assert all(candidate.severity == InsightSeverity.ADVICE for candidate in candidates)
    assert f"{TARGET_DATE}:calories:snack_high" not in {candidate.key for candidate in candidates}


def test_knowledge_cautions_are_aggregated_by_meal_with_highest_severity() -> None:
    candidates = _evaluate(
        now=datetime(2026, 5, 24, 15, 0),
        meals=[_meal(MealType.LUNCH, meal_id="m1"), _meal(MealType.LUNCH, meal_id="m2")],
        knowledge_cautions=[
            MealKnowledgeCaution(
                meal_id="m1",
                meal_type=MealType.LUNCH,
                food_name="虾",
                recommendation_level=RecommendationLevel.AVOID.value,
                summary="虾过敏风险",
                hard_blocks=["allergy: shrimp"],
            ),
            MealKnowledgeCaution(
                meal_id="m2",
                meal_type=MealType.LUNCH,
                food_name="啤酒",
                recommendation_level=RecommendationLevel.LIMIT.value,
                summary="痛风需限制啤酒",
            ),
            MealKnowledgeCaution(
                meal_id="m2",
                meal_type=MealType.LUNCH,
                food_name="啤酒",
                recommendation_level=RecommendationLevel.LIMIT.value,
                summary="痛风需限制啤酒",
            ),
        ],
    )

    cautions = [candidate for candidate in candidates if candidate.category == InsightCategory.CONDITION_CAUTION]

    assert len(cautions) == 1
    assert cautions[0].severity == InsightSeverity.CRITICAL
    assert "风险食物" in cautions[0].title
    assert "虾、啤酒" in cautions[0].message
    assert "避开已标记食物" in cautions[0].message
    assert cautions[0].meal_ids == ["m1", "m2"]
    assert cautions[0].signals["foods"] == ["虾", "啤酒"]
    assert cautions[0].signals["hard_blocks"] == ["allergy: shrimp"]


class FakeKnowledgeService:
    def __init__(self):
        self.manual_restrictions_seen = None

    async def evaluate_food_for_user(
        self,
        db,
        *,
        user,
        conditions,
        food_name=None,
        food_code=None,
        explicit_condition_codes=None,
        manual_restrictions=None,
    ):
        self.manual_restrictions_seen = manual_restrictions
        return SimpleNamespace(
            food_name=food_name,
            recommendation_level=RecommendationLevel.AVOID,
            matched_disease_codes=["gout"],
            hard_blocks=["allergy: peanut"],
            summary="avoid peanut",
            conflict_note="peanut allergy conflict",
            caution_note=None,
        )


@pytest.mark.asyncio
async def test_knowledge_service_adapter_returns_caution_contracts_and_allergy_restrictions() -> None:
    service = FakeKnowledgeService()
    allergy = HealthCondition(
        user_id=1,
        condition_code="peanut",
        title="Peanut",
        icon="allergy",
        condition_type=ConditionType.ALLERGY,
        status=ConditionStatus.ACTIVE,
        trend=TrendType.STABLE,
    )

    cautions = await evaluate_knowledge_cautions_for_meals(
        object(),
        user=SimpleNamespace(id=1),
        conditions=[allergy],
        meals=[_meal(MealType.DINNER, name="peanut sauce", meal_id="dinner")],
        knowledge_service=service,
    )

    assert service.manual_restrictions_seen == ["Peanut", "peanut"]
    assert len(cautions) == 1
    assert cautions[0].meal_id == "dinner"
    assert cautions[0].meal_type == MealType.DINNER
    assert cautions[0].recommendation_level == RecommendationLevel.AVOID.value
    assert cautions[0].hard_blocks == ["allergy: peanut"]


def test_positive_feedback_only_when_no_stronger_candidate_exists() -> None:
    positive = _evaluate(
        now=datetime(2026, 5, 24, 15, 0),
        meals=[
            _meal(
                MealType.LUNCH,
                calories=700,
                sodium=300,
                purine=50,
                protein=35,
                carbs=80,
                fat=18,
                fiber=8,
            )
        ],
    )
    warning = _evaluate(
        now=datetime(2026, 5, 24, 15, 0),
        meals=[_meal(MealType.LUNCH, calories=950)],
    )

    assert [candidate.category for candidate in positive] == [InsightCategory.POSITIVE_FEEDBACK]
    assert positive[0].severity == InsightSeverity.POSITIVE
    assert "继续保持" in positive[0].title
    assert "类似份量" in positive[0].message
    assert not [candidate for candidate in warning if candidate.category == InsightCategory.POSITIVE_FEEDBACK]


def test_generated_smart_insight_copy_uses_simplified_chinese() -> None:
    candidates = [
        *_evaluate(now=datetime(2026, 5, 24, 12, 30)),
        *_evaluate(
            now=datetime(2026, 5, 24, 15, 0),
            meals=[_meal(MealType.LUNCH, calories=950, sodium=2600)],
        ),
        *_evaluate(
            now=datetime(2026, 5, 24, 15, 0),
            meals=[_meal(MealType.DINNER, calories=700, protein=5, carbs=120, fat=5)],
        ),
    ]

    legacy_fragments = ["Next step", "Scale back", "Lower sodium", "You've logged", "This meal"]
    assert candidates
    for candidate in candidates:
        combined = f"{candidate.title} {candidate.message}"
        assert re.search(r"[\u4e00-\u9fff]", candidate.title)
        assert re.search(r"[\u4e00-\u9fff]", candidate.message)
        for fragment in legacy_fragments:
            assert fragment not in combined
