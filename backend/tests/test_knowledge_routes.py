import pytest

from app.api.routes import knowledge as knowledge_route
from app.models.knowledge import FoodItem


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _KnowledgeDb:
    def __init__(self, foods):
        self.foods = foods

    async def execute(self, _statement):
        return _ScalarResult(self.foods)


@pytest.mark.asyncio
async def test_list_foods_uses_normalized_query_matching():
    foods = [
        FoodItem(
            food_code='braised_beef_noodles',
            name_zh='红烧牛肉面',
            aliases_json=['红烧牛肉面', '牛肉拉面'],
            category='STAPLE',
            common_units_json=['碗'],
            calories_per_100g=120,
            protein_per_100g=5,
            carbs_per_100g=20,
            fat_per_100g=3,
            fiber_per_100g=1,
            sodium_per_100g=500,
            purine_per_100g=60,
            nutrition_source_code='core_v1_recipe_estimate',
            nutrition_source_detail='Core v1 recipe estimate from common Chinese portions.',
            nutrition_estimate_quality='RECIPE_ESTIMATE',
            nutrition_review_status='REVIEWED',
            allergen_tags_json=['wheat'],
            risk_tags_json=['starchy_staple', 'high_sodium'],
            is_enabled=True,
        ),
        FoodItem(
            food_code='white_rice',
            name_zh='白米饭',
            aliases_json=['米饭'],
            category='STAPLE',
            common_units_json=['碗'],
            calories_per_100g=116,
            protein_per_100g=2,
            carbs_per_100g=25,
            fat_per_100g=0.3,
            fiber_per_100g=0.3,
            sodium_per_100g=1,
            purine_per_100g=10,
            allergen_tags_json=[],
            risk_tags_json=['starchy_staple'],
            is_enabled=True,
        ),
    ]
    db = _KnowledgeDb(foods)

    results = await knowledge_route.list_foods(current_user=object(), db=db, q='  红 烧 牛 肉 面  ', category=None, risk_tag=None)

    assert [item.food_code for item in results] == ['braised_beef_noodles']
    assert results[0].nutrition_source_code == 'core_v1_recipe_estimate'
    assert results[0].nutrition_estimate_quality == 'RECIPE_ESTIMATE'
    assert results[0].nutrition_review_status == 'REVIEWED'
