"""Multimodal intake parsing and confirmation service."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health_condition import HealthCondition
from app.models.knowledge import FallbackStatus, KnowledgeOrigin, RecommendationLevel
from app.models.meal import FoodCategory, Meal, MealType, SyncStatus
from app.models.user import User
from app.schemas.intake import (
    IntakeCandidate,
    IntakeConfirmFailure,
    IntakeConfirmItem,
    IntakeConfirmRequest,
    IntakeConfirmResponse,
    IntakeDraftSessionResponse,
    IntakeSource,
    PhotoParseRequest,
    VoiceParseRequest,
)
from app.schemas.meal import MealResponse
from app.services.knowledge import KnowledgeService, write_knowledge_audit_log
from app.services.knowledge.contracts import LocalDecision, NormalizedConditions


CATEGORY_ALIAS_MAP = {
    "STAPLE": FoodCategory.STAPLE,
    "VEG": FoodCategory.VEG,
    "FRUIT": FoodCategory.VEG,
    "MEAT": FoodCategory.MEAT,
    "SEAFOOD": FoodCategory.MEAT,
    "SOY": FoodCategory.MEAT,
    "DAIRY": FoodCategory.DRINK,
    "DRINK": FoodCategory.DRINK,
    "BEVERAGE": FoodCategory.DRINK,
    "SNACK": FoodCategory.SNACK,
}

MEAL_TYPE_HINTS = [
    (MealType.BREAKFAST, ("早餐", "早饭", "早上", "早晨", "上午")),
    (MealType.LUNCH, ("午餐", "午饭", "中午")),
    (MealType.DINNER, ("晚餐", "晚饭", "晚上", "傍晚")),
    (MealType.SNACK, ("加餐", "零食", "夜宵")),
]

AMOUNT_PATTERN = re.compile(
    r"(?P<amount>(?:\d+(?:\.\d+)?)|半|两|一|二|三|四|五|六|七|八|九|十|少量|一点)\s*(?P<unit>毫升|ml|mL|克|g|杯|碗|个|根|份|包|瓶|听|块)"
)
SEPARATOR_PATTERN = re.compile(r"[，,、；;]|(?:\s*和\s*)|(?:\s*以及\s*)|(?:\s*还有\s*)|(?:\s*外加\s*)|(?:\s*加上\s*)")
LEADING_CONTEXT_PATTERN = re.compile(
    r"^(今天|今日|刚才|刚刚|我|上午|下午|早上|早晨|中午|晚上|早餐|午餐|晚餐|加餐|夜宵|早饭|午饭|晚饭|吃了|喝了|吃|喝)+"
)

GENERIC_CATEGORY_HINTS = {
    FoodCategory.STAPLE: {"calories": 116.0, "protein": 2.6, "carbs": 25.9, "fat": 0.3, "fiber": 0.5, "sodium": 4.0, "purine": 12.0},
    FoodCategory.MEAT: {"calories": 165.0, "protein": 22.0, "carbs": 1.0, "fat": 8.0, "fiber": 0.0, "sodium": 80.0, "purine": 120.0},
    FoodCategory.VEG: {"calories": 30.0, "protein": 2.0, "carbs": 5.0, "fat": 0.3, "fiber": 2.0, "sodium": 20.0, "purine": 15.0},
    FoodCategory.DRINK: {"calories": 20.0, "protein": 1.0, "carbs": 3.0, "fat": 0.5, "fiber": 0.0, "sodium": 15.0, "purine": 2.0},
    FoodCategory.SNACK: {"calories": 300.0, "protein": 5.0, "carbs": 35.0, "fat": 14.0, "fiber": 1.0, "sodium": 240.0, "purine": 18.0},
}

COMMON_FOOD_HINTS = {
    "鸡蛋": {
        "aliases": ("鸡蛋", "水煮蛋", "煎蛋", "蛋"),
        "category": FoodCategory.MEAT,
        "grams_per_unit": 50.0,
        "nutrition_per_100g": {"calories": 144.0, "protein": 13.0, "carbs": 1.1, "fat": 10.0, "fiber": 0.0, "sodium": 140.0, "purine": 10.0},
    },
    "玉米": {
        "aliases": ("玉米", "甜玉米", "玉米棒"),
        "category": FoodCategory.STAPLE,
        "grams_per_unit": 120.0,
        "nutrition_per_100g": {"calories": 112.0, "protein": 3.6, "carbs": 22.8, "fat": 1.5, "fiber": 2.9, "sodium": 1.0, "purine": 16.0},
    },
    "排骨": {
        "aliases": ("排骨", "红烧排骨", "糖醋排骨"),
        "category": FoodCategory.MEAT,
        "grams_per_unit": 100.0,
        "nutrition_per_100g": {"calories": 260.0, "protein": 17.0, "carbs": 6.0, "fat": 18.0, "fiber": 0.0, "sodium": 180.0, "purine": 135.0},
    },
}

UNIT_BASE_WEIGHTS = {
    "g": 1.0,
    "克": 1.0,
    "ml": 1.0,
    "毫升": 1.0,
    "个": 50.0,
    "根": 80.0,
    "杯": 250.0,
    "碗": 150.0,
    "份": 100.0,
    "包": 100.0,
    "瓶": 500.0,
    "听": 330.0,
    "块": 80.0,
}

NUMBER_WORDS = {"半": 0.5, "一": 1.0, "二": 2.0, "两": 2.0, "三": 3.0, "四": 4.0, "五": 5.0, "六": 6.0, "七": 7.0, "八": 8.0, "九": 9.0, "十": 10.0}

STRICTNESS_ORDER = {
    RecommendationLevel.RECOMMEND: 0,
    RecommendationLevel.MODERATE: 1,
    RecommendationLevel.CONDITIONAL: 2,
    RecommendationLevel.INSUFFICIENT: 3,
    RecommendationLevel.LIMIT: 4,
    RecommendationLevel.AVOID: 5,
}

FALLBACK_PRIORITY = {
    FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD: 0,
    FallbackStatus.LOCAL_PARTIAL_ALLOW_CLOUD: 1,
    FallbackStatus.LOCAL_COMPLETE: 2,
    FallbackStatus.LOCAL_BLOCKED_NO_CLOUD: 3,
}


class IntakeService:
    def __init__(self, knowledge_service: Optional[KnowledgeService] = None):
        self.knowledge_service = knowledge_service or KnowledgeService()

    async def parse_voice(
        self,
        db: AsyncSession,
        *,
        user: User,
        conditions: list[HealthCondition],
        data: VoiceParseRequest,
    ) -> IntakeDraftSessionResponse:
        normalized = await self.knowledge_service.normalize_conditions(db, conditions)
        meal_type = self._infer_meal_type(data.transcript, data.meal_time_hint)
        record_date = data.record_date or date.today()
        time_hint = data.meal_time_hint or self._detect_time_hint(data.transcript)

        candidates: list[IntakeCandidate] = []
        for segment in self._split_voice_segments(data.transcript):
            candidate = await self._candidate_from_voice_segment(
                db,
                user=user,
                normalized=normalized,
                segment=segment,
                meal_type=meal_type,
                time_hint=time_hint,
            )
            if candidate is not None:
                candidates.append(candidate)

        await self._write_parse_audit(
            db,
            route_name="/api/intake/voice/parse",
            user_id=user.id,
            query_excerpt=data.transcript,
            candidates=candidates,
        )
        return IntakeDraftSessionResponse(
            source=IntakeSource.VOICE,
            raw_input_text=data.transcript,
            record_date=record_date,
            meal_time_hint=time_hint,
            candidates=candidates,
            summary_warning=self._build_session_warning(candidates),
        )

    async def parse_photo_result(
        self,
        db: AsyncSession,
        *,
        user: User,
        conditions: list[HealthCondition],
        data: PhotoParseRequest,
    ) -> IntakeDraftSessionResponse:
        normalized = await self.knowledge_service.normalize_conditions(db, conditions)
        meal_type = self._infer_meal_type(data.ai_response or "", data.meal_time_hint)
        record_date = data.record_date or date.today()
        time_hint = data.meal_time_hint or self._detect_time_hint(data.ai_response or "")

        candidates: list[IntakeCandidate] = []
        for food in data.recognized_foods:
            candidates.append(
                await self._candidate_from_photo_food(
                    db,
                    user=user,
                    normalized=normalized,
                    food=food,
                    meal_type=meal_type,
                    time_hint=time_hint,
                )
            )

        await self._write_parse_audit(
            db,
            route_name="/api/intake/photo/parse-result",
            user_id=user.id,
            query_excerpt=data.ai_response or "recognized_foods",
            candidates=candidates,
        )
        return IntakeDraftSessionResponse(
            source=IntakeSource.PHOTO,
            raw_summary=data.ai_response,
            record_date=record_date,
            meal_time_hint=time_hint,
            candidates=candidates,
            summary_warning=self._build_session_warning(candidates),
        )

    async def confirm(
        self,
        db: AsyncSession,
        *,
        user: User,
        conditions: list[HealthCondition],
        data: IntakeConfirmRequest,
    ) -> IntakeConfirmResponse:
        if not data.candidates:
            raise ValueError("待确认候选项不能为空")

        normalized = await self.knowledge_service.normalize_conditions(db, conditions)
        record_date = data.record_date or date.today()

        meals: list[Meal] = []
        failures: list[IntakeConfirmFailure] = []
        warnings_summary: list[str] = []
        confirmed_candidates: list[IntakeCandidate] = []

        for item in data.candidates:
            try:
                meal, candidate = await self._meal_from_confirm_item(
                    db,
                    user=user,
                    normalized=normalized,
                    item=item,
                    record_date=record_date,
                    raw_input_text=data.raw_input_text,
                    raw_summary=data.raw_summary,
                )
                db.add(meal)
                meals.append(meal)
                confirmed_candidates.append(candidate)
                warnings_summary.extend(candidate.warnings)
            except ValueError as exc:
                failures.append(
                    IntakeConfirmFailure(
                        draft_id=item.draft_id,
                        food_name=item.food_name,
                        reason=str(exc),
                    )
                )

        if meals:
            await db.flush()
            for meal in meals:
                await db.refresh(meal)

        await self._write_parse_audit(
            db,
            route_name="/api/intake/confirm",
            user_id=user.id,
            query_excerpt=data.raw_input_text or data.raw_summary or data.source.value,
            candidates=confirmed_candidates,
        )

        return IntakeConfirmResponse(
            meals=[MealResponse.model_validate(meal) for meal in meals],
            meal_ids=[meal.id for meal in meals],
            warning_summary=self._unique(warnings_summary),
            failed_items=failures,
        )

    async def _candidate_from_voice_segment(
        self,
        db: AsyncSession,
        *,
        user: User,
        normalized: NormalizedConditions,
        segment: str,
        meal_type: MealType,
        time_hint: Optional[str],
    ) -> Optional[IntakeCandidate]:
        raw_segment = segment.strip()
        if not raw_segment:
            return None

        amount_text, normalized_amount, unit, food_text = self._extract_amount(raw_segment)
        food_name = food_text or raw_segment
        matched_food = await self.knowledge_service.matcher.find_by_name_or_code(db, food_name=food_name)
        category = self._resolve_category(food_name, matched_food.category if matched_food else None)
        estimate = self._estimate_from_match_or_hint(
            food_name=food_name,
            matched_food=matched_food,
            category=category,
            normalized_amount=normalized_amount,
            unit=unit,
        )
        decision = await self.knowledge_service.evaluate_food(
            db,
            normalized=normalized,
            food_name=food_name,
            food_code=matched_food.food_code if matched_food else None,
            user=user,
        )
        estimated_fields = estimate["estimated_fields"]
        if normalized_amount is not None:
            estimated_fields = self._unique(["amount", *estimated_fields])

        return IntakeCandidate(
            draft_id=str(uuid.uuid4()),
            source=IntakeSource.VOICE,
            meal_type=meal_type,
            category=category,
            food_name=food_name,
            food_code=matched_food.food_code if matched_food else None,
            amount_text=amount_text,
            normalized_amount=normalized_amount,
            unit=unit,
            time_hint=time_hint,
            confidence=0.9 if matched_food else 0.62,
            calories=estimate["nutrition"].get("calories"),
            protein=estimate["nutrition"].get("protein"),
            carbs=estimate["nutrition"].get("carbs"),
            fat=estimate["nutrition"].get("fat"),
            fiber=estimate["nutrition"].get("fiber"),
            sodium=estimate["nutrition"].get("sodium"),
            sugar=estimate["nutrition"].get("sugar"),
            purine=estimate["nutrition"].get("purine"),
            allergen_tags=list(matched_food.allergen_tags_json or []) if matched_food else [],
            risk_tags=list(matched_food.risk_tags_json or []) if matched_food else [],
            estimated_fields=estimated_fields,
            estimated_notes=estimate["estimated_notes"],
            local_rule_hit=bool(decision.matched_disease_codes or decision.hard_blocks),
            matched_disease_codes=decision.matched_disease_codes,
            recommendation_level=decision.recommendation_level,
            warnings=self._build_warnings(decision),
            citations=decision.citations,
            origin=decision.origin,
            fallback_status=decision.fallback_status,
            conflict_note=decision.conflict_note,
            caution_note=decision.caution_note,
        )

    async def _candidate_from_photo_food(
        self,
        db: AsyncSession,
        *,
        user: User,
        normalized: NormalizedConditions,
        food,
        meal_type: MealType,
        time_hint: Optional[str],
    ) -> IntakeCandidate:
        amount_text, normalized_amount, unit, _ = self._extract_amount(food.estimated_portion or "1份")
        matched_food = await self.knowledge_service.matcher.find_by_name_or_code(db, food_name=food.food_name)
        category = self._resolve_category(food.food_name, matched_food.category if matched_food else food.category)
        decision = await self.knowledge_service.evaluate_food(
            db,
            normalized=normalized,
            food_name=food.food_name,
            food_code=matched_food.food_code if matched_food else None,
            user=user,
        )
        warnings = self._unique([*(food.warnings or []), *self._build_warnings(decision)])
        risk_tags = list(food.risk_tags or [])
        if matched_food and matched_food.risk_tags_json:
            risk_tags = self._unique([*risk_tags, *matched_food.risk_tags_json])
        allergen_tags = list(food.allergen_tags or [])
        if matched_food and matched_food.allergen_tags_json:
            allergen_tags = self._unique([*allergen_tags, *matched_food.allergen_tags_json])

        return IntakeCandidate(
            draft_id=str(uuid.uuid4()),
            source=IntakeSource.PHOTO,
            meal_type=meal_type,
            category=category,
            food_name=food.food_name,
            food_code=matched_food.food_code if matched_food else None,
            amount_text=amount_text,
            normalized_amount=normalized_amount,
            unit=unit,
            time_hint=time_hint,
            confidence=float(food.confidence or 0),
            ingredients=list(food.ingredients or []),
            cooking_method=food.cooking_method,
            calories=food.nutrition.calories,
            protein=food.nutrition.protein,
            carbs=food.nutrition.carbs,
            fat=food.nutrition.fat,
            fiber=food.nutrition.fiber,
            sodium=food.nutrition.sodium,
            sugar=food.nutrition.sugar,
            purine=food.nutrition.purine,
            allergen_tags=allergen_tags,
            risk_tags=risk_tags,
            estimated_fields=self._unique(
                ["amount", "calories", "sodium", "purine", "protein", "carbs", "fat", "fiber"]
                + (["sugar"] if food.nutrition.sugar is not None else [])
            ),
            estimated_notes=[
                "分量来自图片识别估算。",
                "营养值来自图片识别估算，非实验室精确测量。",
            ],
            local_rule_hit=bool(decision.matched_disease_codes or decision.hard_blocks),
            matched_disease_codes=decision.matched_disease_codes,
            recommendation_level=decision.recommendation_level,
            warnings=warnings,
            citations=decision.citations,
            origin=decision.origin,
            fallback_status=decision.fallback_status,
            conflict_note=decision.conflict_note,
            caution_note=decision.caution_note,
        )

    async def _meal_from_confirm_item(
        self,
        db: AsyncSession,
        *,
        user: User,
        normalized: NormalizedConditions,
        item: IntakeConfirmItem,
        record_date: date,
        raw_input_text: Optional[str],
        raw_summary: Optional[str],
    ) -> tuple[Meal, IntakeCandidate]:
        food_name = item.food_name.strip()
        if not food_name:
            raise ValueError("食物名称不能为空")

        matched_food = await self.knowledge_service.matcher.find_by_name_or_code(
            db,
            food_name=food_name,
            food_code=item.food_code,
        )
        category = item.category or self._resolve_category(food_name, matched_food.category if matched_food else None)
        amount_text = self._compose_amount_text(item.amount_text, item.normalized_amount, item.unit)
        decision = await self.knowledge_service.evaluate_food(
            db,
            normalized=normalized,
            food_name=food_name,
            food_code=matched_food.food_code if matched_food else item.food_code,
            user=user,
        )
        estimate = self._estimate_from_confirm_item(item, matched_food, category)
        warnings = self._unique([*item.warnings, *self._build_warnings(decision)])

        candidate = IntakeCandidate(
            draft_id=item.draft_id,
            source=item.source,
            meal_type=item.meal_type,
            category=category,
            food_name=food_name,
            food_code=matched_food.food_code if matched_food else item.food_code,
            amount_text=amount_text,
            normalized_amount=item.normalized_amount,
            unit=item.unit,
            note=item.note,
            confidence=float(item.confidence or 0),
            ingredients=item.ingredients,
            cooking_method=item.cooking_method,
            calories=estimate["nutrition"].get("calories"),
            protein=estimate["nutrition"].get("protein"),
            carbs=estimate["nutrition"].get("carbs"),
            fat=estimate["nutrition"].get("fat"),
            fiber=estimate["nutrition"].get("fiber"),
            sodium=estimate["nutrition"].get("sodium"),
            sugar=estimate["nutrition"].get("sugar"),
            purine=estimate["nutrition"].get("purine"),
            allergen_tags=item.allergen_tags,
            risk_tags=self._unique([*item.risk_tags, *(matched_food.risk_tags_json if matched_food else [])]),
            estimated_fields=estimate["estimated_fields"],
            estimated_notes=estimate["estimated_notes"],
            local_rule_hit=bool(decision.matched_disease_codes or decision.hard_blocks),
            matched_disease_codes=decision.matched_disease_codes,
            recommendation_level=decision.recommendation_level,
            warnings=warnings,
            citations=decision.citations,
            origin=decision.origin,
            fallback_status=decision.fallback_status,
            conflict_note=decision.conflict_note,
            caution_note=decision.caution_note,
        )
        meal = Meal(
            user_id=user.id,
            client_id=str(uuid.uuid4()),
            name=food_name,
            portion=amount_text,
            calories=estimate["nutrition"].get("calories") or 0,
            sodium=estimate["nutrition"].get("sodium") or 0,
            purine=estimate["nutrition"].get("purine") or 0,
            protein=estimate["nutrition"].get("protein"),
            carbs=estimate["nutrition"].get("carbs"),
            fat=estimate["nutrition"].get("fat"),
            fiber=estimate["nutrition"].get("fiber"),
            meal_type=item.meal_type,
            category=category,
            record_date=record_date,
            note=item.note,
            ai_recognized=item.source in {IntakeSource.PHOTO, IntakeSource.AI_QUICK_LOG},
            source=item.source.value,
            source_detail=self._source_detail(item.source),
            confidence=item.confidence,
            estimated_fields_json=estimate["estimated_fields"],
            rule_warnings_json=warnings,
            recognition_meta_json={
                "food_code": matched_food.food_code if matched_food else item.food_code,
                "normalized_amount": item.normalized_amount,
                "unit": item.unit,
                "ingredients": item.ingredients,
                "cooking_method": item.cooking_method,
                "origin": decision.origin.value,
                "fallback_status": decision.fallback_status.value,
                "citations": [citation.model_dump() for citation in decision.citations],
                "risk_tags": self._unique([*item.risk_tags, *(matched_food.risk_tags_json if matched_food else [])]),
                "allergen_tags": item.allergen_tags,
                "estimated_notes": estimate["estimated_notes"],
                "sugar": estimate["nutrition"].get("sugar"),
                "raw_input_excerpt": (raw_input_text or "")[:300] or None,
                "raw_summary_excerpt": (raw_summary or "")[:300] or None,
            },
            sync_status=SyncStatus.SYNCED,
        )
        return meal, candidate

    def _estimate_from_confirm_item(self, item: IntakeConfirmItem, matched_food, category: FoodCategory) -> dict:
        if any(
            value is not None
            for value in (
                item.calories,
                item.protein,
                item.carbs,
                item.fat,
                item.fiber,
                item.sodium,
                item.purine,
                item.sugar,
            )
        ):
            return {
                "nutrition": {
                    "calories": item.calories,
                    "protein": item.protein,
                    "carbs": item.carbs,
                    "fat": item.fat,
                    "fiber": item.fiber,
                    "sodium": item.sodium,
                    "purine": item.purine,
                    "sugar": item.sugar,
                },
                "estimated_fields": item.estimated_fields or self._infer_estimated_fields_from_values(item),
                "estimated_notes": item.estimated_notes or ["本次记录保留了候选确认时的估算结果。"],
            }
        return self._estimate_from_match_or_hint(
            food_name=item.food_name,
            matched_food=matched_food,
            category=category,
            normalized_amount=item.normalized_amount,
            unit=item.unit,
        )

    def _estimate_from_match_or_hint(
        self,
        *,
        food_name: str,
        matched_food,
        category: FoodCategory,
        normalized_amount: Optional[float],
        unit: Optional[str],
    ) -> dict:
        if matched_food is not None:
            multiplier = self._amount_multiplier(normalized_amount, unit, matched_food.common_units_json or [])
            nutrition = {
                "calories": self._round_optional(matched_food.calories_per_100g, multiplier),
                "protein": self._round_optional(matched_food.protein_per_100g, multiplier),
                "carbs": self._round_optional(matched_food.carbs_per_100g, multiplier),
                "fat": self._round_optional(matched_food.fat_per_100g, multiplier),
                "fiber": self._round_optional(matched_food.fiber_per_100g, multiplier),
                "sodium": self._round_optional(matched_food.sodium_per_100g, multiplier),
                "purine": self._round_optional(matched_food.purine_per_100g, multiplier),
                "sugar": None,
            }
            return {
                "nutrition": nutrition,
                "estimated_fields": self._unique(["calories", "protein", "carbs", "fat", "fiber", "sodium", "purine"]),
                "estimated_notes": ["基于本地食物骨架与份量规则估算。"],
            }

        hint = self._match_common_food_hint(food_name)
        if hint is not None:
            multiplier = self._amount_multiplier(normalized_amount, unit, [], default_unit_weight=hint["grams_per_unit"])
            nutrition = {field: self._round_optional(value, multiplier) for field, value in hint["nutrition_per_100g"].items()}
            nutrition["sugar"] = None
            return {
                "nutrition": nutrition,
                "estimated_fields": self._unique(["calories", "protein", "carbs", "fat", "fiber", "sodium", "purine"]),
                "estimated_notes": ["未命中知识库，使用通用食物估算。"],
            }

        generic = GENERIC_CATEGORY_HINTS[category]
        multiplier = self._amount_multiplier(normalized_amount, unit, [])
        nutrition = {field: self._round_optional(value, multiplier) for field, value in generic.items()}
        nutrition["sugar"] = None
        return {
            "nutrition": nutrition,
            "estimated_fields": self._unique(["calories", "protein", "carbs", "fat", "fiber", "sodium", "purine"]),
            "estimated_notes": ["未命中知识库，使用分类级通用估算。"],
        }

    def _split_voice_segments(self, transcript: str) -> list[str]:
        cleaned = transcript.strip()
        if not cleaned:
            return []
        parts = [self._clean_segment(part) for part in SEPARATOR_PATTERN.split(cleaned)]
        return [part for part in parts if part]

    def _clean_segment(self, segment: str) -> str:
        stripped = segment.strip(" 。.!！？?，,、；;")
        stripped = LEADING_CONTEXT_PATTERN.sub("", stripped)
        return stripped.strip()

    def _infer_meal_type(self, text: str, meal_time_hint: Optional[str]) -> MealType:
        haystack = f"{meal_time_hint or ''} {text or ''}"
        for meal_type, keywords in MEAL_TYPE_HINTS:
            if any(keyword in haystack for keyword in keywords):
                return meal_type
        current_hour = datetime.now().hour
        if current_hour < 10:
            return MealType.BREAKFAST
        if current_hour < 14:
            return MealType.LUNCH
        if current_hour < 21:
            return MealType.DINNER
        return MealType.SNACK

    def _detect_time_hint(self, text: str) -> Optional[str]:
        for _, keywords in MEAL_TYPE_HINTS:
            for keyword in keywords:
                if keyword in text:
                    return keyword
        return None

    def _extract_amount(self, segment: str) -> tuple[str, Optional[float], Optional[str], str]:
        match = AMOUNT_PATTERN.search(segment)
        if match:
            amount_token = match.group("amount")
            unit = self._normalize_unit(match.group("unit"))
            normalized_amount = self._parse_numeric_token(amount_token)
            food_text = (segment[: match.start()] + segment[match.end() :]).strip()
            food_text = re.sub(r"^(约|大约|差不多|左右|一份|一碗|一杯)", "", food_text).strip()
            return match.group(0).strip(), normalized_amount, unit, food_text

        if segment.startswith(("少量", "一点")):
            return "少量", None, "份", segment[2:].strip()

        return "1份", None, "份", segment.strip()

    def _normalize_unit(self, unit: Optional[str]) -> Optional[str]:
        if unit in {"ml", "mL"}:
            return "ml"
        if unit == "g":
            return "g"
        return unit

    def _parse_numeric_token(self, token: str) -> Optional[float]:
        if not token:
            return None
        try:
            return float(token)
        except ValueError:
            return NUMBER_WORDS.get(token)

    def _resolve_category(self, food_name: str, raw_category: Optional[str]) -> FoodCategory:
        if raw_category:
            normalized = str(raw_category).upper()
            if normalized in CATEGORY_ALIAS_MAP:
                return CATEGORY_ALIAS_MAP[normalized]
        if any(keyword in food_name for keyword in ("豆浆", "牛奶", "酸奶", "可乐", "汽水", "啤酒", "茶", "水")):
            return FoodCategory.DRINK
        if any(keyword in food_name for keyword in ("米饭", "面", "燕麦", "玉米", "粥", "包子")):
            return FoodCategory.STAPLE
        if any(keyword in food_name for keyword in ("菜", "黄瓜", "西兰花", "菠菜", "苹果", "梨", "香蕉")):
            return FoodCategory.VEG
        if any(keyword in food_name for keyword in ("薯片", "蛋糕", "方便面", "饼干")):
            return FoodCategory.SNACK
        return FoodCategory.MEAT

    def _amount_multiplier(
        self,
        normalized_amount: Optional[float],
        unit: Optional[str],
        common_units: list[str],
        default_unit_weight: Optional[float] = None,
    ) -> float:
        if normalized_amount is None:
            return 1.0
        normalized_unit = self._normalize_unit(unit) if unit else None
        if normalized_unit in {"g", "克", "ml", "毫升"}:
            return normalized_amount / 100.0
        base_weight = UNIT_BASE_WEIGHTS.get(normalized_unit or "", default_unit_weight or 100.0)
        if common_units:
            first_unit = common_units[0]
            match = re.match(r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>\D+)", first_unit)
            if match and match.group("unit").strip() in {"g", "克", "ml", "毫升"}:
                base_weight = float(match.group("amount"))
        return (normalized_amount * base_weight) / 100.0

    def _match_common_food_hint(self, food_name: str) -> Optional[dict]:
        for hint in COMMON_FOOD_HINTS.values():
            if any(alias in food_name for alias in hint["aliases"]):
                return hint
        return None

    def _compose_amount_text(
        self,
        raw_amount_text: Optional[str],
        normalized_amount: Optional[float],
        unit: Optional[str],
    ) -> str:
        if normalized_amount is not None and unit:
            amount = int(normalized_amount) if float(normalized_amount).is_integer() else round(normalized_amount, 1)
            return f"{amount}{unit}"
        if raw_amount_text:
            return raw_amount_text
        return "1份"

    def _build_warnings(self, decision: LocalDecision) -> list[str]:
        warnings: list[str] = []
        if decision.recommendation_level in {RecommendationLevel.AVOID, RecommendationLevel.LIMIT}:
            warnings.append(f"本地规则：{decision.food_name} -> {decision.recommendation_level.value}")
        warnings.extend(decision.hard_blocks)
        if decision.caution_note:
            warnings.append(decision.caution_note)
        if decision.conflict_note:
            warnings.append(decision.conflict_note)
        return self._unique(warnings)

    def _build_session_warning(self, candidates: list[IntakeCandidate]) -> Optional[str]:
        if not candidates:
            return "未解析出可确认的候选项，请手动补充后再记账。"
        if any(candidate.warnings for candidate in candidates):
            return "存在本地规则命中项，请在确认前检查 warning。"
        if any(candidate.fallback_status == FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD for candidate in candidates):
            return "部分食物未命中本地知识库，已按可确认候选返回，请人工核对。"
        return None

    async def _write_parse_audit(
        self,
        db: AsyncSession,
        *,
        route_name: str,
        user_id: int,
        query_excerpt: str,
        candidates: list[IntakeCandidate],
    ) -> None:
        if not candidates:
            await write_knowledge_audit_log(
                db,
                user_id=user_id,
                route_name=route_name,
                query_excerpt=query_excerpt,
                origin=KnowledgeOrigin.LOCAL_KNOWLEDGE,
                fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
                matched_disease_codes=[],
                matched_food_codes=[],
                called_cloud=False,
                cloud_blocked_reason="仅进行本地候选解析。",
            )
            return

        strictest_level = None
        strictest_fallback = FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD
        origins: list[KnowledgeOrigin] = []
        matched_disease_codes: list[str] = []
        matched_food_codes: list[str] = []
        for candidate in candidates:
            if candidate.recommendation_level is not None:
                strictest_level = self._pick_stricter_level(strictest_level, candidate.recommendation_level)
            if FALLBACK_PRIORITY[candidate.fallback_status] > FALLBACK_PRIORITY[strictest_fallback]:
                strictest_fallback = candidate.fallback_status
            origins.append(candidate.origin)
            matched_disease_codes.extend(candidate.matched_disease_codes)
            if candidate.food_code:
                matched_food_codes.append(candidate.food_code)

        if any(origin == KnowledgeOrigin.LOCAL_RULE for origin in origins):
            origin = KnowledgeOrigin.LOCAL_RULE
        elif any(origin == KnowledgeOrigin.MIXED for origin in origins):
            origin = KnowledgeOrigin.MIXED
        else:
            origin = origins[0]

        await write_knowledge_audit_log(
            db,
            user_id=user_id,
            route_name=route_name,
            query_excerpt=query_excerpt,
            origin=origin,
            fallback_status=strictest_fallback,
            matched_disease_codes=self._unique(matched_disease_codes),
            matched_food_codes=self._unique(matched_food_codes),
            local_decision_level=strictest_level,
            called_cloud=False,
            cloud_blocked_reason="仅进行本地候选解析与规则校验。",
        )

    def _infer_estimated_fields_from_values(self, item: IntakeConfirmItem) -> list[str]:
        fields = []
        for field_name in ("calories", "protein", "carbs", "fat", "fiber", "sodium", "sugar", "purine"):
            if getattr(item, field_name) is not None:
                fields.append(field_name)
        if item.normalized_amount is not None:
            fields.append("amount")
        return fields

    def _pick_stricter_level(
        self,
        current: Optional[RecommendationLevel],
        candidate: RecommendationLevel,
    ) -> RecommendationLevel:
        if current is None:
            return candidate
        return candidate if STRICTNESS_ORDER[candidate] > STRICTNESS_ORDER[current] else current

    def _source_detail(self, source: IntakeSource) -> str:
        if source == IntakeSource.VOICE:
            return "voice_parse_v1"
        if source == IntakeSource.PHOTO:
            return "photo_parse_v1"
        if source == IntakeSource.AI_QUICK_LOG:
            return "ai_quick_log"
        return "manual_entry"

    def _round_optional(self, value: Optional[float], multiplier: float) -> Optional[float]:
        if value is None:
            return None
        return round(value * multiplier, 1)

    def _unique(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            if item and item not in seen:
                seen.add(item)
                result.append(item)
        return result
