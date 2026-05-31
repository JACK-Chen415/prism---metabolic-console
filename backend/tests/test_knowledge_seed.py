import asyncio
from copy import deepcopy

import pytest

from app.models.knowledge import (
    Disease,
    DiseaseFoodRule,
    FoodItem,
    HealthConditionMapping,
    KnowledgeSource,
    RuleSourceMap,
)
from app.seed import knowledge_seed as seed_module
from app.seed.knowledge_seed import load_dataset, upsert_seed, validate_dataset
from app.services.knowledge.matcher import normalize_food_text


def test_core_v1_dataset_validation_passes():
    dataset = load_dataset("core_v1")
    validate_dataset(dataset)


def test_core_v1_every_food_has_rule_for_each_disease():
    dataset = load_dataset("core_v1")
    food_codes = {item["food_code"] for item in dataset["foods"]}

    for ruleset in dataset["rulesets"]:
        ruleset_food_codes = {rule["food_code"] for rule in ruleset["rules"]}
        missing = sorted(food_codes - ruleset_food_codes)

        assert missing == [], f"{ruleset['disease_code']} missing rules for {missing}"


def test_core_v1_food_nutrition_sources_are_reviewed():
    dataset = load_dataset("core_v1")
    allowed_qualities = {
        "STANDARD_REFERENCE",
        "LABEL_REFERENCE",
        "RECIPE_ESTIMATE",
        "MIXED_REFERENCE_AND_RECIPE_ESTIMATE",
    }
    qualities = set()

    for food in dataset["foods"]:
        source_code = food.get("nutrition_source_code")
        source_detail = food.get("nutrition_source_detail")
        quality = food.get("nutrition_estimate_quality")
        review_status = food.get("nutrition_review_status")

        assert isinstance(source_code, str) and source_code.strip()
        assert len(source_code) <= 120
        assert isinstance(source_detail, str) and source_detail.strip()
        assert len(source_detail) <= 255
        assert quality in allowed_qualities
        assert review_status == "REVIEWED"
        qualities.add(quality)

    assert {"STANDARD_REFERENCE", "LABEL_REFERENCE", "RECIPE_ESTIMATE"}.issubset(qualities)


def test_core_v1_food_tags_use_reviewed_vocabularies():
    dataset = load_dataset("core_v1")
    allowed_allergens = {"dairy", "egg", "peanut", "seafood", "shellfish", "soy", "wheat"}
    allowed_risks = {
        "alcohol",
        "animal_protein",
        "contains_natural_sugar",
        "dairy",
        "dessert",
        "egg",
        "high_fat",
        "high_fiber",
        "high_glycemic_load",
        "high_purine",
        "high_sodium",
        "high_sugar",
        "higher_glycemic_load",
        "hydration",
        "low_energy_density",
        "low_fat",
        "moderate_purine",
        "organ_meat",
        "plant_protein",
        "processed_meat",
        "seafood",
        "shellfish",
        "soy",
        "starchy_staple",
        "sweetened_beverage",
        "ultra_processed",
        "whole_grain",
    }

    for food in dataset["foods"]:
        assert set(food.get("allergen_tags_json") or []).issubset(allowed_allergens)
        assert set(food.get("risk_tags_json") or []).issubset(allowed_risks)


def test_core_v1_china_market_additions_keep_aliases_and_tags():
    dataset = load_dataset("core_v1")
    foods = {item["food_code"]: item for item in dataset["foods"]}
    expected = {
        "soy_sauce": {
            "aliases": {"生抽", "老抽"},
            "allergens": {"soy"},
            "risks": {"high_sodium"},
        },
        "wheat_noodles": {
            "aliases": {"挂面", "鲜面条"},
            "allergens": {"wheat"},
            "risks": {"starchy_staple", "high_glycemic_load"},
        },
        "bok_choy": {
            "aliases": {"上海青", "小青菜"},
            "allergens": set(),
            "risks": {"high_fiber", "low_energy_density"},
        },
        "pork_liver": {
            "aliases": {"卤猪肝", "炒猪肝"},
            "allergens": set(),
            "risks": {"animal_protein", "high_purine", "organ_meat"},
        },
        "sweet_milk_tea": {
            "aliases": {"奶茶", "珍珠奶茶"},
            "allergens": {"dairy"},
            "risks": {"high_sugar", "sweetened_beverage"},
        },
        "rice_congee": {
            "aliases": {"米粥", "大米粥"},
            "allergens": set(),
            "risks": {"high_glycemic_load"},
        },
        "pickled_mustard_greens": {
            "aliases": {"咸菜", "榨菜"},
            "allergens": set(),
            "risks": {"high_sodium", "ultra_processed"},
        },
        "hot_pot_broth_spicy": {
            "aliases": {"火锅底料", "麻辣锅底"},
            "allergens": set(),
            "risks": {"high_sodium", "high_fat"},
        },
        "peanuts": {
            "aliases": {"花生米", "炒花生"},
            "allergens": {"peanut"},
            "risks": {"high_fat", "plant_protein"},
        },
        "crab": {
            "aliases": {"大闸蟹", "河蟹"},
            "allergens": {"seafood", "shellfish"},
            "risks": {"seafood", "shellfish", "moderate_purine"},
        },
        "steamed_bun": {
            "aliases": {"白馒头", "蒸馒头"},
            "allergens": {"wheat"},
            "risks": {"starchy_staple", "high_glycemic_load"},
        },
        "fried_dough_stick": {
            "aliases": {"炸油条", "早餐油条"},
            "allergens": {"wheat"},
            "risks": {"starchy_staple", "high_glycemic_load", "high_fat", "high_sodium", "ultra_processed"},
        },
        "braised_beef_noodles": {
            "aliases": {"红烧牛肉面", "牛肉拉面"},
            "allergens": {"wheat"},
            "risks": {"starchy_staple", "high_sodium", "animal_protein", "moderate_purine"},
        },
        "tomato": {
            "aliases": {"西红柿", "鲜番茄"},
            "allergens": set(),
            "risks": {"low_energy_density", "high_fiber"},
        },
        "chinese_cabbage": {
            "aliases": {"白菜心", "娃娃菜"},
            "allergens": set(),
            "risks": {"low_energy_density", "high_fiber"},
        },
        "potato": {
            "aliases": {"马铃薯", "洋芋"},
            "allergens": set(),
            "risks": {"starchy_staple", "high_glycemic_load"},
        },
        "sweet_potato": {
            "aliases": {"地瓜", "甘薯"},
            "allergens": set(),
            "risks": {"starchy_staple", "high_fiber"},
        },
        "shiitake_mushroom": {
            "aliases": {"冬菇", "鲜香菇"},
            "allergens": set(),
            "risks": {"moderate_purine", "high_fiber"},
        },
        "grass_carp": {
            "aliases": {"鲩鱼", "清蒸草鱼"},
            "allergens": {"seafood"},
            "risks": {"seafood", "animal_protein", "moderate_purine"},
        },
        "boiled_dumplings": {
            "aliases": {"饺子", "猪肉白菜饺子"},
            "allergens": {"wheat"},
            "risks": {"starchy_staple", "high_sodium", "animal_protein", "moderate_purine"},
        },
        "egg_fried_rice": {
            "aliases": {"扬州炒饭", "鸡蛋炒饭"},
            "allergens": {"egg"},
            "risks": {"egg", "starchy_staple", "high_glycemic_load", "high_sodium", "high_fat"},
        },
        "mapo_tofu": {
            "aliases": {"麻辣豆腐", "麻婆豆腐盖饭"},
            "allergens": {"soy"},
            "risks": {"soy", "plant_protein", "moderate_purine", "high_sodium", "high_fat"},
        },
        "tomato_egg_stir_fry": {
            "aliases": {"西红柿炒鸡蛋", "番茄炒鸡蛋"},
            "allergens": {"egg"},
            "risks": {"egg", "animal_protein", "high_fat"},
        },
        "xiaolongbao": {
            "aliases": {"灌汤包", "汤包"},
            "allergens": {"wheat"},
            "risks": {"starchy_staple", "high_sodium", "animal_protein", "moderate_purine"},
        },
        "meat_baozi": {
            "aliases": {"鲜肉包", "猪肉包", "肉包"},
            "allergens": {"wheat"},
            "risks": {"starchy_staple", "high_sodium", "animal_protein", "moderate_purine"},
        },
        "vegetable_baozi": {
            "aliases": {"素菜包", "青菜包", "蔬菜包"},
            "allergens": {"wheat"},
            "risks": {"starchy_staple", "high_glycemic_load", "high_sodium"},
        },
        "jianbing_guozi": {
            "aliases": {"煎饼馃子", "早餐煎饼", "鸡蛋煎饼果子"},
            "allergens": {"wheat", "egg", "soy"},
            "risks": {"starchy_staple", "high_glycemic_load", "high_sodium", "high_fat", "egg", "soy"},
        },
        "shaomai": {
            "aliases": {"烧麦", "糯米烧卖", "香菇烧卖"},
            "allergens": {"wheat", "soy"},
            "risks": {"starchy_staple", "high_glycemic_load", "high_sodium", "animal_protein", "moderate_purine", "soy"},
        },
        "sweetened_soy_milk": {
            "aliases": {"加糖豆浆", "甜味豆浆"},
            "allergens": {"soy"},
            "risks": {"soy", "plant_protein", "high_sugar", "sweetened_beverage"},
        },
        "cheung_fun": {
            "aliases": {"广式肠粉", "猪肉肠粉", "鸡蛋肠粉"},
            "allergens": {"soy", "egg"},
            "risks": {"starchy_staple", "high_glycemic_load", "high_sodium", "soy", "egg"},
        },
        "sweet_tofu_pudding": {
            "aliases": {"甜豆腐脑", "糖水豆花"},
            "allergens": {"soy"},
            "risks": {"soy", "plant_protein", "high_sugar", "dessert"},
        },
        "sticky_rice_roll": {
            "aliases": {"糯米饭团", "早餐饭团", "油条饭团"},
            "allergens": {"wheat", "soy"},
            "risks": {"starchy_staple", "high_glycemic_load", "high_sodium", "high_fat", "ultra_processed", "soy"},
        },
        "luosifen": {
            "aliases": {"柳州螺蛳粉", "酸笋螺蛳粉", "袋装螺蛳粉"},
            "allergens": {"seafood"},
            "risks": {"starchy_staple", "high_sodium", "high_fat", "ultra_processed", "moderate_purine", "seafood"},
        },
        "fried_chicken_cutlet": {
            "aliases": {"鸡排", "香酥鸡排", "炸鸡"},
            "allergens": {"wheat"},
            "risks": {"animal_protein", "moderate_purine", "high_fat", "high_sodium", "ultra_processed"},
        },
        "grilled_cold_noodles": {
            "aliases": {"东北烤冷面", "铁板烤冷面"},
            "allergens": {"wheat", "egg", "soy"},
            "risks": {"egg", "soy", "starchy_staple", "high_glycemic_load", "high_sodium", "high_fat"},
        },
        "braised_pork_belly": {
            "aliases": {"东坡肉", "扣肉"},
            "allergens": set(),
            "risks": {"animal_protein", "high_fat", "high_sodium", "moderate_purine"},
        },
        "kung_pao_chicken": {
            "aliases": {"宫爆鸡丁", "辣炒鸡丁"},
            "allergens": {"peanut"},
            "risks": {"animal_protein", "high_fat", "high_sodium", "moderate_purine"},
        },
        "scallion_pancake": {
            "aliases": {"葱饼", "煎葱饼"},
            "allergens": {"wheat"},
            "risks": {"starchy_staple", "high_glycemic_load", "high_fat", "high_sodium"},
        },
        "steamed_egg_custard": {
            "aliases": {"蒸蛋羹", "蒸水蛋"},
            "allergens": {"egg"},
            "risks": {"egg", "animal_protein"},
        },
        "steamed_perch": {
            "aliases": {"鲈鱼", "蒸鲈鱼"},
            "allergens": {"seafood"},
            "risks": {"seafood", "animal_protein", "moderate_purine"},
        },
        "zhajiangmian": {
            "aliases": {"老北京炸酱面", "肉酱面"},
            "allergens": {"wheat", "soy"},
            "risks": {"starchy_staple", "high_glycemic_load", "high_sodium", "animal_protein", "moderate_purine", "soy"},
        },
        "hot_dry_noodles": {
            "aliases": {"武汉热干面", "芝麻酱热干面"},
            "allergens": {"wheat", "peanut"},
            "risks": {"starchy_staple", "high_glycemic_load", "high_sodium", "high_fat", "plant_protein"},
        },
        "salted_duck_egg": {
            "aliases": {"盐鸭蛋", "咸蛋"},
            "allergens": {"egg"},
            "risks": {"egg", "animal_protein", "high_sodium", "high_fat"},
        },
        "tea_egg": {
            "aliases": {"卤茶叶蛋", "五香茶叶蛋"},
            "allergens": {"egg", "soy"},
            "risks": {"egg", "animal_protein", "high_sodium", "soy"},
        },
        "braised_eggplant": {
            "aliases": {"油焖茄子", "酱烧茄子"},
            "allergens": {"soy"},
            "risks": {"high_fat", "high_sodium", "high_glycemic_load", "soy"},
        },
        "roujiamo": {
            "aliases": {"腊汁肉夹馍", "白吉馍夹肉"},
            "allergens": {"wheat"},
            "risks": {"starchy_staple", "high_glycemic_load", "high_sodium", "animal_protein", "high_fat", "moderate_purine"},
        },
        "liangpi": {
            "aliases": {"陕西凉皮", "麻酱凉皮"},
            "allergens": {"wheat", "peanut"},
            "risks": {"starchy_staple", "high_glycemic_load", "high_sodium", "high_fat"},
        },
        "wonton_soup": {
            "aliases": {"云吞", "鲜肉馄饨"},
            "allergens": {"wheat"},
            "risks": {"starchy_staple", "high_sodium", "animal_protein", "moderate_purine"},
        },
        "malatang_spicy": {
            "aliases": {"麻辣串", "串串香"},
            "allergens": {"soy", "peanut"},
            "risks": {"high_sodium", "high_fat", "ultra_processed", "animal_protein", "moderate_purine", "soy"},
        },
        "grilled_skewers": {
            "aliases": {"烤串", "羊肉串"},
            "allergens": set(),
            "risks": {"animal_protein", "high_sodium", "high_fat", "moderate_purine"},
        },
    }

    for food_code, checks in expected.items():
        food = foods[food_code]
        assert checks["aliases"].issubset(set(food["aliases_json"]))
        assert checks["allergens"].issubset(set(food["allergen_tags_json"]))
        assert checks["risks"].issubset(set(food["risk_tags_json"]))


def test_core_v1_new_breakfast_takeout_rules_remain_conservative():
    dataset = load_dataset("core_v1")
    rules_by_disease = {
        ruleset["disease_code"]: {rule["food_code"]: rule for rule in ruleset["rules"]}
        for ruleset in dataset["rulesets"]
    }

    new_food_codes = {
        "meat_baozi",
        "vegetable_baozi",
        "jianbing_guozi",
        "shaomai",
        "sweetened_soy_milk",
        "cheung_fun",
        "sweet_tofu_pudding",
        "sticky_rice_roll",
        "luosifen",
        "fried_chicken_cutlet",
        "grilled_cold_noodles",
    }
    for disease_code, rules in rules_by_disease.items():
        assert new_food_codes.issubset(rules), f"{disease_code} missing new breakfast/takeout rules"

    for food_code in {"meat_baozi", "jianbing_guozi", "shaomai", "sticky_rice_roll", "luosifen", "fried_chicken_cutlet", "grilled_cold_noodles"}:
        assert rules_by_disease["gout"][food_code]["recommendation_level"] in {"LIMIT", "AVOID"}

    for food_code in {"meat_baozi", "vegetable_baozi", "jianbing_guozi", "shaomai", "cheung_fun", "sticky_rice_roll", "luosifen", "fried_chicken_cutlet", "grilled_cold_noodles"}:
        assert rules_by_disease["hypertension"][food_code]["recommendation_level"] in {"LIMIT", "AVOID"}

    assert rules_by_disease["type2_diabetes"]["sweetened_soy_milk"]["recommendation_level"] == "AVOID"
    assert rules_by_disease["type2_diabetes"]["sweet_tofu_pudding"]["recommendation_level"] == "AVOID"
    for food_code in {"jianbing_guozi", "shaomai", "cheung_fun", "sticky_rice_roll", "luosifen", "fried_chicken_cutlet", "grilled_cold_noodles"}:
        assert rules_by_disease["type2_diabetes"][food_code]["recommendation_level"] in {"LIMIT", "AVOID"}

    for food_code in {"jianbing_guozi", "sweetened_soy_milk", "sweet_tofu_pudding", "sticky_rice_roll", "luosifen", "fried_chicken_cutlet", "grilled_cold_noodles"}:
        assert rules_by_disease["hyperlipidemia"][food_code]["recommendation_level"] in {"LIMIT", "AVOID"}


def test_core_v1_food_match_terms_are_unique_after_normalization():
    dataset = load_dataset("core_v1")
    terms: dict[str, str] = {}

    for food in dataset["foods"]:
        candidates = [food["food_code"], food["name_zh"], *(food.get("aliases_json") or [])]
        for candidate in candidates:
            normalized = normalize_food_text(candidate)
            assert normalized
            previous = terms.get(normalized)
            assert previous in {None, food["food_code"]}, (
                f"normalized term {normalized!r} maps to both {previous} and {food['food_code']}"
            )
            terms[normalized] = food["food_code"]


def test_core_v1_aliases_avoid_generic_substring_terms():
    dataset = load_dataset("core_v1")
    risky_aliases = {"蛋", "肉", "菜", "鱼", "奶", "水", "饭", "面", "汤", "粥"}

    for food in dataset["foods"]:
        aliases = {normalize_food_text(alias) for alias in food.get("aliases_json") or []}
        assert aliases.isdisjoint(risky_aliases), f"{food['food_code']} has over-broad alias"


def test_validate_dataset_rejects_food_tag_alias_and_rule_regressions():
    base = load_dataset("core_v1")

    cases = []

    unknown_tag_dataset = deepcopy(base)
    unknown_tag_dataset["foods"][0]["risk_tags_json"] = [
        *(unknown_tag_dataset["foods"][0].get("risk_tags_json") or []),
        "raw_unreviewed_tag",
    ]
    cases.append((unknown_tag_dataset, "uses unknown risk tags"))

    broad_alias_dataset = deepcopy(base)
    broad_alias_dataset["foods"][0]["aliases_json"] = [
        *(broad_alias_dataset["foods"][0].get("aliases_json") or []),
        "饭",
    ]
    cases.append((broad_alias_dataset, "over-broad alias"))

    duplicate_alias_dataset = deepcopy(base)
    duplicate_alias_dataset["foods"][1]["aliases_json"] = [
        *(duplicate_alias_dataset["foods"][1].get("aliases_json") or []),
        duplicate_alias_dataset["foods"][0]["name_zh"],
    ]
    cases.append((duplicate_alias_dataset, "maps to both"))

    missing_source_dataset = deepcopy(base)
    missing_source_dataset["foods"][0]["nutrition_source_code"] = ""
    cases.append((missing_source_dataset, "missing nutrition_source_code"))

    unsupported_quality_dataset = deepcopy(base)
    unsupported_quality_dataset["foods"][0]["nutrition_estimate_quality"] = "UNREVIEWED_AI_GUESS"
    cases.append((unsupported_quality_dataset, "unsupported nutrition_estimate_quality"))

    unreviewed_status_dataset = deepcopy(base)
    unreviewed_status_dataset["foods"][0]["nutrition_review_status"] = "NEEDS_REVIEW"
    cases.append((unreviewed_status_dataset, "unsupported nutrition_review_status"))

    missing_rule_dataset = deepcopy(base)
    missing_food_code = missing_rule_dataset["foods"][0]["food_code"]
    missing_rule_dataset["rulesets"][0]["rules"] = [
        rule for rule in missing_rule_dataset["rulesets"][0]["rules"]
        if rule["food_code"] != missing_food_code
    ]
    cases.append((missing_rule_dataset, "missing rules for"))

    for dataset, expected_message in cases:
        with pytest.raises(ValueError, match=expected_message):
            validate_dataset(dataset)


def test_upsert_seed_flushes_parent_tables_before_rules(monkeypatch):
    dataset = load_dataset("core_v1")
    events: list[str] = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def flush(self):
            events.append("flush")

        async def commit(self):
            events.append("commit")

        async def rollback(self):
            events.append("rollback")

    async def fake_upsert_rows(session, *, model, rows, key_fields, summary, defaults):
        events.append(model.__name__)

    monkeypatch.setattr(seed_module, "async_session_maker", lambda: FakeSession())
    monkeypatch.setattr(seed_module, "_upsert_rows", fake_upsert_rows)

    asyncio.run(upsert_seed(dataset, dry_run=False, disable_missing=False))

    assert events == [
        Disease.__name__,
        FoodItem.__name__,
        KnowledgeSource.__name__,
        HealthConditionMapping.__name__,
        "flush",
        DiseaseFoodRule.__name__,
        "flush",
        RuleSourceMap.__name__,
        "flush",
        "commit",
    ]
