"""Multimodal intake parsing and confirmation service."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_sensitive_value
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
    IntakeParseStatus,
    IntakeSource,
    PhotoParseRequest,
    TextParseRequest,
    VoiceAutoLogRequest,
    VoiceParseRequest,
)
from app.schemas.meal import MealResponse
from app.services.knowledge import KnowledgeService, write_knowledge_audit_log
from app.services.knowledge.contracts import LocalDecision, NormalizedConditions
from app.services.knowledge.matcher import normalize_food_text


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
    r"(?P<amount>(?:\d+(?:\.\d+)?)|半|两|一|二|三|四|五|六|七|八|九|十)\s*(?P<unit>毫升|ml|mL|克|g|杯|碗|个|根|份|包|瓶|听|块)"
)

FUZZY_AMOUNT_PATTERN = re.compile(
    r"(?P<amount>小半|一小|一大|几)\s*(?P<unit>碗|杯|份|块|口)"
)

TASTE_CUE_PATTERN = re.compile(
    r"(有点咸|偏咸|比较咸|清淡|很淡|偏淡|有点淡|淡一点)"
)

SEPARATOR_PATTERN = re.compile(
    r"[，,、；;]|(?:\s*和\s*)|(?:\s*以及\s*)|(?:\s*还有\s*)|(?:\s*外加\s*)|(?:\s*加上\s*)"
)

LEADING_CONTEXT_PATTERN = re.compile(
    r"^(今天|今日|刚才|刚刚|我|上午|下午|早上|早晨|中午|晚上|早餐|午餐|晚餐|加餐|夜宵|早饭|午饭|晚饭|吃了|喝了|吃|喝)+"
)

TEXT_LOG_PREFIXES = (
    "帮我记录一下",
    "帮我记录",
    "帮我记一下",
    "帮我记",
    "麻烦记录一下",
    "麻烦记录",
    "麻烦记一下",
    "麻烦记",
    "请记录一下",
    "请记录",
    "请记一下",
    "请记",
    "记录一下",
    "记录",
    "记一下",
    "记个",
    "记上",
    "录入一下",
    "录入",
    "登记一下",
    "登记",
    "添加",
)

TEXT_LOG_INTENT_KEYWORDS = (
    "记录",
    "记一下",
    "记个",
    "记上",
    "帮我记",
    "帮我记录",
    "录入",
    "登记",
    "添加到饮食",
    "log",
)

TEXT_MEAL_LOG_KEYWORDS = (
    "吃了",
    "喝了",
    "吃过",
    "喝过",
    "刚吃",
    "刚喝",
    "早餐",
    "午餐",
    "晚餐",
    "加餐",
    "夜宵",
    "早饭",
    "午饭",
    "晚饭",
)

TEXT_NON_LOG_KEYWORDS = (
    "能不能",
    "可以吗",
    "适合",
    "推荐",
    "建议",
    "怎么吃",
    "吃什么",
    "喝什么",
    "为什么",
    "为何",
    "热量",
    "卡路里",
    "营养",
    "?",
    "？",
)

GENERIC_FOOD_SEGMENTS = {
    "早餐",
    "午餐",
    "晚餐",
    "加餐",
    "夜宵",
    "早饭",
    "午饭",
    "晚饭",
    "饭",
    "菜",
    "东西",
    "食物",
    "这顿",
    "这餐",
    "一顿",
    "一点东西",
    "点东西",
}

GENERIC_CATEGORY_HINTS = {
    FoodCategory.STAPLE: {
        "calories": 116.0,
        "protein": 2.6,
        "carbs": 25.9,
        "fat": 0.3,
        "fiber": 0.5,
        "sodium": 4.0,
        "purine": 12.0,
    },
    FoodCategory.MEAT: {
        "calories": 165.0,
        "protein": 22.0,
        "carbs": 1.0,
        "fat": 8.0,
        "fiber": 0.0,
        "sodium": 80.0,
        "purine": 120.0,
    },
    FoodCategory.VEG: {
        "calories": 30.0,
        "protein": 2.0,
        "carbs": 5.0,
        "fat": 0.3,
        "fiber": 2.0,
        "sodium": 20.0,
        "purine": 15.0,
    },
    FoodCategory.DRINK: {
        "calories": 20.0,
        "protein": 1.0,
        "carbs": 3.0,
        "fat": 0.5,
        "fiber": 0.0,
        "sodium": 15.0,
        "purine": 2.0,
    },
    FoodCategory.SNACK: {
        "calories": 300.0,
        "protein": 5.0,
        "carbs": 35.0,
        "fat": 14.0,
        "fiber": 1.0,
        "sodium": 240.0,
        "purine": 18.0,
    },
}

COMMON_FOOD_HINTS = {
    "鸡蛋": {
        "aliases": ("鸡蛋", "水煮蛋", "煎蛋", "蛋"),
        "category": FoodCategory.MEAT,
        "grams_per_unit": 50.0,
        "nutrition_per_100g": {
            "calories": 144.0,
            "protein": 13.0,
            "carbs": 1.1,
            "fat": 10.0,
            "fiber": 0.0,
            "sodium": 140.0,
            "purine": 10.0,
        },
    },
    "玉米": {
        "aliases": ("玉米", "甜玉米", "玉米棒"),
        "category": FoodCategory.STAPLE,
        "grams_per_unit": 120.0,
        "nutrition_per_100g": {
            "calories": 112.0,
            "protein": 3.6,
            "carbs": 22.8,
            "fat": 1.5,
            "fiber": 2.9,
            "sodium": 1.0,
            "purine": 16.0,
        },
    },
    "排骨": {
        "aliases": ("排骨", "红烧排骨", "糖醋排骨"),
        "category": FoodCategory.MEAT,
        "grams_per_unit": 100.0,
        "nutrition_per_100g": {
            "calories": 260.0,
            "protein": 17.0,
            "carbs": 6.0,
            "fat": 18.0,
            "fiber": 0.0,
            "sodium": 180.0,
            "purine": 135.0,
        },
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
    "口": 15.0,
}

NUMBER_WORDS = {
    "半": 0.5,
    "一": 1.0,
    "二": 2.0,
    "两": 2.0,
    "三": 3.0,
    "四": 4.0,
    "五": 5.0,
    "六": 6.0,
    "七": 7.0,
    "八": 8.0,
    "九": 9.0,
    "十": 10.0,
}

FUZZY_AMOUNT_VALUES = {
    "小半": 0.4,
    "一小": 0.75,
    "一大": 1.5,
    "少量": 0.25,
    "一点": 0.2,
}

FUZZY_UNIT_COUNTS = {
    ("几", "口"): 2.0,
    ("几", "块"): 3.0,
    ("几", "份"): 1.5,
    ("几", "碗"): 2.0,
    ("几", "杯"): 2.0,
}

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

PREP_HIGH_SODIUM_TERMS = (
    "酱油",
    "生抽",
    "老抽",
    "蚝油",
    "豆瓣酱",
    "黄豆酱",
    "豆豉",
    "腐乳",
    "鱼露",
    "咸菜",
    "榨菜",
    "腌菜",
    "腌制",
    "盐焗",
    "卤",
    "火锅底料",
    "麻辣锅底",
    "牛油锅底",
)

PREP_HIGH_SUGAR_TERMS = (
    "白糖",
    "冰糖",
    "砂糖",
    "红糖",
    "蜂蜜",
    "糖醋",
    "甜酱",
    "炼乳",
    "焦糖",
)

PREP_HIGH_FAT_TERMS = (
    "油炸",
    "煎炸",
    "炸",
    "油煎",
    "干煸",
    "油焖",
    "红烧",
    "烧烤",
    "奶油",
    "黄油",
    "牛油锅底",
)

PREP_ULTRA_PROCESSED_TERMS = (
    "火锅底料",
    "麻辣锅底",
    "牛油锅底",
    "方便酱包",
    "复合调味料",
)

PREP_ALLERGEN_TERMS: dict[str, tuple[str, ...]] = {
    "peanut": ("花生", "花生米", "花生碎", "花生酱", "peanut", "peanuts"),
    "seafood": ("海鲜", "鱼露", "虾", "虾仁", "虾皮", "蟹", "螃蟹", "贝类", "鱼肉", "seafood"),
    "shellfish": ("虾", "虾仁", "虾皮", "蟹", "螃蟹", "贝类", "shellfish", "shrimp", "crab"),
    "dairy": ("牛奶", "奶油", "黄油", "芝士", "奶酪", "乳制品", "炼乳", "dairy", "milk"),
    "egg": ("鸡蛋", "蛋液", "蛋黄", "蛋清", "蛋", "egg"),
    "soy": ("酱油", "生抽", "老抽", "豆瓣酱", "黄豆酱", "豆豉", "豆腐", "黄豆", "大豆", "soy"),
    "wheat": ("小麦", "面粉", "麸质", "面包糠", "wheat", "gluten"),
}

PREP_ALLERGEN_DISPLAY = {
    "peanut": "花生",
    "seafood": "海鲜",
    "shellfish": "贝类/甲壳类",
    "dairy": "乳制品",
    "egg": "鸡蛋",
    "soy": "大豆",
    "wheat": "小麦",
}

PREP_ALLERGEN_RISK_TAGS = {
    "peanut": ("high_fat", "plant_protein"),
    "seafood": ("seafood", "moderate_purine"),
    "shellfish": ("shellfish", "seafood", "moderate_purine"),
    "dairy": ("dairy",),
    "egg": ("egg", "animal_protein"),
    "soy": ("soy", "plant_protein"),
    "wheat": ("starchy_staple",),
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

    async def parse_text(
        self,
        db: AsyncSession,
        *,
        user: User,
        conditions: list[HealthCondition],
        data: TextParseRequest,
    ) -> IntakeDraftSessionResponse:
        normalized = await self.knowledge_service.normalize_conditions(db, conditions)
        record_date = data.record_date or date.today()
        current_text = data.text.strip()
        context_text = (data.context_text or "").strip()
        current_segments = self._extract_text_food_segments(current_text)
        context_segments = self._extract_text_food_segments(context_text)
        use_context_completion = self._should_use_context_completion(
            current_text=current_text,
            context_text=context_text,
            current_segments=current_segments,
            context_segments=context_segments,
        )
        time_hint = (
            data.meal_time_hint
            or self._detect_time_hint(current_text)
            or self._detect_time_hint(context_text)
        )

        if not self._looks_like_meal_log_text(current_text) and not use_context_completion:
            await self._write_parse_audit(
                db,
                route_name="/api/intake/text/parse",
                user_id=user.id,
                query_excerpt=current_text,
                candidates=[],
            )
            return IntakeDraftSessionResponse(
                source=IntakeSource.AI_QUICK_LOG,
                status=IntakeParseStatus.REFUSED,
                raw_input_text=current_text,
                record_date=record_date,
                meal_time_hint=time_hint,
                refusal_reason="这条消息不像是在记录饮食，我先不生成餐食草稿。",
            )

        meal_type = self._infer_meal_type(
            current_text if current_segments or not context_text else context_text,
            data.meal_time_hint,
        )
        food_segments = current_segments or (context_segments if use_context_completion else [])
        global_taste_notes = self._extract_taste_cues(current_text)[1]
        if not food_segments:
            await self._write_parse_audit(
                db,
                route_name="/api/intake/text/parse",
                user_id=user.id,
                query_excerpt=current_text,
                candidates=[],
            )
            return IntakeDraftSessionResponse(
                source=IntakeSource.AI_QUICK_LOG,
                status=IntakeParseStatus.NEEDS_CLARIFICATION,
                raw_input_text=current_text,
                record_date=record_date,
                meal_time_hint=time_hint,
                missing_fields=["foods"],
                follow_up_prompt="请补充这餐具体吃了什么，我再帮你生成待确认记录。",
            )

        follow_up_detail = self._extract_follow_up_detail(current_text) if use_context_completion else None
        candidates: list[IntakeCandidate] = []
        for segment in food_segments:
            candidate_segment = segment
            note_override = None
            estimated_note_overrides: list[str] = []
            inferred_amount = False

            if follow_up_detail is not None:
                candidate_segment = self._merge_context_food_segment(
                    context_segment=segment,
                    amount_text=follow_up_detail["amount_text"],
                )
                note_override = self._compose_note(follow_up_detail["taste_notes"])
                estimated_note_overrides = self._build_follow_up_estimated_notes(
                    amount_text=follow_up_detail["amount_text"],
                    taste_notes=follow_up_detail["taste_notes"],
                )
                inferred_amount = follow_up_detail["normalized_amount"] is not None
            elif len(food_segments) == 1 and global_taste_notes:
                note_override = self._compose_note(global_taste_notes)

            candidate = await self._candidate_from_voice_segment(
                db,
                user=user,
                normalized=normalized,
                segment=candidate_segment,
                meal_type=meal_type,
                time_hint=time_hint,
                source=IntakeSource.AI_QUICK_LOG,
                note_override=note_override,
                estimated_note_overrides=estimated_note_overrides,
                inferred_amount=inferred_amount,
            )
            if candidate is not None:
                candidates.append(candidate)

        if not candidates:
            await self._write_parse_audit(
                db,
                route_name="/api/intake/text/parse",
                user_id=user.id,
                query_excerpt=current_text,
                candidates=[],
            )
            return IntakeDraftSessionResponse(
                source=IntakeSource.AI_QUICK_LOG,
                status=IntakeParseStatus.NEEDS_CLARIFICATION,
                raw_input_text=current_text,
                record_date=record_date,
                meal_time_hint=time_hint,
                missing_fields=["foods"],
                follow_up_prompt="请补充这餐具体吃了什么，我再帮你生成待确认记录。",
            )

        await self._write_parse_audit(
            db,
            route_name="/api/intake/text/parse",
            user_id=user.id,
            query_excerpt=current_text,
            candidates=candidates,
        )

        return IntakeDraftSessionResponse(
            source=IntakeSource.AI_QUICK_LOG,
            status=IntakeParseStatus.READY,
            raw_input_text=current_text,
            record_date=record_date,
            meal_time_hint=time_hint,
            candidates=candidates,
            summary_warning=self._build_session_warning(candidates),
        )

    async def voice_auto_log(
        self,
        db: AsyncSession,
        *,
        user: User,
        conditions: list[HealthCondition],
        data: VoiceAutoLogRequest,
    ) -> IntakeConfirmResponse:
        """
        语音自动录入。

        传入前端语音识别后的 transcript：
        1. 先复用 parse_voice 生成候选项；
        2. 再复用 confirm 自动写入饮食日志；
        3. 返回最终写入结果。
        """
        if not data.auto_confirm:
            raise ValueError("语音自动录入需要 auto_confirm=true")

        draft = await self.parse_voice(
            db,
            user=user,
            conditions=conditions,
            data=VoiceParseRequest(
                transcript=data.transcript,
                meal_time_hint=data.meal_time_hint,
                record_date=data.record_date,
            ),
        )

        if not draft.candidates:
            raise ValueError("未从语音内容中解析出可记录的饮食项，请补充食物名称、分量或餐次。")

        confirm_items = [
            IntakeConfirmItem.model_validate(candidate.model_dump())
            for candidate in draft.candidates
        ]

        result = await self.confirm(
            db,
            user=user,
            conditions=conditions,
            data=IntakeConfirmRequest(
                source=IntakeSource.VOICE,
                raw_input_text=draft.raw_input_text or data.transcript,
                raw_summary=draft.raw_summary,
                record_date=draft.record_date,
                candidates=confirm_items,
            ),
        )

        await self._write_parse_audit(
            db,
            route_name="/api/intake/voice/auto-log",
            user_id=user.id,
            query_excerpt=data.transcript,
            candidates=draft.candidates,
        )

        return result

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

        strictest_fallback = max(
            (candidate.fallback_status for candidate in candidates),
            key=lambda value: FALLBACK_PRIORITY[value],
            default=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
        )
        reviewed_summary = self.knowledge_service.enforce_llm_output_safety(
            data.ai_response,
            local_decisions=candidates,
            fallback_status=strictest_fallback,
            context_label="图片识别摘要",
        )

        await self._write_parse_audit(
            db,
            route_name="/api/intake/photo/parse-result",
            user_id=user.id,
            query_excerpt=reviewed_summary or "recognized_foods",
            candidates=candidates,
        )

        return IntakeDraftSessionResponse(
            source=IntakeSource.PHOTO,
            raw_summary=reviewed_summary,
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

    async def reevaluate_confirm_item(
        self,
        db: AsyncSession,
        *,
        user: User,
        conditions: list[HealthCondition],
        item: IntakeConfirmItem,
    ) -> IntakeCandidate:
        normalized = await self.knowledge_service.normalize_conditions(db, conditions)
        return await self._candidate_from_confirm_item(
            db,
            user=user,
            normalized=normalized,
            item=item,
            recompute_nutrition=True,
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
        source: IntakeSource = IntakeSource.VOICE,
        note_override: Optional[str] = None,
        estimated_note_overrides: Optional[list[str]] = None,
        inferred_amount: bool = False,
    ) -> Optional[IntakeCandidate]:
        raw_segment = segment.strip()
        if not raw_segment:
            return None

        cleaned_segment, inline_taste_notes = self._extract_taste_cues(raw_segment)
        amount_text, normalized_amount, unit, food_text = self._extract_amount(cleaned_segment)
        food_name = (food_text or cleaned_segment).strip()
        note = self._compose_note([*inline_taste_notes, *(note_override and [note_override] or [])])

        matched_food = await self.knowledge_service.matcher.find_by_name_or_code(
            db,
            food_name=food_name,
        )

        category = self._resolve_category(
            food_name,
            matched_food.category if matched_food else None,
        )

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
        estimated_notes = list(estimate["estimated_notes"])
        if normalized_amount is not None:
            estimated_fields = self._unique(["amount", *estimated_fields])
        if inferred_amount:
            estimated_notes.append(f"分量根据补充回答按“{amount_text}”估算。")
        if estimated_note_overrides:
            estimated_notes.extend(estimated_note_overrides)

        return IntakeCandidate(
            draft_id=str(uuid.uuid4()),
            source=source,
            meal_type=meal_type,
            category=category,
            food_name=food_name,
            food_code=matched_food.food_code if matched_food else None,
            amount_text=amount_text,
            normalized_amount=normalized_amount,
            unit=unit,
            time_hint=time_hint,
            note=note,
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
            estimated_notes=self._unique(estimated_notes),
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
        amount_text, normalized_amount, unit, _ = self._extract_amount(
            food.estimated_portion or "1份"
        )

        matched_food = await self.knowledge_service.matcher.find_by_name_or_code(
            db,
            food_name=food.food_name,
        )

        category = self._resolve_category(
            food.food_name,
            matched_food.category if matched_food else food.category,
        )

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
            seasonings=[],
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
                [
                    "amount",
                    "calories",
                    "sodium",
                    "purine",
                    "protein",
                    "carbs",
                    "fat",
                    "fiber",
                ]
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

    async def _candidate_from_confirm_item(
        self,
        db: AsyncSession,
        *,
        user: User,
        normalized: NormalizedConditions,
        item: IntakeConfirmItem,
        recompute_nutrition: bool = False,
    ) -> IntakeCandidate:
        food_name = item.food_name.strip()
        if not food_name:
            raise ValueError("食物名称不能为空")

        matched_food = await self.knowledge_service.matcher.find_by_name_or_code(
            db,
            food_name=food_name,
            food_code=item.food_code,
        )

        category = item.category or self._resolve_category(
            food_name,
            matched_food.category if matched_food else None,
        )

        amount_text = self._compose_amount_text(
            item.amount_text,
            item.normalized_amount,
            item.unit,
        )

        decision = await self.knowledge_service.evaluate_food(
            db,
            normalized=normalized,
            food_name=food_name,
            food_code=matched_food.food_code if matched_food else item.food_code,
            manual_restrictions=item.manual_restrictions,
            user=user,
        )

        if recompute_nutrition:
            estimate = self._estimate_from_match_or_hint(
                food_name=food_name,
                matched_food=matched_food,
                category=category,
                normalized_amount=item.normalized_amount,
                unit=item.unit,
            )
        else:
            estimate = self._estimate_from_confirm_item(item, matched_food, category)

        matched_allergen_tags = list(matched_food.allergen_tags_json or []) if matched_food else []
        matched_risk_tags = list(matched_food.risk_tags_json or []) if matched_food else []
        warnings = self._build_warnings(decision)
        prep_adjustments = self._build_prep_detail_adjustments(
            item=item,
            estimate=estimate,
            normalized=normalized,
        )

        warnings = self._unique([*warnings, *prep_adjustments["warnings"], *prep_adjustments["hard_blocks"]])
        allergen_tags = self._unique(
            [
                *item.allergen_tags,
                *matched_allergen_tags,
                *prep_adjustments["allergen_tags"],
            ]
        )
        risk_tags = self._unique(
            [
                *item.risk_tags,
                *decision.risk_tags,
                *matched_risk_tags,
                *prep_adjustments["risk_tags"],
            ]
        )
        recommendation_level = decision.recommendation_level
        fallback_status = decision.fallback_status
        origin = decision.origin
        if prep_adjustments["hard_blocks"]:
            recommendation_level = self._pick_stricter_level(
                recommendation_level,
                RecommendationLevel.AVOID,
            )
            fallback_status = FallbackStatus.LOCAL_BLOCKED_NO_CLOUD
            origin = KnowledgeOrigin.LOCAL_RULE

        return IntakeCandidate(
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
            seasonings=item.seasonings,
            calories=prep_adjustments["nutrition"].get("calories"),
            protein=prep_adjustments["nutrition"].get("protein"),
            carbs=prep_adjustments["nutrition"].get("carbs"),
            fat=prep_adjustments["nutrition"].get("fat"),
            fiber=prep_adjustments["nutrition"].get("fiber"),
            sodium=prep_adjustments["nutrition"].get("sodium"),
            sugar=prep_adjustments["nutrition"].get("sugar"),
            purine=prep_adjustments["nutrition"].get("purine"),
            allergen_tags=allergen_tags,
            risk_tags=risk_tags,
            estimated_fields=prep_adjustments["estimated_fields"],
            estimated_notes=prep_adjustments["estimated_notes"],
            local_rule_hit=bool(decision.matched_disease_codes or decision.hard_blocks or prep_adjustments["hard_blocks"]),
            matched_disease_codes=decision.matched_disease_codes,
            recommendation_level=recommendation_level,
            warnings=warnings,
            citations=decision.citations,
            origin=origin,
            fallback_status=fallback_status,
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
        candidate = await self._candidate_from_confirm_item(
            db,
            user=user,
            normalized=normalized,
            item=item,
        )

        meal = Meal(
            user_id=user.id,
            client_id=str(uuid.uuid4()),
            name=candidate.food_name,
            portion=candidate.amount_text,
            calories=candidate.calories or 0,
            sodium=candidate.sodium or 0,
            purine=candidate.purine or 0,
            protein=candidate.protein,
            carbs=candidate.carbs,
            fat=candidate.fat,
            fiber=candidate.fiber,
            meal_type=candidate.meal_type,
            category=candidate.category,
            record_date=record_date,
            note=candidate.note,
            ai_recognized=candidate.source in {IntakeSource.PHOTO, IntakeSource.AI_QUICK_LOG},
            source=candidate.source.value,
            source_detail=self._source_detail(candidate.source),
            confidence=candidate.confidence,
            estimated_fields_json=candidate.estimated_fields,
            rule_warnings_json=candidate.warnings,
            recognition_meta_json={
                "food_code": candidate.food_code,
                "normalized_amount": candidate.normalized_amount,
                "unit": candidate.unit,
                "ingredients": candidate.ingredients,
                "cooking_method": candidate.cooking_method,
                "seasonings": candidate.seasonings,
                "origin": candidate.origin.value,
                "fallback_status": candidate.fallback_status.value,
                "citations": [citation.model_dump() for citation in candidate.citations],
                "risk_tags": candidate.risk_tags,
                "allergen_tags": candidate.allergen_tags,
                "estimated_notes": candidate.estimated_notes,
                "sugar": candidate.sugar,
                "raw_input_hash": hash_sensitive_value(raw_input_text),
                "raw_summary_hash": hash_sensitive_value(raw_summary),
            },
            sync_status=SyncStatus.SYNCED,
        )

        return meal, candidate

    def _estimate_from_confirm_item(
        self,
        item: IntakeConfirmItem,
        matched_food,
        category: FoodCategory,
    ) -> dict:
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
                "estimated_fields": item.estimated_fields
                or self._infer_estimated_fields_from_values(item),
                "estimated_notes": item.estimated_notes
                or ["本次记录保留了候选确认时的估算结果。"],
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
            multiplier = self._amount_multiplier(
                normalized_amount,
                unit,
                matched_food.common_units_json or [],
            )

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
                "estimated_fields": self._unique(
                    ["calories", "protein", "carbs", "fat", "fiber", "sodium", "purine"]
                ),
                "estimated_notes": ["基于本地食物骨架与份量规则估算。"],
            }

        hint = self._match_common_food_hint(food_name)
        if hint is not None:
            multiplier = self._amount_multiplier(
                normalized_amount,
                unit,
                [],
                default_unit_weight=hint["grams_per_unit"],
            )

            nutrition = {
                field: self._round_optional(value, multiplier)
                for field, value in hint["nutrition_per_100g"].items()
            }
            nutrition["sugar"] = None

            return {
                "nutrition": nutrition,
                "estimated_fields": self._unique(
                    ["calories", "protein", "carbs", "fat", "fiber", "sodium", "purine"]
                ),
                "estimated_notes": ["未命中知识库，使用通用食物估算。"],
            }

        generic = GENERIC_CATEGORY_HINTS[category]
        multiplier = self._amount_multiplier(normalized_amount, unit, [])

        nutrition = {
            field: self._round_optional(value, multiplier)
            for field, value in generic.items()
        }
        nutrition["sugar"] = None

        return {
            "nutrition": nutrition,
            "estimated_fields": self._unique(
                ["calories", "protein", "carbs", "fat", "fiber", "sodium", "purine"]
            ),
            "estimated_notes": ["未命中知识库，使用分类级通用估算。"],
        }

    def _split_voice_segments(self, transcript: str) -> list[str]:
        cleaned = transcript.strip()
        if not cleaned:
            return []

        parts = [self._clean_segment(part) for part in SEPARATOR_PATTERN.split(cleaned)]
        return [part for part in parts if part]

    def _clean_segment(self, segment: str) -> str:
        stripped = segment.strip(" 。.!！？?，,、；;:：-")
        stripped = LEADING_CONTEXT_PATTERN.sub("", stripped)
        return stripped.strip()

    def _looks_like_meal_log_text(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text or "")
        if not normalized:
            return False

        explicit_log_intent = any(keyword in normalized for keyword in TEXT_LOG_INTENT_KEYWORDS)
        if explicit_log_intent:
            return True

        if any(keyword in normalized for keyword in TEXT_NON_LOG_KEYWORDS):
            return False

        return any(keyword in normalized for keyword in TEXT_MEAL_LOG_KEYWORDS)

    def _extract_text_food_segments(self, text: str) -> list[str]:
        segments: list[str] = []

        for segment in self._split_voice_segments(text):
            cleaned_segment = self._strip_text_log_prefix(segment)
            if not self._is_specific_food_segment(cleaned_segment):
                continue
            segments.append(cleaned_segment)

        return segments

    def _strip_text_log_prefix(self, segment: str) -> str:
        cleaned = segment.strip(" 。.!！？?，,、；;:：-")

        changed = True
        while changed and cleaned:
            changed = False
            for prefix in TEXT_LOG_PREFIXES:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix) :].strip(" 。.!！？?，,、；;:：-")
                    cleaned = self._clean_segment(cleaned)
                    changed = True

        return cleaned.strip(" 。.!！？?，,、；;:：-")

    def _is_specific_food_segment(self, segment: str) -> bool:
        if not segment:
            return False

        cleaned_segment, _ = self._extract_taste_cues(segment)
        amount_text, _, _, food_name = self._extract_amount(cleaned_segment)
        normalized_food_name = re.sub(r"\s+", "", food_name)
        if amount_text != "1份" and not normalized_food_name:
            return False
        normalized_food_name = normalized_food_name or re.sub(r"\s+", "", cleaned_segment)
        return bool(normalized_food_name) and normalized_food_name not in GENERIC_FOOD_SEGMENTS

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
        fuzzy_match = FUZZY_AMOUNT_PATTERN.search(segment)
        if fuzzy_match:
            amount_token = fuzzy_match.group("amount")
            unit = self._normalize_unit(fuzzy_match.group("unit"))
            normalized_amount = FUZZY_AMOUNT_VALUES.get(amount_token) or FUZZY_UNIT_COUNTS.get(
                (amount_token, unit or "")
            )
            food_text = (segment[: fuzzy_match.start()] + segment[fuzzy_match.end() :]).strip(
                " 。.!！？?，,、；;:：-"
            )
            return fuzzy_match.group(0).strip(), normalized_amount, unit, food_text

        match = AMOUNT_PATTERN.search(segment)

        if match:
            amount_token = match.group("amount")
            unit = self._normalize_unit(match.group("unit"))
            normalized_amount = self._parse_numeric_token(amount_token)

            food_text = (segment[: match.start()] + segment[match.end() :]).strip(
                " 。.!！？?，,、；;:：-"
            )
            food_text = re.sub(
                r"^(约|大约|差不多|左右|一份|一碗|一杯)",
                "",
                food_text,
            ).strip()

            return match.group(0).strip(), normalized_amount, unit, food_text

        fuzzy_prefix_match = re.search(r"(?P<amount>少量|一点)", segment)
        if fuzzy_prefix_match:
            amount_token = fuzzy_prefix_match.group("amount")
            normalized_amount = FUZZY_AMOUNT_VALUES[amount_token]
            food_text = (segment[: fuzzy_prefix_match.start()] + segment[fuzzy_prefix_match.end() :]).strip(
                " 。.!！？?，,、；;:：-"
            )
            return amount_token, normalized_amount, "份", food_text

        return "1份", None, "份", segment.strip()

    def _extract_taste_cues(self, text: str) -> tuple[str, list[str]]:
        if not text:
            return "", []

        cues = [match.group(0) for match in TASTE_CUE_PATTERN.finditer(text)]
        cleaned = TASTE_CUE_PATTERN.sub(" ", text)
        cleaned = re.sub(r"(味道|口味)(?:上)?", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = cleaned.strip(" 。.!！？?，,、；;:：-")
        return cleaned, self._unique(cues)

    def _extract_follow_up_detail(self, text: str) -> Optional[dict]:
        stripped = self._strip_text_log_prefix(text)
        cleaned_text, taste_notes = self._extract_taste_cues(stripped)
        amount_text, normalized_amount, unit, food_text = self._extract_amount(cleaned_text)
        has_amount = normalized_amount is not None or amount_text != "1份"
        residual_text = re.sub(r"\s+", "", food_text)

        if not has_amount and not taste_notes:
            return None

        if residual_text and residual_text not in GENERIC_FOOD_SEGMENTS:
            return None

        return {
            "amount_text": amount_text if has_amount else None,
            "normalized_amount": normalized_amount,
            "unit": unit if has_amount else None,
            "taste_notes": taste_notes,
        }

    def _should_use_context_completion(
        self,
        *,
        current_text: str,
        context_text: str,
        current_segments: list[str],
        context_segments: list[str],
    ) -> bool:
        if current_segments or not context_text or len(context_segments) != 1:
            return False

        if not self._looks_like_meal_log_text(context_text):
            return False

        return self._extract_follow_up_detail(current_text) is not None

    def _merge_context_food_segment(self, context_segment: str, amount_text: Optional[str]) -> str:
        cleaned_context, _ = self._extract_taste_cues(context_segment)
        _, _, _, context_food_name = self._extract_amount(cleaned_context)
        base_food_name = (context_food_name or cleaned_context).strip()
        if not amount_text:
            return base_food_name
        return f"{amount_text}{base_food_name}".strip()

    def _build_follow_up_estimated_notes(
        self,
        *,
        amount_text: Optional[str],
        taste_notes: list[str],
    ) -> list[str]:
        notes: list[str] = ["食物名称沿用上一轮上下文补全。"]
        if amount_text:
            notes.append(f"分量来自补充回答：{amount_text}。")
        if taste_notes:
            notes.append(f"口味描述来自补充回答：{'；'.join(taste_notes)}。")
        return notes

    def _compose_note(self, notes: list[str]) -> Optional[str]:
        if not notes:
            return None
        return "；".join(self._unique(notes))

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

        base_weight = UNIT_BASE_WEIGHTS.get(
            normalized_unit or "",
            default_unit_weight or 100.0,
        )

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

        if decision.recommendation_level in {
            RecommendationLevel.AVOID,
            RecommendationLevel.LIMIT,
        }:
            warnings.append(f"本地规则：{decision.food_name} -> {decision.recommendation_level.value}")

        warnings.extend(decision.hard_blocks)

        if decision.caution_note:
            warnings.append(decision.caution_note)

        if decision.conflict_note:
            warnings.append(decision.conflict_note)

        return self._unique(warnings)

    def _build_prep_detail_adjustments(
        self,
        *,
        item: IntakeConfirmItem,
        estimate: dict,
        normalized: NormalizedConditions,
    ) -> dict:
        detail_text = self._compose_prep_detail_text(item)
        normalized_detail = normalize_food_text(detail_text)
        nutrition = dict(estimate["nutrition"])
        estimated_fields = list(estimate["estimated_fields"])
        estimated_notes = list(estimate["estimated_notes"])
        warnings: list[str] = []
        hard_blocks: list[str] = []
        allergen_tags: list[str] = []
        risk_tags: list[str] = []

        if not normalized_detail:
            return {
                "nutrition": nutrition,
                "estimated_fields": estimated_fields,
                "estimated_notes": estimated_notes,
                "warnings": warnings,
                "hard_blocks": hard_blocks,
                "allergen_tags": allergen_tags,
                "risk_tags": risk_tags,
            }

        if self._contains_any_term(normalized_detail, PREP_HIGH_SODIUM_TERMS):
            self._bump_nutrition(nutrition, "sodium", 350.0)
            self._add_unique(risk_tags, "high_sodium")
            self._add_unique(estimated_fields, "sodium")
            warnings.append("配料或调料包含高钠项，已按更保守钠负担复核。")

        if self._contains_any_term(normalized_detail, PREP_HIGH_SUGAR_TERMS):
            self._bump_nutrition(nutrition, "sugar", 10.0)
            self._bump_nutrition(nutrition, "carbs", 10.0)
            self._bump_nutrition(nutrition, "calories", 40.0)
            self._add_unique(risk_tags, "high_sugar")
            self._add_unique(estimated_fields, "sugar")
            self._add_unique(estimated_fields, "carbs")
            self._add_unique(estimated_fields, "calories")
            warnings.append("配料或调料包含加糖项，已按更保守糖负担复核。")

        if self._contains_any_term(normalized_detail, PREP_HIGH_FAT_TERMS):
            self._bump_nutrition(nutrition, "fat", 8.0)
            self._bump_nutrition(nutrition, "calories", 80.0)
            self._add_unique(risk_tags, "high_fat")
            self._add_unique(estimated_fields, "fat")
            self._add_unique(estimated_fields, "calories")
            warnings.append("烹饪方式包含高油脂做法，已按更保守脂肪负担复核。")

        if self._contains_any_term(normalized_detail, PREP_ULTRA_PROCESSED_TERMS):
            self._add_unique(risk_tags, "ultra_processed")
            warnings.append("配料或调料包含高加工度项，已按本地规则保守标记。")

        for tag, terms in PREP_ALLERGEN_TERMS.items():
            if self._contains_any_term(normalized_detail, terms):
                self._add_unique(allergen_tags, tag)
                for risk_tag in PREP_ALLERGEN_RISK_TAGS.get(tag, ()):
                    self._add_unique(risk_tags, risk_tag)

        for allergy in normalized.allergy_terms:
            allergy_norm = normalize_food_text(allergy)
            if not allergy_norm:
                continue
            if self._constraint_matches_prep_tags(allergy_norm, allergen_tags, normalized_detail):
                hard_blocks.append(f"过敏约束命中：{allergy}")

        for restriction in item.manual_restrictions:
            restriction_norm = normalize_food_text(restriction)
            if not restriction_norm:
                continue
            if restriction_norm in normalized_detail or self._constraint_matches_prep_tags(
                restriction_norm,
                allergen_tags,
                normalized_detail,
            ):
                hard_blocks.append(f"显式忌口命中：{restriction}")

        if warnings:
            estimated_notes.append("已根据配料、调料和烹饪方式做本地保守复核。")
        if hard_blocks:
            estimated_notes.append("配料或调料命中了本地过敏/忌口约束。")

        return {
            "nutrition": nutrition,
            "estimated_fields": estimated_fields,
            "estimated_notes": estimated_notes,
            "warnings": warnings,
            "hard_blocks": self._unique(hard_blocks),
            "allergen_tags": allergen_tags,
            "risk_tags": risk_tags,
        }

    def _compose_prep_detail_text(self, item: IntakeConfirmItem) -> str:
        parts = [item.food_name]
        parts.extend(item.ingredients or [])
        if item.cooking_method:
            parts.append(item.cooking_method)
        parts.extend(item.seasonings or [])
        if item.note:
            parts.append(item.note)
        return " ".join(part for part in parts if part)

    def _contains_any_term(self, normalized_text: str, terms: tuple[str, ...]) -> bool:
        if not normalized_text:
            return False
        return any(normalize_food_text(term) in normalized_text for term in terms if term)

    def _constraint_matches_prep_tags(
        self,
        constraint_norm: str,
        allergen_tags: list[str],
        normalized_detail: str,
    ) -> bool:
        if constraint_norm in normalized_detail:
            return True
        for tag in allergen_tags:
            aliases = PREP_ALLERGEN_TERMS.get(tag, ())
            normalized_aliases = [normalize_food_text(alias) for alias in aliases if alias]
            if constraint_norm == tag:
                return True
            if any(
                constraint_norm == alias
                or constraint_norm in alias
                or alias in constraint_norm
                for alias in normalized_aliases
                if alias
            ):
                return True
        return False

    def _add_unique(self, items: list[str], value: str) -> None:
        if value and value not in items:
            items.append(value)

    def _bump_nutrition(self, nutrition: dict, field: str, delta: float) -> None:
        current = nutrition.get(field)
        if current is None:
            nutrition[field] = round(delta, 1)
            return
        nutrition[field] = round(float(current) + delta, 1)

    def _build_session_warning(self, candidates: list[IntakeCandidate]) -> Optional[str]:
        if not candidates:
            return "未解析出可确认的候选项，请手动补充后再记账。"

        if any(candidate.warnings for candidate in candidates):
            return "存在本地规则命中项，请在确认前检查 warning。"

        if any(
            candidate.fallback_status == FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD
            for candidate in candidates
        ):
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
                strictest_level = self._pick_stricter_level(
                    strictest_level,
                    candidate.recommendation_level,
                )

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

        for field_name in (
            "calories",
            "protein",
            "carbs",
            "fat",
            "fiber",
            "sodium",
            "sugar",
            "purine",
        ):
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
