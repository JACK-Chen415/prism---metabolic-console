"""Single source for daily nutrition target calculation."""

from collections.abc import Iterable
from typing import Optional

from app.models.health_condition import ConditionStatus, HealthCondition
from app.models.user import Gender, User
from app.schemas.user import CalorieRange, DailyTargets
from app.services.knowledge.normalizer import match_default_disease_code


DEFAULT_ACTIVITY_FACTOR = 1.375
BMR_RANGE_RATIO = 0.05
CALORIE_TARGET_STEP = 10
SAFETY_CALORIE_FLOORS = {
    "MALE": 1500,
    "FEMALE": 1200,
    "UNKNOWN": 1300,
}

DEFAULT_DAILY_TARGETS = DailyTargets(
    calories=0,
    sodium=2300,
    purine=600,
    activity_factor=DEFAULT_ACTIVITY_FACTOR,
    recommended_calorie_target=0,
    target_strategy="insufficient_data",
    target_explanation="请先在设置中完善身高、体重、年龄、性别，以获得更准确估算。",
    is_estimated=True,
    has_complete_profile=False,
)


def _enum_value(value) -> Optional[str]:
    if value is None:
        return None
    return getattr(value, "value", value)


def _round_to_step(value: float, step: int = CALORIE_TARGET_STEP) -> int:
    return int(round(value / step) * step)


def calculate_bmi(user: User) -> Optional[float]:
    if not user.height or not user.weight:
        return None
    return round(user.weight / (user.height / 100) ** 2, 1)


def _bmi_category(bmi: Optional[float]) -> Optional[str]:
    if bmi is None:
        return None
    if bmi < 18.5:
        return "underweight"
    if bmi < 24:
        return "normal"
    if bmi < 28:
        return "overweight"
    return "obese"


def _bmr_for_gender(user: User, gender: str) -> float:
    base = (10 * user.weight) + (6.25 * user.height) - (5 * user.age)
    return base + (5 if gender == "MALE" else -161)


def _calculate_bmr_and_range(user: User) -> tuple[Optional[int], Optional[CalorieRange]]:
    if not all([user.age, user.height, user.weight]):
        return None, None

    gender = _enum_value(user.gender)
    if gender in {"MALE", "FEMALE"}:
        bmr = _bmr_for_gender(user, gender)
        bmr_value = round(bmr)
        return bmr_value, CalorieRange(
            min=round(bmr * (1 - BMR_RANGE_RATIO)),
            max=round(bmr * (1 + BMR_RANGE_RATIO)),
        )

    male_bmr = _bmr_for_gender(user, Gender.MALE.value)
    female_bmr = _bmr_for_gender(user, Gender.FEMALE.value)
    neutral_bmr = (male_bmr + female_bmr) / 2
    return round(neutral_bmr), CalorieRange(
        min=round(min(male_bmr, female_bmr)),
        max=round(max(male_bmr, female_bmr)),
    )


def _calorie_floor(user: User) -> int:
    return SAFETY_CALORIE_FLOORS.get(_enum_value(user.gender) or "UNKNOWN", SAFETY_CALORIE_FLOORS["UNKNOWN"])


def _recommended_target(user: User, bmi_category: Optional[str], estimated_tdee: float) -> tuple[int, str, str]:
    # 估算值，仅供记录和参考；不是医学处方。
    if bmi_category == "underweight":
        raw_target = estimated_tdee + 400
        strategy = "gain"
        explanation = "当前 BMI 偏低，建议形成适度热量富余，帮助健康增重。"
    elif bmi_category == "normal":
        raw_target = estimated_tdee
        strategy = "maintain"
        explanation = "当前 BMI 处于正常范围，建议摄入量接近日常总消耗，用于维持当前体重。"
    elif bmi_category == "overweight":
        raw_target = estimated_tdee - 400
        strategy = "mild_loss"
        explanation = "当前 BMI 处于超重范围，建议形成适度热量缺口，帮助健康减重。"
    else:
        raw_target = estimated_tdee - 650
        strategy = "loss"
        explanation = "当前 BMI 处于肥胖范围，建议在安全下限以上形成较明确的热量缺口，帮助健康减重。"

    target = max(_round_to_step(raw_target), _calorie_floor(user))
    return target, strategy, explanation


def _condition_limits(conditions: Iterable[HealthCondition]) -> tuple[int, int]:
    active_codes = set()
    for condition in conditions:
        if condition.status not in {ConditionStatus.ACTIVE, ConditionStatus.MONITORING}:
            continue
        active_codes.add(
            match_default_disease_code(condition.condition_code, condition.title) or condition.condition_code
        )

    return (
        1500 if "hypertension" in active_codes else 2300,
        300 if "gout" in active_codes else 600,
    )


def calculate_daily_targets(user: User, conditions: Iterable[HealthCondition]) -> DailyTargets:
    sodium_limit, purine_limit = _condition_limits(conditions)
    bmi = calculate_bmi(user)
    bmi_category = _bmi_category(bmi)
    bmr, bmr_range = _calculate_bmr_and_range(user)
    has_complete_profile = bool(user.gender and user.age and user.height and user.weight)

    if bmr is None or bmi_category is None:
        return DailyTargets(
            **{
                **DEFAULT_DAILY_TARGETS.model_dump(),
                "sodium": sodium_limit,
                "purine": purine_limit,
                "bmi": bmi,
                "bmi_category": bmi_category,
            }
        )

    estimated_tdee = bmr * DEFAULT_ACTIVITY_FACTOR
    recommended, strategy, explanation = _recommended_target(user, bmi_category, estimated_tdee)

    return DailyTargets(
        calories=recommended,
        sodium=sodium_limit,
        purine=purine_limit,
        bmi=bmi,
        bmi_category=bmi_category,
        bmr=bmr,
        bmr_range=bmr_range,
        activity_factor=DEFAULT_ACTIVITY_FACTOR,
        estimated_tdee=round(estimated_tdee),
        recommended_calorie_target=recommended,
        target_strategy=strategy,
        target_explanation=explanation,
        is_estimated=True,
        has_complete_profile=has_complete_profile,
    )
