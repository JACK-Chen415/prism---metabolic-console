"""Deterministic smart-insight evaluation for meal feedback.

This module intentionally keeps Slice 1 independent from persistence and API
wiring. The pure evaluator accepts normalized input contracts; the optional
async helper at the bottom adapts the existing KnowledgeService into those
contracts for later callers.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Any, Optional, Protocol

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.models.health_condition import ConditionStatus, ConditionType, HealthCondition
from app.models.knowledge import RecommendationLevel
from app.models.meal import Meal, MealType
from app.models.message import AppMessage, MessageType
from app.models.user import User
from app.schemas.user import DailyTargets
from app.services.knowledge import KnowledgeService
from app.services.knowledge.normalizer import match_default_disease_code
from app.services.target_service import calculate_daily_targets


class InsightSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    ADVICE = "ADVICE"
    INFO = "INFO"
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"


class InsightCategory(str, Enum):
    MISSING_MEAL = "MISSING_MEAL"
    CALORIES = "CALORIES"
    SODIUM = "SODIUM"
    PURINE = "PURINE"
    MACRO_BALANCE = "MACRO_BALANCE"
    FIBER = "FIBER"
    CONDITION_CAUTION = "CONDITION_CAUTION"
    POSITIVE_FEEDBACK = "POSITIVE_FEEDBACK"


SEVERITY_RANK = {
    InsightSeverity.NEUTRAL: 0,
    InsightSeverity.POSITIVE: 1,
    InsightSeverity.INFO: 2,
    InsightSeverity.ADVICE: 3,
    InsightSeverity.WARNING: 4,
    InsightSeverity.CRITICAL: 5,
}

ACTIVE_CONDITION_STATUSES = {
    ConditionStatus.ACTIVE.value,
    ConditionStatus.MONITORING.value,
    ConditionStatus.ALERT.value,
}

DEFAULT_MEAL_WINDOWS = {
    MealType.BREAKFAST: (time(8, 30), time(10, 0)),
    MealType.LUNCH: (time(12, 0), time(14, 0)),
    MealType.DINNER: (time(18, 0), time(20, 0)),
}

MEAL_CALORIE_BANDS = {
    MealType.BREAKFAST: (0.20, 0.30),
    MealType.LUNCH: (0.30, 0.40),
    MealType.DINNER: (0.30, 0.35),
}

DEFAULT_SODIUM_LIMIT_MG = 2300
DEFAULT_PURINE_LIMIT_MG = 600
GOUT_PURINE_LIMIT_MG = 300
DEFAULT_FIBER_TARGET_G = 25
MIN_MACRO_ENERGY_KCAL = 150
SMART_INSIGHT_ATTRIBUTION_PREFIX = "smart-insights:v1"
INSIGHT_CATEGORY_PRIORITY = {
    InsightCategory.CONDITION_CAUTION: 0,
    InsightCategory.CALORIES: 1,
    InsightCategory.SODIUM: 2,
    InsightCategory.PURINE: 3,
    InsightCategory.MISSING_MEAL: 4,
    InsightCategory.MACRO_BALANCE: 5,
    InsightCategory.FIBER: 6,
    InsightCategory.POSITIVE_FEEDBACK: 7,
}
MEAL_TYPE_PRIORITY = {
    MealType.BREAKFAST: 0,
    MealType.LUNCH: 1,
    MealType.DINNER: 2,
    MealType.SNACK: 3,
}
MAX_NON_SEVERE_CANDIDATES_PER_DAY = 3


class MealWindowState(BaseModel):
    meal_type: MealType
    starts_at: time
    ends_at: time
    is_active: bool
    has_logged_meal: bool


class MealInsightInput(BaseModel):
    id: Optional[str] = None
    name: str
    meal_type: MealType
    record_date: date
    calories: float = 0
    sodium: float = 0
    purine: float = 0
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    fiber: Optional[float] = None

    @classmethod
    def from_obj(cls, meal: Any) -> "MealInsightInput":
        meal_id = getattr(meal, "id", None)
        return cls(
            id=str(meal_id) if meal_id is not None else None,
            name=getattr(meal, "name"),
            meal_type=_coerce_meal_type(getattr(meal, "meal_type")),
            record_date=getattr(meal, "record_date"),
            calories=float(getattr(meal, "calories", 0) or 0),
            sodium=float(getattr(meal, "sodium", 0) or 0),
            purine=float(getattr(meal, "purine", 0) or 0),
            protein=_optional_float(getattr(meal, "protein", None)),
            carbs=_optional_float(getattr(meal, "carbs", None)),
            fat=_optional_float(getattr(meal, "fat", None)),
            fiber=_optional_float(getattr(meal, "fiber", None)),
        )


class ConditionInsightInput(BaseModel):
    condition_code: str
    title: str = ""
    condition_type: Optional[str] = None
    status: str = ConditionStatus.MONITORING.value

    @classmethod
    def from_obj(cls, condition: Any) -> "ConditionInsightInput":
        return cls(
            condition_code=str(getattr(condition, "condition_code", "") or ""),
            title=str(getattr(condition, "title", "") or ""),
            condition_type=_enum_value(getattr(condition, "condition_type", None)),
            status=_enum_value(getattr(condition, "status", ConditionStatus.MONITORING)),
        )


class MealKnowledgeCaution(BaseModel):
    meal_id: Optional[str] = None
    meal_type: MealType
    food_name: str
    recommendation_level: Optional[str] = None
    summary: str = ""
    hard_blocks: list[str] = Field(default_factory=list)
    conflict_note: Optional[str] = None
    caution_note: Optional[str] = None
    matched_disease_codes: list[str] = Field(default_factory=list)


class InsightCandidate(BaseModel):
    key: str
    category: InsightCategory
    severity: InsightSeverity
    title: str
    message: str
    target_date: date
    meal_type: Optional[MealType] = None
    meal_ids: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)


class InsightEvaluationContext(BaseModel):
    target_date: date
    now: datetime
    meals: list[MealInsightInput] = Field(default_factory=list)
    conditions: list[ConditionInsightInput] = Field(default_factory=list)
    daily_targets: Optional[DailyTargets] = None
    knowledge_cautions: list[MealKnowledgeCaution] = Field(default_factory=list)
    meal_windows: dict[MealType, tuple[time, time]] = Field(default_factory=dict)


class SmartInsightRefreshResult(BaseModel):
    target_date: date
    generated_count: int
    messages: list[Any] = Field(default_factory=list)


class SmartInsightEvaluator:
    """Pure deterministic evaluator for Slice 1 smart-insight candidates."""

    def evaluate(self, context: InsightEvaluationContext) -> list[InsightCandidate]:
        meals = [meal for meal in context.meals if meal.record_date == context.target_date]
        meals_by_type = _group_meals_by_type(meals)

        candidates: list[InsightCandidate] = []
        candidates.extend(self._evaluate_missing_meals(context, meals_by_type))
        candidates.extend(self._evaluate_meal_calories(context, meals_by_type))
        candidates.extend(self._evaluate_sodium(context, meals))
        candidates.extend(self._evaluate_purine(context, meals))
        candidates.extend(self._evaluate_macros(context, meals_by_type))
        candidates.extend(self._evaluate_fiber(context, meals_by_type))
        candidates.extend(self._evaluate_knowledge_cautions(context))
        candidates.extend(self._evaluate_positive_feedback(context, meals, candidates))
        candidates = self._post_process_candidates(candidates)

        return sorted(
            candidates,
            key=lambda item: (-SEVERITY_RANK[item.severity], item.key),
        )

    def _post_process_candidates(self, candidates: Sequence[InsightCandidate]) -> list[InsightCandidate]:
        if len(candidates) <= 1:
            return list(candidates)

        meal_scoped: dict[MealType, list[InsightCandidate]] = defaultdict(list)
        global_candidates: list[InsightCandidate] = []

        for candidate in candidates:
            if candidate.meal_type is None:
                global_candidates.append(candidate)
                continue
            meal_scoped[candidate.meal_type].append(candidate)

        compressed: list[InsightCandidate] = list(global_candidates)
        for meal_candidates in meal_scoped.values():
            ranked_candidates = sorted(meal_candidates, key=_candidate_priority)
            strongest_rank = max(SEVERITY_RANK[candidate.severity] for candidate in ranked_candidates)

            if strongest_rank >= SEVERITY_RANK[InsightSeverity.WARNING]:
                compressed.extend(
                    candidate
                    for candidate in ranked_candidates
                    if SEVERITY_RANK[candidate.severity] >= SEVERITY_RANK[InsightSeverity.WARNING]
                )
                continue

            compressed.append(ranked_candidates[0])

        severe_candidates = [
            candidate
            for candidate in compressed
            if SEVERITY_RANK[candidate.severity] >= SEVERITY_RANK[InsightSeverity.WARNING]
        ]
        non_severe_candidates = [
            candidate
            for candidate in compressed
            if SEVERITY_RANK[candidate.severity] < SEVERITY_RANK[InsightSeverity.WARNING]
        ]

        return severe_candidates + sorted(
            non_severe_candidates,
            key=_candidate_priority,
        )[:MAX_NON_SEVERE_CANDIDATES_PER_DAY]

    def meal_window_states(self, context: InsightEvaluationContext) -> list[MealWindowState]:
        meals = [meal for meal in context.meals if meal.record_date == context.target_date]
        meals_by_type = _group_meals_by_type(meals)
        current_time = context.now.time()
        is_current_date = context.now.date() == context.target_date
        meal_windows = _resolve_meal_windows(context.meal_windows)

        return [
            MealWindowState(
                meal_type=meal_type,
                starts_at=starts_at,
                ends_at=ends_at,
                is_active=is_current_date and starts_at <= current_time <= ends_at,
                has_logged_meal=bool(meals_by_type.get(meal_type)),
            )
            for meal_type, (starts_at, ends_at) in meal_windows.items()
        ]

    def _evaluate_missing_meals(
        self,
        context: InsightEvaluationContext,
        meals_by_type: dict[MealType, list[MealInsightInput]],
    ) -> list[InsightCandidate]:
        candidates: list[InsightCandidate] = []
        for state in self.meal_window_states(context):
            if not state.is_active or state.has_logged_meal:
                continue
            candidates.append(
                InsightCandidate(
                    key=f"{context.target_date}:missing:{state.meal_type.value.lower()}",
                    category=InsightCategory.MISSING_MEAL,
                    severity=InsightSeverity.ADVICE,
                    title=f"Log {_meal_label(state.meal_type)} before {state.ends_at.strftime('%H:%M')}",
                    message=(
                        f"The {_meal_label(state.meal_type)} window is open until "
                        f"{state.ends_at.strftime('%H:%M')}. Add it now so today's coaching stays accurate."
                    ),
                    target_date=context.target_date,
                    meal_type=state.meal_type,
                    signals={
                        "window_start": state.starts_at.isoformat(timespec="minutes"),
                        "window_end": state.ends_at.isoformat(timespec="minutes"),
                    },
                )
            )
        return candidates

    def _evaluate_meal_calories(
        self,
        context: InsightEvaluationContext,
        meals_by_type: dict[MealType, list[MealInsightInput]],
    ) -> list[InsightCandidate]:
        target = _calorie_target(context.daily_targets)
        if target <= 0:
            return []

        candidates: list[InsightCandidate] = []
        for meal_type, meals in meals_by_type.items():
            calories = sum(meal.calories for meal in meals)
            meal_ids = _meal_ids(meals)

            if meal_type == MealType.SNACK:
                threshold = max(400, target * 0.20)
                if calories > threshold:
                    candidates.append(
                        InsightCandidate(
                            key=f"{context.target_date}:calories:snack_high",
                            category=InsightCategory.CALORIES,
                            severity=InsightSeverity.ADVICE,
                            title="Keep snacks lighter for the rest of today",
                            message=(
                                f"This snack logged {_format_number(calories)} kcal, above your "
                                f"{_format_number(threshold)} kcal snack threshold. Next step: skip one extra add-on "
                                "or choose a lighter option later today."
                            ),
                            target_date=context.target_date,
                            meal_type=meal_type,
                            meal_ids=meal_ids,
                            signals={"calories": calories, "threshold": threshold, "daily_target": target},
                        )
                    )
                continue

            band = MEAL_CALORIE_BANDS.get(meal_type)
            if not band:
                continue

            lower = target * band[0]
            upper = target * band[1]
            if calories > upper * 1.15:
                candidates.append(
                    InsightCandidate(
                        key=f"{context.target_date}:calories:{meal_type.value.lower()}_high",
                        category=InsightCategory.CALORIES,
                        severity=InsightSeverity.WARNING,
                        title=f"Scale back this {_meal_label(meal_type)}",
                        message=(
                            f"This {_meal_label(meal_type)} logged {_format_number(calories)} kcal, above your "
                            f"{_format_number(lower)}-{_format_number(upper)} kcal target band. Next step: trim one "
                            "calorie-dense item or portion next time."
                        ),
                        target_date=context.target_date,
                        meal_type=meal_type,
                        meal_ids=meal_ids,
                        signals={
                            "calories": calories,
                            "band_min": lower,
                            "band_max": upper,
                            "daily_target": target,
                        },
                    )
                )
            elif calories < lower * 0.75:
                candidates.append(
                    InsightCandidate(
                        key=f"{context.target_date}:calories:{meal_type.value.lower()}_low",
                        category=InsightCategory.CALORIES,
                        severity=InsightSeverity.ADVICE,
                        title=f"Round out this {_meal_label(meal_type)} a bit more",
                        message=(
                            f"This {_meal_label(meal_type)} logged {_format_number(calories)} kcal, below your "
                            f"{_format_number(lower)}-{_format_number(upper)} kcal target band. Next step: add a "
                            "balanced side like protein, fruit, or a staple portion."
                        ),
                        target_date=context.target_date,
                        meal_type=meal_type,
                        meal_ids=meal_ids,
                        signals={
                            "calories": calories,
                            "band_min": lower,
                            "band_max": upper,
                            "daily_target": target,
                        },
                    )
                )
        return candidates

    def _evaluate_sodium(
        self,
        context: InsightEvaluationContext,
        meals: Sequence[MealInsightInput],
    ) -> list[InsightCandidate]:
        limit = _sodium_limit(context.daily_targets)
        total = sum(meal.sodium for meal in meals)
        if total <= limit:
            return []
        return [
            InsightCandidate(
                key=f"{context.target_date}:sodium:daily_excess",
                category=InsightCategory.SODIUM,
                severity=InsightSeverity.WARNING,
                title="Lower sodium for the rest of today",
                message=(
                    f"You've logged {_format_number(total)} mg sodium, above your "
                    f"{_format_number(limit)} mg daily limit. Next step: skip extra sauces and choose lower-sodium "
                    "foods for later meals."
                ),
                target_date=context.target_date,
                meal_ids=_meal_ids(meals),
                signals={"sodium_mg": total, "limit_mg": limit},
            )
        ]

    def _evaluate_purine(
        self,
        context: InsightEvaluationContext,
        meals: Sequence[MealInsightInput],
    ) -> list[InsightCandidate]:
        if not _has_active_gout(context.conditions):
            return []

        limit = _purine_limit(context.daily_targets, gout_user=True)
        total = sum(meal.purine for meal in meals)
        if total <= limit:
            return []
        return [
            InsightCandidate(
                key=f"{context.target_date}:purine:gout_excess",
                category=InsightCategory.PURINE,
                severity=InsightSeverity.WARNING,
                title="Keep the rest of today lower purine",
                message=(
                    f"You've logged {_format_number(total)} mg purine, above your gout-focused "
                    f"{_format_number(limit)} mg limit. Next step: avoid more high-purine choices like beer or organ "
                    "meats in later meals."
                ),
                target_date=context.target_date,
                meal_ids=_meal_ids(meals),
                signals={"purine_mg": total, "limit_mg": limit},
            )
        ]

    def _evaluate_macros(
        self,
        context: InsightEvaluationContext,
        meals_by_type: dict[MealType, list[MealInsightInput]],
    ) -> list[InsightCandidate]:
        candidates: list[InsightCandidate] = []
        for meal_type, meals in meals_by_type.items():
            if not _all_macro_data_present(meals):
                continue

            protein = sum(meal.protein or 0 for meal in meals)
            carbs = sum(meal.carbs or 0 for meal in meals)
            fat = sum(meal.fat or 0 for meal in meals)
            macro_energy = protein * 4 + carbs * 4 + fat * 9
            if macro_energy < MIN_MACRO_ENERGY_KCAL:
                continue

            ratios = {
                "protein": (protein * 4) / macro_energy,
                "carbs": (carbs * 4) / macro_energy,
                "fat": (fat * 9) / macro_energy,
            }
            imbalance = _strongest_macro_imbalance(ratios)
            if not imbalance:
                continue

            candidates.append(
                InsightCandidate(
                    key=f"{context.target_date}:macros:{meal_type.value.lower()}_{imbalance}",
                    category=InsightCategory.MACRO_BALANCE,
                    severity=InsightSeverity.ADVICE,
                    title=_macro_title(meal_type, imbalance),
                    message=_macro_message(meal_type, imbalance),
                    target_date=context.target_date,
                    meal_type=meal_type,
                    meal_ids=_meal_ids(meals),
                    signals={
                        "imbalance": imbalance,
                        "protein_ratio": round(ratios["protein"], 4),
                        "carbs_ratio": round(ratios["carbs"], 4),
                        "fat_ratio": round(ratios["fat"], 4),
                    },
                )
            )
        return candidates

    def _evaluate_fiber(
        self,
        context: InsightEvaluationContext,
        meals_by_type: dict[MealType, list[MealInsightInput]],
    ) -> list[InsightCandidate]:
        candidates: list[InsightCandidate] = []
        for meal_type, meals in meals_by_type.items():
            if meal_type == MealType.SNACK or not any(meal.fiber is not None for meal in meals):
                continue

            fiber = sum(meal.fiber or 0 for meal in meals)
            calories = sum(meal.calories for meal in meals)
            if calories < 150 or fiber >= 3:
                continue

            candidates.append(
                InsightCandidate(
                    key=f"{context.target_date}:fiber:{meal_type.value.lower()}_low",
                    category=InsightCategory.FIBER,
                    severity=InsightSeverity.ADVICE,
                    title=f"Add more fiber to {_meal_label(meal_type)}",
                    message=(
                        f"This {_meal_label(meal_type)} logged {_format_number(fiber)} g fiber. Next step: add "
                        "vegetables, beans, fruit, or whole grains to bring it up."
                    ),
                    target_date=context.target_date,
                    meal_type=meal_type,
                    meal_ids=_meal_ids(meals),
                    signals={
                        "fiber_g": fiber,
                        "meal_threshold_g": 3,
                        "daily_reference_g": DEFAULT_FIBER_TARGET_G,
                    },
                )
            )
        return candidates

    def _evaluate_knowledge_cautions(self, context: InsightEvaluationContext) -> list[InsightCandidate]:
        grouped: dict[MealType, list[MealKnowledgeCaution]] = defaultdict(list)
        for caution in context.knowledge_cautions:
            grouped[caution.meal_type].append(caution)

        candidates: list[InsightCandidate] = []
        for meal_type, cautions in grouped.items():
            ranked = [(self._knowledge_severity(caution), caution) for caution in cautions]
            severity = max((item[0] for item in ranked), key=lambda value: SEVERITY_RANK[value])
            foods = _unique([caution.food_name for caution in cautions])
            hard_blocks = _unique(block for caution in cautions for block in caution.hard_blocks)
            levels = _unique(
                caution.recommendation_level
                for caution in cautions
                if caution.recommendation_level
            )
            notes = _unique(
                note
                for caution in cautions
                for note in [caution.conflict_note, caution.caution_note, caution.summary]
                if note
            )

            candidates.append(
                InsightCandidate(
                    key=f"{context.target_date}:knowledge:{meal_type.value.lower()}",
                    category=InsightCategory.CONDITION_CAUTION,
                    severity=severity,
                    title=_condition_caution_title(meal_type, severity),
                    message=_condition_caution_message(meal_type, foods, notes, hard_blocks),
                    target_date=context.target_date,
                    meal_type=meal_type,
                    meal_ids=_unique(caution.meal_id for caution in cautions if caution.meal_id),
                    signals={
                        "foods": foods,
                        "recommendation_levels": levels,
                        "hard_blocks": hard_blocks,
                    },
                )
            )
        return candidates

    def _evaluate_positive_feedback(
        self,
        context: InsightEvaluationContext,
        meals: Sequence[MealInsightInput],
        existing_candidates: Sequence[InsightCandidate],
    ) -> list[InsightCandidate]:
        has_stronger_feedback = any(
            SEVERITY_RANK[candidate.severity] >= SEVERITY_RANK[InsightSeverity.ADVICE]
            for candidate in existing_candidates
        )
        if has_stronger_feedback or not meals:
            return []

        return [
            InsightCandidate(
                key=f"{context.target_date}:positive:daily_no_warning",
                category=InsightCategory.POSITIVE_FEEDBACK,
                severity=InsightSeverity.POSITIVE,
                title="Keep this meal pattern going",
                message="Today's logged meals stayed within current rules. Repeat similar portions and meal choices next time.",
                target_date=context.target_date,
                meal_ids=_meal_ids(meals),
                signals={"meal_count": len(meals)},
            )
        ]

    @staticmethod
    def _knowledge_severity(caution: MealKnowledgeCaution) -> InsightSeverity:
        if caution.hard_blocks:
            return InsightSeverity.CRITICAL
        if caution.recommendation_level in {
            RecommendationLevel.AVOID.value,
            RecommendationLevel.LIMIT.value,
        }:
            return InsightSeverity.WARNING
        if caution.recommendation_level in {
            RecommendationLevel.MODERATE.value,
            RecommendationLevel.CONDITIONAL.value,
        }:
            return InsightSeverity.ADVICE
        return InsightSeverity.INFO


class KnowledgeServiceLike(Protocol):
    async def evaluate_food_for_user(
        self,
        db: Any,
        *,
        user: Any,
        conditions: Sequence[Any],
        food_name: Optional[str] = None,
        food_code: Optional[str] = None,
        explicit_condition_codes: Optional[list[str]] = None,
        manual_restrictions: Optional[list[str]] = None,
    ) -> Any:
        ...


def build_insight_context(
    *,
    target_date: date,
    now: datetime,
    meals: Sequence[Any],
    conditions: Sequence[Any],
    daily_targets: Optional[DailyTargets] = None,
    knowledge_cautions: Optional[Sequence[MealKnowledgeCaution]] = None,
    meal_windows: Optional[dict[MealType, tuple[time, time]]] = None,
) -> InsightEvaluationContext:
    return InsightEvaluationContext(
        target_date=target_date,
        now=now,
        meals=[meal if isinstance(meal, MealInsightInput) else MealInsightInput.from_obj(meal) for meal in meals],
        conditions=[
            condition
            if isinstance(condition, ConditionInsightInput)
            else ConditionInsightInput.from_obj(condition)
            for condition in conditions
        ],
        daily_targets=daily_targets,
        knowledge_cautions=list(knowledge_cautions or []),
        meal_windows=dict(meal_windows or {}),
    )


def evaluate_smart_insights(
    *,
    target_date: date,
    now: datetime,
    meals: Sequence[Any],
    conditions: Sequence[Any],
    daily_targets: Optional[DailyTargets] = None,
    knowledge_cautions: Optional[Sequence[MealKnowledgeCaution]] = None,
    meal_windows: Optional[dict[MealType, tuple[time, time]]] = None,
) -> list[InsightCandidate]:
    context = build_insight_context(
        target_date=target_date,
        now=now,
        meals=meals,
        conditions=conditions,
        daily_targets=daily_targets,
        knowledge_cautions=knowledge_cautions,
        meal_windows=meal_windows,
    )
    return SmartInsightEvaluator().evaluate(context)


def _resolve_meal_windows(
    overrides: Optional[dict[MealType, tuple[time, time]]] = None,
) -> dict[MealType, tuple[time, time]]:
    meal_windows = dict(DEFAULT_MEAL_WINDOWS)
    for meal_type, window in (overrides or {}).items():
        if meal_type in meal_windows:
            meal_windows[meal_type] = window
    return meal_windows


async def evaluate_knowledge_cautions_for_meals(
    db: Any,
    *,
    user: Any,
    conditions: Sequence[Any],
    meals: Sequence[Any],
    knowledge_service: KnowledgeServiceLike,
    manual_restrictions: Optional[Sequence[str]] = None,
) -> list[MealKnowledgeCaution]:
    """Adapt KnowledgeService decisions into pure evaluator cautions."""

    restrictions = _manual_restrictions_from_conditions(conditions)
    restrictions.extend(manual_restrictions or [])
    restrictions = _unique(restrictions)

    cautions: list[MealKnowledgeCaution] = []
    for meal_obj in meals:
        meal = meal_obj if isinstance(meal_obj, MealInsightInput) else MealInsightInput.from_obj(meal_obj)
        decision = await knowledge_service.evaluate_food_for_user(
            db,
            user=user,
            conditions=conditions,
            food_name=meal.name,
            manual_restrictions=restrictions,
        )
        caution = _caution_from_decision(meal, decision)
        if caution:
            cautions.append(caution)
    return cautions


class SmartInsightMessageService:
    """Persist deterministic smart insights as AppMessage records."""

    def __init__(
        self,
        *,
        evaluator: Optional[SmartInsightEvaluator] = None,
        knowledge_service: Optional[KnowledgeServiceLike] = None,
    ):
        self.evaluator = evaluator or SmartInsightEvaluator()
        self.knowledge_service = knowledge_service or KnowledgeService()

    async def refresh_today(
        self,
        db: Any,
        *,
        user: User,
        target_date: Optional[date] = None,
        now: Optional[datetime] = None,
    ) -> SmartInsightRefreshResult:
        target_date = target_date or date.today()
        now = now or datetime.now(timezone.utc)

        conditions = await self._load_conditions(db, user.id)
        meals = await self._load_meals(db, user.id, target_date)
        daily_targets = calculate_daily_targets(user, conditions)
        knowledge_cautions = await self._build_knowledge_cautions(db, user, conditions, meals)
        candidates = self.evaluator.evaluate(
            build_insight_context(
                target_date=target_date,
                now=now,
                meals=meals,
                conditions=conditions,
                daily_targets=daily_targets,
                knowledge_cautions=knowledge_cautions,
            )
        )

        await self._delete_generated_messages_for_date(db, user.id, target_date)

        messages: list[AppMessage] = []
        for candidate in candidates:
            message = self._message_from_candidate(user.id, candidate)
            db.add(message)
            messages.append(message)

        await db.flush()
        for message in messages:
            await db.refresh(message)

        return SmartInsightRefreshResult(
            target_date=target_date,
            generated_count=len(messages),
            messages=messages,
        )

    async def list_today(
        self,
        db: Any,
        *,
        user: User,
        target_date: Optional[date] = None,
    ) -> list[AppMessage]:
        target_date = target_date or date.today()
        result = await db.execute(
            select(AppMessage)
            .where(
                AppMessage.user_id == user.id,
                AppMessage.attribution.like(f"{self._date_prefix(target_date)}%"),
            )
            .order_by(AppMessage.created_at.desc())
        )
        return list(result.scalars().all())

    async def _load_conditions(self, db: Any, user_id: int) -> list[Any]:
        result = await db.execute(
            select(HealthCondition).where(HealthCondition.user_id == user_id)
        )
        return list(result.scalars().all())

    async def _load_meals(self, db: Any, user_id: int, target_date: date) -> list[Any]:
        result = await db.execute(
            select(Meal).where(
                Meal.user_id == user_id,
                Meal.record_date == target_date,
            )
        )
        return list(result.scalars().all())

    async def _build_knowledge_cautions(
        self,
        db: Any,
        user: User,
        conditions: Sequence[Any],
        meals: Sequence[Any],
    ) -> list[MealKnowledgeCaution]:
        if not meals or not conditions:
            return []
        return await evaluate_knowledge_cautions_for_meals(
            db,
            user=user,
            conditions=conditions,
            meals=meals,
            knowledge_service=self.knowledge_service,
        )

    async def _delete_generated_messages_for_date(
        self,
        db: Any,
        user_id: int,
        target_date: date,
    ) -> None:
        result = await db.execute(
            select(AppMessage).where(
                AppMessage.user_id == user_id,
                AppMessage.attribution.like(f"{self._date_prefix(target_date)}%"),
            )
        )
        for message in result.scalars().all():
            await db.delete(message)

    def _message_from_candidate(self, user_id: int, candidate: InsightCandidate) -> AppMessage:
        return AppMessage(
            user_id=user_id,
            message_type=self._message_type(candidate),
            title=candidate.title[:100],
            content=candidate.message,
            attribution=self._attribution(candidate),
        )

    @staticmethod
    def _message_type(candidate: InsightCandidate) -> MessageType:
        if candidate.severity in {InsightSeverity.CRITICAL, InsightSeverity.WARNING}:
            return MessageType.WARNING
        if candidate.severity == InsightSeverity.ADVICE:
            return MessageType.ADVICE
        return MessageType.BRIEF

    @staticmethod
    def _date_prefix(target_date: date) -> str:
        return f"{SMART_INSIGHT_ATTRIBUTION_PREFIX}|date={target_date.isoformat()}|"

    def _attribution(self, candidate: InsightCandidate) -> str:
        parts = [
            f"key={candidate.key}",
            f"category={candidate.category.value}",
            f"severity={candidate.severity.value}",
        ]
        if candidate.meal_ids:
            parts.append(f"meal_ids={','.join(candidate.meal_ids)}")
        return f"{self._date_prefix(candidate.target_date)}{'|'.join(parts)}"


def _caution_from_decision(meal: MealInsightInput, decision: Any) -> Optional[MealKnowledgeCaution]:
    level = _enum_value(getattr(decision, "recommendation_level", None))
    hard_blocks = list(getattr(decision, "hard_blocks", []) or [])
    if not hard_blocks and level not in {
        RecommendationLevel.AVOID.value,
        RecommendationLevel.LIMIT.value,
        RecommendationLevel.MODERATE.value,
        RecommendationLevel.CONDITIONAL.value,
    }:
        return None

    return MealKnowledgeCaution(
        meal_id=meal.id,
        meal_type=meal.meal_type,
        food_name=str(getattr(decision, "food_name", meal.name) or meal.name),
        recommendation_level=level,
        summary=str(getattr(decision, "summary", "") or ""),
        hard_blocks=hard_blocks,
        conflict_note=getattr(decision, "conflict_note", None),
        caution_note=getattr(decision, "caution_note", None),
        matched_disease_codes=list(getattr(decision, "matched_disease_codes", []) or []),
    )


def _manual_restrictions_from_conditions(conditions: Sequence[Any]) -> list[str]:
    restrictions: list[str] = []
    for condition in conditions:
        condition_type = _enum_value(getattr(condition, "condition_type", None))
        if condition_type != ConditionType.ALLERGY.value:
            continue
        title = str(getattr(condition, "title", "") or "")
        code = str(getattr(condition, "condition_code", "") or "")
        if title:
            restrictions.append(title)
        if code:
            restrictions.append(code)
    return restrictions


def _group_meals_by_type(meals: Iterable[MealInsightInput]) -> dict[MealType, list[MealInsightInput]]:
    grouped: dict[MealType, list[MealInsightInput]] = defaultdict(list)
    for meal in meals:
        grouped[meal.meal_type].append(meal)
    return dict(grouped)


def _calorie_target(daily_targets: Optional[DailyTargets]) -> int:
    if not daily_targets:
        return 0
    return daily_targets.recommended_calorie_target or daily_targets.calories or 0


def _sodium_limit(daily_targets: Optional[DailyTargets]) -> int:
    if not daily_targets:
        return DEFAULT_SODIUM_LIMIT_MG
    return daily_targets.sodium or DEFAULT_SODIUM_LIMIT_MG


def _purine_limit(daily_targets: Optional[DailyTargets], *, gout_user: bool) -> int:
    fallback = GOUT_PURINE_LIMIT_MG if gout_user else DEFAULT_PURINE_LIMIT_MG
    if not daily_targets:
        return fallback
    return daily_targets.purine or fallback


def _has_active_gout(conditions: Sequence[ConditionInsightInput]) -> bool:
    for condition in conditions:
        if condition.status not in ACTIVE_CONDITION_STATUSES:
            continue
        normalized = match_default_disease_code(condition.condition_code, condition.title)
        if normalized == "gout" or condition.condition_code == "gout":
            return True
    return False


def _all_macro_data_present(meals: Sequence[MealInsightInput]) -> bool:
    return bool(meals) and all(
        meal.protein is not None and meal.carbs is not None and meal.fat is not None
        for meal in meals
    )


def _strongest_macro_imbalance(ratios: dict[str, float]) -> Optional[str]:
    imbalances: dict[str, float] = {}
    if ratios["carbs"] > 0.65:
        imbalances["carb_heavy"] = (ratios["carbs"] - 0.65) / 0.65
    if ratios["fat"] > 0.40:
        imbalances["fat_heavy"] = (ratios["fat"] - 0.40) / 0.40
    if ratios["protein"] < 0.15:
        imbalances["protein_weak"] = (0.15 - ratios["protein"]) / 0.15
    if not imbalances:
        return None
    return max(imbalances.items(), key=lambda item: item[1])[0]


def _meal_ids(meals: Iterable[MealInsightInput]) -> list[str]:
    return _unique(meal.id for meal in meals if meal.id)


def _meal_label(meal_type: MealType) -> str:
    return meal_type.value.lower()


def _format_number(value: float) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}"


def _macro_title(meal_type: MealType, imbalance: str) -> str:
    meal_label = _meal_label(meal_type)
    if imbalance == "carb_heavy":
        return f"Add more protein to this {meal_label}"
    if imbalance == "fat_heavy":
        return f"Lighten the fattier parts of this {meal_label}"
    return f"Add a stronger protein source to this {meal_label}"


def _macro_message(meal_type: MealType, imbalance: str) -> str:
    meal_label = _meal_label(meal_type)
    if imbalance == "carb_heavy":
        return (
            f"This {meal_label} skews carb heavy. Next step: pair the starch-heavy items with lean protein or extra "
            "vegetables."
        )
    if imbalance == "fat_heavy":
        return (
            f"This {meal_label} skews fat heavy. Next step: swap one fried, oily, or creamy item for a leaner choice."
        )
    return (
        f"This {meal_label} is light on protein. Next step: add eggs, tofu, dairy, fish, or another protein source."
    )


def _condition_caution_title(meal_type: MealType, severity: InsightSeverity) -> str:
    if severity == InsightSeverity.CRITICAL:
        return f"Remove flagged items from this {_meal_label(meal_type)}"
    return f"Adjust this {_meal_label(meal_type)} for condition safety"


def _condition_caution_message(
    meal_type: MealType,
    foods: Sequence[str],
    notes: Sequence[str],
    hard_blocks: Sequence[str],
) -> str:
    meal_label = _meal_label(meal_type)
    food_text = f"Check {', '.join(foods[:2])}" if foods else f"Check this {meal_label}"
    action = "avoid the flagged items and choose a safer swap" if hard_blocks else "limit or swap the flagged items"
    note_text = f" {notes[0]}" if notes else ""
    return f"{food_text} before repeating this {meal_label}. Next step: {action}.{note_text}"


def _candidate_priority(candidate: InsightCandidate) -> tuple[int, int, int, str]:
    return (
        -SEVERITY_RANK[candidate.severity],
        INSIGHT_CATEGORY_PRIORITY.get(candidate.category, len(INSIGHT_CATEGORY_PRIORITY)),
        MEAL_TYPE_PRIORITY.get(candidate.meal_type, len(MEAL_TYPE_PRIORITY)),
        candidate.key,
    )


def _unique(values: Iterable[Any]) -> list[Any]:
    seen = set()
    result = []
    for value in values:
        if value is None or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _coerce_meal_type(value: Any) -> MealType:
    if isinstance(value, MealType):
        return value
    primitive = value.value if isinstance(value, Enum) else value
    return MealType(primitive)


def _enum_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    return getattr(value, "value", value)
