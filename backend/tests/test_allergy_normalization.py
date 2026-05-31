from types import SimpleNamespace

import pytest

from app.models.health_condition import ConditionStatus, ConditionType, HealthCondition, TrendType
from app.services.knowledge.contracts import NormalizedConditions
from app.services.knowledge.normalizer import HealthConditionNormalizer
from app.services.knowledge.service import KnowledgeService


def _allergy_condition(text: str) -> HealthCondition:
    return HealthCondition(
        user_id=1,
        condition_code=text,
        title=text,
        icon="medical_services",
        condition_type=ConditionType.ALLERGY,
        status=ConditionStatus.MONITORING,
        trend=TrendType.STABLE,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("phrase", "expected_terms"),
    [
        ("虾过敏", {"shellfish", "shrimp", "seafood", "虾"}),
        ("花生过敏", {"peanut", "花生"}),
        ("牛奶过敏", {"dairy", "牛奶"}),
        ("鸡蛋过敏", {"egg", "鸡蛋"}),
        ("小麦过敏", {"wheat", "gluten", "小麦"}),
        ("大豆过敏", {"soy", "大豆"}),
        ("芝麻过敏", {"sesame", "芝麻"}),
        ("鱼过敏", {"fish", "seafood", "鱼"}),
    ],
)
async def test_chinese_allergy_phrases_normalize_to_canonical_tags(monkeypatch, phrase, expected_terms):
    normalizer = HealthConditionNormalizer()

    async def fake_load_mappings(db):
        return []

    monkeypatch.setattr(normalizer, "_load_mappings", fake_load_mappings)

    normalized = await normalizer.normalize(None, [_allergy_condition(phrase)])
    normalized_terms = set(normalized.allergy_terms)

    assert expected_terms <= normalized_terms
    assert phrase not in normalized_terms
    assert not any(term.endswith("过敏") for term in normalized_terms)


@pytest.mark.parametrize(
    ("phrase", "food"),
    [
        (
            "虾过敏",
            SimpleNamespace(
                food_code="shrimp",
                name_zh="鲜虾",
                aliases_json=["虾仁"],
                allergen_tags_json=["shellfish"],
            ),
        ),
        (
            "花生过敏",
            SimpleNamespace(
                food_code="salad",
                name_zh="拌菜",
                aliases_json=["花生碎"],
                allergen_tags_json=[],
            ),
        ),
        (
            "牛奶过敏",
            SimpleNamespace(
                food_code="milk_porridge",
                name_zh="奶粥",
                aliases_json=[],
                allergen_tags_json=["dairy"],
            ),
        ),
        (
            "鸡蛋过敏",
            SimpleNamespace(
                food_code="egg_dish",
                name_zh="蛋羹",
                aliases_json=["鸡蛋"],
                allergen_tags_json=[],
            ),
        ),
        (
            "小麦过敏",
            SimpleNamespace(
                food_code="wheat_noodle",
                name_zh="面条",
                aliases_json=["面粉"],
                allergen_tags_json=["wheat"],
            ),
        ),
        (
            "大豆过敏",
            SimpleNamespace(
                food_code="tofu",
                name_zh="豆腐",
                aliases_json=["豆腐"],
                allergen_tags_json=[],
            ),
        ),
        (
            "芝麻过敏",
            SimpleNamespace(
                food_code="sesame_sauce",
                name_zh="凉拌菜",
                aliases_json=["芝麻酱"],
                allergen_tags_json=["sesame"],
            ),
        ),
        (
            "鱼过敏",
            SimpleNamespace(
                food_code="fish_soup",
                name_zh="鱼汤",
                aliases_json=["鲈鱼"],
                allergen_tags_json=["seafood"],
            ),
        ),
    ],
)
def test_allergy_terms_hit_food_tags_and_aliases(phrase, food):
    normalizer = HealthConditionNormalizer()
    service = KnowledgeService(normalizer=normalizer)
    condition = _allergy_condition(phrase)
    normalized = NormalizedConditions(
        disease_codes=[],
        allergy_terms=normalizer._extract_allergy_terms(condition),
        unmapped_conditions=[],
    )

    reasons = service._resolve_hard_blocks(food, normalized, [])

    assert reasons
    assert any(reason.startswith("过敏约束命中：") for reason in reasons)
    assert all(phrase not in reason for reason in reasons)
