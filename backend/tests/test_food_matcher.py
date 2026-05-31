import pytest

from app.models.knowledge import FoodItem
from app.services.knowledge.matcher import FoodMatcherService, normalize_food_text


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        if len(self._rows) > 1:
            raise AssertionError("test query expected at most one row")
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _MatcherDb:
    def __init__(self, *result_sets):
        self._result_sets = list(result_sets)
        self.execute_count = 0

    async def execute(self, _statement):
        self.execute_count += 1
        if not self._result_sets:
            raise AssertionError("unexpected extra database query")
        return _ScalarResult(self._result_sets.pop(0))


def _food(food_code: str, name_zh: str, aliases: list[str]) -> FoodItem:
    return FoodItem(
        food_code=food_code,
        name_zh=name_zh,
        aliases_json=aliases,
        category="STAPLE",
        nutrition_source_code="core_v1_recipe_estimate",
        nutrition_source_detail="reviewed test nutrition source",
        nutrition_estimate_quality="RECIPE_ESTIMATE",
        nutrition_review_status="REVIEWED",
        is_enabled=True,
    )


def test_normalize_food_text_removes_spacing_and_case_noise():
    assert normalize_food_text("  Beef  NOODLES  ") == "beefnoodles"
    assert normalize_food_text(" 红 烧 牛 肉 面 ") == "红烧牛肉面"
    assert normalize_food_text(None) == ""


@pytest.mark.asyncio
async def test_find_by_name_or_code_matches_reviewed_seed_alias_after_direct_miss():
    noodles = _food("braised_beef_noodles", "红烧牛肉面", ["牛肉拉面", "红烧牛肉面"])
    rice = _food("white_rice", "白米饭", ["米饭"])
    db = _MatcherDb([], [rice, noodles])

    matched = await FoodMatcherService().find_by_name_or_code(db, food_name="  牛 肉 拉 面  ")

    assert matched is noodles
    assert db.execute_count == 2


@pytest.mark.asyncio
async def test_match_many_from_text_uses_aliases_and_deduplicates_food_codes():
    noodles = _food("braised_beef_noodles", "红烧牛肉面", ["牛肉拉面", "红烧牛肉面"])
    sweet_soy = _food("sweetened_soy_milk", "甜豆浆", ["加糖豆浆", "甜味豆浆"])
    db = _MatcherDb([noodles, sweet_soy])

    matched = await FoodMatcherService().match_many_from_text(
        db,
        "早餐：红烧牛肉面，又叫牛肉拉面；饮品是加糖豆浆。",
    )

    assert [food.food_code for food in matched] == [
        "braised_beef_noodles",
        "sweetened_soy_milk",
    ]
