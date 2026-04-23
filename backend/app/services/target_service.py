"""Single source for daily nutrition target calculation."""

from collections.abc import Iterable
from typing import Optional

from app.models.health_condition import ConditionStatus, HealthCondition
from app.models.user import User
from app.schemas.user import DailyTargets


DEFAULT_DAILY_TARGETS = DailyTargets(calories=2000, sodium=2300, purine=600)


def calculate_bmi(user: User) -> Optional[float]:
    if not user.height or not user.weight:
        return None
    return round(user.weight / (user.height / 100) ** 2, 1)


def calculate_daily_targets(user: User, conditions: Iterable[HealthCondition]) -> DailyTargets:
    if not all([user.gender, user.age, user.height, user.weight]):
        return DEFAULT_DAILY_TARGETS

    s = 5 if user.gender.value == "MALE" else -161
    bmr = (10 * user.weight) + (6.25 * user.height) - (5 * user.age) + s
    calories = int(bmr * 1.375)

    active_codes = {
        condition.condition_code
        for condition in conditions
        if condition.status in {ConditionStatus.ACTIVE, ConditionStatus.MONITORING}
    }

    return DailyTargets(
        calories=calories,
        sodium=1500 if "hypertension" in active_codes else 2300,
        purine=300 if "gout" in active_codes else 600,
    )
