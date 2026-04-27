"""Food matching helpers for local rule evaluation."""

from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import FoodItem


def normalize_food_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return "".join(str(value).strip().lower().split())


class FoodMatcherService:
    async def find_by_name_or_code(
        self,
        db: AsyncSession,
        *,
        food_name: Optional[str] = None,
        food_code: Optional[str] = None,
    ) -> Optional[FoodItem]:
        if food_code:
            result = await db.execute(
                select(FoodItem).where(
                    FoodItem.food_code == food_code,
                    FoodItem.is_enabled.is_(True),
                )
            )
            food = result.scalar_one_or_none()
            if food:
                return food

        normalized_name = normalize_food_text(food_name)
        if not normalized_name:
            return None

        result = await db.execute(
            select(FoodItem).where(
                or_(
                    FoodItem.name_zh == food_name,
                    FoodItem.food_code == normalized_name,
                ),
                FoodItem.is_enabled.is_(True),
            )
        )
        direct = result.scalar_one_or_none()
        if direct:
            return direct

        all_foods = (
            await db.execute(select(FoodItem).where(FoodItem.is_enabled.is_(True)))
        ).scalars().all()
        for food in all_foods:
            candidates = [food.food_code, food.name_zh, *(food.aliases_json or [])]
            normalized_candidates = [normalize_food_text(candidate) for candidate in candidates if candidate]
            if normalized_name in normalized_candidates:
                return food
            if any(candidate and candidate in normalized_name for candidate in normalized_candidates):
                return food
        return None

    async def match_many_from_text(self, db: AsyncSession, query: str) -> list[FoodItem]:
        normalized_query = normalize_food_text(query)
        if not normalized_query:
            return []

        all_foods = (
            await db.execute(select(FoodItem).where(FoodItem.is_enabled.is_(True)))
        ).scalars().all()
        matched: list[FoodItem] = []
        seen: set[str] = set()
        for food in all_foods:
            candidates = [food.name_zh, food.food_code, *(food.aliases_json or [])]
            normalized_candidates = [normalize_food_text(candidate) for candidate in candidates if candidate]
            if any(candidate and candidate in normalized_query for candidate in normalized_candidates):
                if food.food_code not in seen:
                    seen.add(food.food_code)
                    matched.append(food)
        return matched
