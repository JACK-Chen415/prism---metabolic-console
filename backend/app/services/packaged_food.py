"""Packaged-food lookup and nutrition-label normalization providers.

The gray-release build intentionally keeps barcode data behind a provider
abstraction. Mock/dev data must never be presented as a real commercial barcode
database.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health_condition import HealthCondition
from app.models.knowledge import FallbackStatus, KnowledgeOrigin, RecommendationLevel
from app.models.user import User
from app.services.knowledge.contracts import LocalDecision, NormalizedConditions
from app.services.knowledge.matcher import normalize_food_text
from app.services.knowledge.service import KnowledgeService


ALLOWED_PACKAGED_FOOD_PROVIDERS = {"mock", "dev", "disabled"}
PACKAGED_FOOD_DISCLAIMER = "包装食品营养信息仅用于健康管理参考，不作诊断、治疗、处方或替代医生建议。"
BARCODE_PATTERN = re.compile(r"^\d{8,14}$")

ALLERGEN_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dairy", ("牛奶", "奶粉", "乳粉", "乳清", "乳制品", "milk", "dairy", "lactose")),
    ("egg", ("鸡蛋", "蛋粉", "蛋黄", "蛋白", "egg")),
    ("peanut", ("花生", "peanut")),
    ("seafood", ("海鲜", "鱼", "鱼粉", "虾", "蟹", "seafood", "fish")),
    ("shellfish", ("虾", "蟹", "贝", "shellfish", "shrimp", "crab")),
    ("soy", ("大豆", "黄豆", "豆粉", "豆浆", "酱油", "豆瓣酱", "soy", "soybean", "soy sauce")),
    ("wheat", ("小麦", "面粉", "麸质", "面筋", "wheat", "gluten", "flour")),
)


class PackagedFoodProviderStatus(str, Enum):
    AVAILABLE = "available"
    MOCK = "mock"
    DISABLED = "disabled"
    PLANNED = "planned"


@dataclass(frozen=True)
class PackagedFoodCandidate:
    barcode: Optional[str]
    food_name: str
    brand: Optional[str]
    category: str
    serving_size: Optional[str]
    serving_size_g: Optional[float]
    calories_per_100g: Optional[float]
    protein_per_100g: Optional[float]
    carbs_per_100g: Optional[float]
    fat_per_100g: Optional[float]
    fiber_per_100g: Optional[float]
    sodium_per_100g: Optional[float]
    sugar_per_100g: Optional[float]
    purine_per_100g: Optional[float]
    ingredients: tuple[str, ...]
    allergen_tags: tuple[str, ...]
    risk_tags: tuple[str, ...]
    nutrition_source_code: str
    nutrition_source_detail: str
    nutrition_estimate_quality: str
    nutrition_review_status: str
    provider: str
    provider_status: PackagedFoodProviderStatus
    confidence: float
    notes: tuple[str, ...] = ()

    @property
    def barcode_last4(self) -> Optional[str]:
        return self.barcode[-4:] if self.barcode else None


class PackagedFoodProvider:
    provider = "disabled"
    status = PackagedFoodProviderStatus.DISABLED
    display_name = "Disabled packaged-food provider"

    async def lookup_barcode(self, barcode: str) -> list[PackagedFoodCandidate]:
        del barcode
        return []


class MockPackagedFoodProvider(PackagedFoodProvider):
    provider = "mock"
    status = PackagedFoodProviderStatus.MOCK
    display_name = "Mock packaged-food provider"

    _items: dict[str, PackagedFoodCandidate] = {
        "6901234567892": PackagedFoodCandidate(
            barcode="6901234567892",
            food_name="无糖原味酸奶",
            brand="Prism Mock Dairy",
            category="DAIRY",
            serving_size="100g",
            serving_size_g=100,
            calories_per_100g=63,
            protein_per_100g=3.5,
            carbs_per_100g=4.7,
            fat_per_100g=3.3,
            fiber_per_100g=0,
            sodium_per_100g=46,
            sugar_per_100g=4.7,
            purine_per_100g=2,
            ingredients=("生牛乳", "乳酸菌"),
            allergen_tags=("dairy",),
            risk_tags=("dairy",),
            nutrition_source_code="mock_packaged_food_label",
            nutrition_source_detail="Mock provider label data for gray-release contract testing.",
            nutrition_estimate_quality="LABEL_REFERENCE",
            nutrition_review_status="NEEDS_USER_REVIEW",
            provider="mock",
            provider_status=PackagedFoodProviderStatus.MOCK,
            confidence=0.82,
            notes=("mock_provider", "requires_user_label_review"),
        ),
        "6970000000027": PackagedFoodCandidate(
            barcode="6970000000027",
            food_name="高钠方便面",
            brand="Prism Mock Noodle",
            category="STAPLE",
            serving_size="120g",
            serving_size_g=120,
            calories_per_100g=460,
            protein_per_100g=8,
            carbs_per_100g=62,
            fat_per_100g=18,
            fiber_per_100g=2,
            sodium_per_100g=1750,
            sugar_per_100g=5,
            purine_per_100g=45,
            ingredients=("小麦粉", "棕榈油", "食用盐", "酱油粉"),
            allergen_tags=("wheat", "soy"),
            risk_tags=("starchy_staple", "high_sodium", "high_fat", "ultra_processed", "soy"),
            nutrition_source_code="mock_packaged_food_label",
            nutrition_source_detail="Mock provider label data for gray-release contract testing.",
            nutrition_estimate_quality="LABEL_REFERENCE",
            nutrition_review_status="NEEDS_USER_REVIEW",
            provider="mock",
            provider_status=PackagedFoodProviderStatus.MOCK,
            confidence=0.78,
            notes=("mock_provider", "high_sodium_label_review_required"),
        ),
    }

    async def lookup_barcode(self, barcode: str) -> list[PackagedFoodCandidate]:
        item = self._items.get(barcode)
        return [item] if item else []


class DisabledPackagedFoodProvider(PackagedFoodProvider):
    provider = "disabled"
    status = PackagedFoodProviderStatus.DISABLED
    display_name = "Disabled packaged-food provider"


def normalize_barcode(raw_barcode: str) -> str:
    barcode = re.sub(r"[\s-]+", "", raw_barcode or "")
    if not BARCODE_PATTERN.match(barcode):
        raise ValueError("条码必须为 8-14 位数字")
    return barcode


def _unique(items: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = str(item).strip().lower()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return tuple(result)


def _optional_non_negative(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return max(float(value), 0.0)


def _infer_allergen_tags(values: Sequence[str]) -> tuple[str, ...]:
    normalized_text = normalize_food_text(" ".join(values))
    tags: list[str] = []
    for tag, keywords in ALLERGEN_KEYWORDS:
        if any(normalize_food_text(keyword) in normalized_text for keyword in keywords):
            tags.append(tag)
    return _unique(tags)


def _infer_risk_tags(
    *,
    sodium_per_100g: Optional[float],
    sugar_per_100g: Optional[float],
    fat_per_100g: Optional[float],
    fiber_per_100g: Optional[float],
    purine_per_100g: Optional[float],
    ingredients: Sequence[str],
    allergen_tags: Sequence[str],
) -> tuple[str, ...]:
    tags: list[str] = list(allergen_tags)
    if sodium_per_100g is not None and sodium_per_100g >= 600:
        tags.append("high_sodium")
    if sugar_per_100g is not None and sugar_per_100g >= 15:
        tags.append("high_sugar")
    if fat_per_100g is not None and fat_per_100g >= 17:
        tags.append("high_fat")
    if fiber_per_100g is not None and fiber_per_100g >= 6:
        tags.append("high_fiber")
    if purine_per_100g is not None and purine_per_100g >= 150:
        tags.append("high_purine")
    elif purine_per_100g is not None and purine_per_100g >= 50:
        tags.append("moderate_purine")
    ingredient_text = normalize_food_text(" ".join(ingredients))
    if any(token in ingredient_text for token in ("方便", "膨化", "香精", "防腐剂", "preservative")):
        tags.append("ultra_processed")
    return _unique(tags)


def build_manual_label_candidate(
    *,
    product_name: str,
    brand: Optional[str],
    barcode: Optional[str],
    category: str,
    serving_size: Optional[str],
    serving_size_g: Optional[float],
    calories_per_100g: Optional[float],
    protein_per_100g: Optional[float],
    carbs_per_100g: Optional[float],
    fat_per_100g: Optional[float],
    fiber_per_100g: Optional[float],
    sodium_per_100g: Optional[float],
    sugar_per_100g: Optional[float],
    purine_per_100g: Optional[float],
    ingredients: Sequence[str],
    allergen_tags: Sequence[str],
    risk_tags: Sequence[str],
) -> PackagedFoodCandidate:
    barcode_clean = normalize_barcode(barcode) if barcode else None
    clean_ingredients = tuple(item.strip() for item in ingredients if item.strip())
    inferred_allergens = _infer_allergen_tags(
        [product_name, brand or "", *clean_ingredients, *allergen_tags]
    )
    merged_allergens = _unique([*allergen_tags, *inferred_allergens])
    inferred_risks = _infer_risk_tags(
        sodium_per_100g=sodium_per_100g,
        sugar_per_100g=sugar_per_100g,
        fat_per_100g=fat_per_100g,
        fiber_per_100g=fiber_per_100g,
        purine_per_100g=purine_per_100g,
        ingredients=clean_ingredients,
        allergen_tags=merged_allergens,
    )
    merged_risks = _unique([*risk_tags, *inferred_risks])
    return PackagedFoodCandidate(
        barcode=barcode_clean,
        food_name=product_name.strip(),
        brand=(brand or "").strip() or None,
        category=(category or "SNACK").strip().upper()[:50] or "SNACK",
        serving_size=(serving_size or "").strip() or None,
        serving_size_g=_optional_non_negative(serving_size_g),
        calories_per_100g=_optional_non_negative(calories_per_100g),
        protein_per_100g=_optional_non_negative(protein_per_100g),
        carbs_per_100g=_optional_non_negative(carbs_per_100g),
        fat_per_100g=_optional_non_negative(fat_per_100g),
        fiber_per_100g=_optional_non_negative(fiber_per_100g),
        sodium_per_100g=_optional_non_negative(sodium_per_100g),
        sugar_per_100g=_optional_non_negative(sugar_per_100g),
        purine_per_100g=_optional_non_negative(purine_per_100g),
        ingredients=clean_ingredients,
        allergen_tags=merged_allergens,
        risk_tags=merged_risks,
        nutrition_source_code="user_packaged_food_label",
        nutrition_source_detail="User-entered packaged-food nutrition label normalized per 100g.",
        nutrition_estimate_quality="LABEL_REFERENCE",
        nutrition_review_status="NEEDS_USER_REVIEW",
        provider="manual_label",
        provider_status=PackagedFoodProviderStatus.AVAILABLE,
        confidence=0.72,
        notes=("manual_label", "requires_user_label_review"),
    )


class PackagedFoodProviderRegistry:
    def __init__(self, provider_name: str = "mock"):
        self.provider_name = (provider_name or "mock").strip().lower().replace("-", "_")

    def get_provider(self) -> PackagedFoodProvider:
        if self.provider_name in {"mock", "dev"}:
            return MockPackagedFoodProvider()
        return DisabledPackagedFoodProvider()


class PackagedFoodLookupService:
    def __init__(
        self,
        provider: Optional[PackagedFoodProvider] = None,
        knowledge_service: Optional[KnowledgeService] = None,
    ):
        self.provider = provider or MockPackagedFoodProvider()
        self.knowledge_service = knowledge_service or KnowledgeService()

    async def lookup_barcode(
        self,
        db: AsyncSession,
        *,
        user: User,
        conditions: Sequence[HealthCondition],
        barcode: str,
        explicit_condition_codes: Optional[list[str]] = None,
        manual_restrictions: Optional[list[str]] = None,
    ) -> list[tuple[PackagedFoodCandidate, LocalDecision]]:
        normalized_barcode = normalize_barcode(barcode)
        candidates = await self.provider.lookup_barcode(normalized_barcode)
        return [
            (candidate, await self.evaluate_candidate(
                db,
                user=user,
                conditions=conditions,
                candidate=candidate,
                explicit_condition_codes=explicit_condition_codes,
                manual_restrictions=manual_restrictions,
            ))
            for candidate in candidates
        ]

    async def normalize_label(
        self,
        db: AsyncSession,
        *,
        user: User,
        conditions: Sequence[HealthCondition],
        candidate: PackagedFoodCandidate,
        explicit_condition_codes: Optional[list[str]] = None,
        manual_restrictions: Optional[list[str]] = None,
    ) -> tuple[PackagedFoodCandidate, LocalDecision]:
        return (
            candidate,
            await self.evaluate_candidate(
                db,
                user=user,
                conditions=conditions,
                candidate=candidate,
                explicit_condition_codes=explicit_condition_codes,
                manual_restrictions=manual_restrictions,
            ),
        )

    async def evaluate_candidate(
        self,
        db: AsyncSession,
        *,
        user: User,
        conditions: Sequence[HealthCondition],
        candidate: PackagedFoodCandidate,
        explicit_condition_codes: Optional[list[str]] = None,
        manual_restrictions: Optional[list[str]] = None,
    ) -> LocalDecision:
        normalized = await self.knowledge_service.normalize_conditions(
            db,
            conditions,
            explicit_condition_codes,
        )
        matched_decision = await self.knowledge_service.evaluate_food(
            db,
            normalized=normalized,
            food_name=candidate.food_name,
            manual_restrictions=manual_restrictions or [],
            user=user,
        )
        if matched_decision.food_code:
            return matched_decision.model_copy(
                update={"risk_tags": list(_unique([*matched_decision.risk_tags, *candidate.risk_tags]))}
            )

        hard_blocks = self._resolve_candidate_hard_blocks(
            candidate,
            normalized,
            manual_restrictions or [],
        )
        if hard_blocks:
            return LocalDecision(
                food_name=candidate.food_name,
                recommendation_level=RecommendationLevel.AVOID,
                matched_disease_codes=normalized.disease_codes,
                hard_blocks=hard_blocks,
                risk_tags=list(candidate.risk_tags),
                summary=f"{candidate.food_name} 的包装食品标签命中过敏/显式忌口，本地规则要求先阻断或改选。",
                origin=KnowledgeOrigin.LOCAL_RULE,
                fallback_status=FallbackStatus.LOCAL_BLOCKED_NO_CLOUD,
                caution_note="包装食品标签存在绝对约束项；云端不能放宽该限制。",
                unmapped_conditions=normalized.unmapped_conditions,
            )

        fallback_status = (
            FallbackStatus.LOCAL_PARTIAL_ALLOW_CLOUD
            if normalized.disease_codes or candidate.risk_tags
            else FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD
        )
        return LocalDecision(
            food_name=candidate.food_name,
            matched_disease_codes=normalized.disease_codes,
            risk_tags=list(candidate.risk_tags),
            summary=f"{candidate.food_name} 已按包装食品营养标签归一化；本地知识库未命中完整病种-食物规则，需人工核对标签后再记录。",
            origin=KnowledgeOrigin.LOCAL_KNOWLEDGE,
            fallback_status=fallback_status,
            caution_note=PACKAGED_FOOD_DISCLAIMER,
            unmapped_conditions=normalized.unmapped_conditions,
        )

    def _resolve_candidate_hard_blocks(
        self,
        candidate: PackagedFoodCandidate,
        normalized: NormalizedConditions,
        manual_restrictions: list[str],
    ) -> list[str]:
        tokens = {
            normalize_food_text(candidate.food_name),
            normalize_food_text(candidate.brand),
            *(normalize_food_text(item) for item in candidate.ingredients),
            *(normalize_food_text(tag) for tag in candidate.allergen_tags),
        }
        reasons: list[str] = []
        for allergy in normalized.allergy_terms:
            allergy_norm = normalize_food_text(allergy)
            if allergy_norm and (allergy_norm in tokens or any(allergy_norm in token for token in tokens)):
                reasons.append(f"过敏约束命中：{allergy}")
        for restriction in manual_restrictions:
            restriction_norm = normalize_food_text(restriction)
            if restriction_norm and (
                restriction_norm in tokens or any(restriction_norm in token for token in tokens)
            ):
                reasons.append(f"显式忌口命中：{restriction}")
        return list(_unique(reasons))
