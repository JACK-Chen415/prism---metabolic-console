"""Idempotent knowledge seed command."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.database import async_session_maker, close_db
from app.models.knowledge import (
    DEFAULT_NUTRITION_ESTIMATE_QUALITY,
    DEFAULT_NUTRITION_REVIEW_STATUS,
    DEFAULT_NUTRITION_SOURCE_CODE,
    DEFAULT_NUTRITION_SOURCE_DETAIL,
    Disease,
    DiseaseFoodRule,
    FoodItem,
    HealthConditionMapping,
    KnowledgeSource,
    RuleSourceMap,
)
from app.services.knowledge.matcher import normalize_food_text


ROOT = Path(__file__).resolve().parents[1] / "seed_data" / "knowledge"
ALLOWED_SOURCE_TIERS = {"TIER_1", "TIER_2"}
ALLOWED_ALLERGEN_TAGS = {"dairy", "egg", "peanut", "seafood", "shellfish", "soy", "wheat"}
ALLOWED_RISK_TAGS = {
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
ALLOWED_RECOMMENDATION_LEVELS = {"AVOID", "CONDITIONAL", "LIMIT", "MODERATE", "RECOMMEND"}
ALLOWED_RULE_CONFIDENCE = {"HIGH", "MEDIUM"}
ALLOWED_CONDITION_SCOPES = {"GENERAL", "STABLE"}
ALLOWED_NUTRITION_ESTIMATE_QUALITIES = {
    "STANDARD_REFERENCE",
    "LABEL_REFERENCE",
    "RECIPE_ESTIMATE",
    "MIXED_REFERENCE_AND_RECIPE_ESTIMATE",
}
ALLOWED_NUTRITION_REVIEW_STATUSES = {"REVIEWED"}
OVER_BROAD_FOOD_ALIASES = {"蛋", "肉", "菜", "鱼", "奶", "水", "饭", "面", "汤", "粥"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed local disease-food knowledge data.")
    parser.add_argument("--dataset", default="core_v1", help="Dataset folder name under seed_data/knowledge")
    parser.add_argument("--validate-only", action="store_true", help="Validate dataset only without DB writes")
    parser.add_argument("--dry-run", action="store_true", help="Run DB upserts and roll back at the end")
    parser.add_argument(
        "--disable-missing-in-dataset",
        action="store_true",
        help="Disable existing seeded records missing from the current dataset instead of leaving them active",
    )
    return parser.parse_args()


def load_dataset(dataset: str) -> dict[str, Any]:
    dataset_dir = ROOT / dataset
    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_dir}")

    def read_json(name: str, default: Any) -> Any:
        path = dataset_dir / name
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    rules = []
    for path in sorted(dataset_dir.glob("rules.*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rules.append(payload)

    return {
        "dataset": dataset,
        "diseases": read_json("diseases.json", []),
        "foods": read_json("foods.json", []),
        "sources": read_json("sources.json", []),
        "mappings": read_json("health_condition_mappings.json", []),
        "rulesets": rules,
    }


def validate_dataset(dataset: dict[str, Any]) -> None:
    errors: list[str] = []
    disease_codes = {item["disease_code"] for item in dataset["diseases"]}
    food_codes = {item["food_code"] for item in dataset["foods"]}
    source_map = {item["source_code"]: item for item in dataset["sources"]}
    mapping_codes: set[str] = set()
    rule_codes: set[str] = set()
    food_match_terms: dict[str, str] = {}
    broad_aliases = {normalize_food_text(item) for item in OVER_BROAD_FOOD_ALIASES}

    if len(disease_codes) != len(dataset["diseases"]):
        errors.append("diseases.json contains duplicate disease_code")
    if len(food_codes) != len(dataset["foods"]):
        errors.append("foods.json contains duplicate food_code")
    if len(source_map) != len(dataset["sources"]):
        errors.append("sources.json contains duplicate source_code")

    for food in dataset["foods"]:
        food_code = food["food_code"]
        allergen_tags = set(food.get("allergen_tags_json") or [])
        risk_tags = set(food.get("risk_tags_json") or [])
        unknown_allergens = sorted(allergen_tags - ALLOWED_ALLERGEN_TAGS)
        unknown_risks = sorted(risk_tags - ALLOWED_RISK_TAGS)
        if unknown_allergens:
            errors.append(f"food {food_code} uses unknown allergen tags: {unknown_allergens}")
        if unknown_risks:
            errors.append(f"food {food_code} uses unknown risk tags: {unknown_risks}")

        source_code = str(food.get("nutrition_source_code") or "").strip()
        source_detail = str(food.get("nutrition_source_detail") or "").strip()
        estimate_quality = str(food.get("nutrition_estimate_quality") or "").strip()
        review_status = str(food.get("nutrition_review_status") or "").strip()
        if not source_code:
            errors.append(f"food {food_code} is missing nutrition_source_code")
        elif len(source_code) > 120:
            errors.append(f"food {food_code} nutrition_source_code is too long")
        if not source_detail:
            errors.append(f"food {food_code} is missing nutrition_source_detail")
        elif len(source_detail) > 255:
            errors.append(f"food {food_code} nutrition_source_detail is too long")
        if estimate_quality not in ALLOWED_NUTRITION_ESTIMATE_QUALITIES:
            errors.append(f"food {food_code} uses unsupported nutrition_estimate_quality")
        if review_status not in ALLOWED_NUTRITION_REVIEW_STATUSES:
            errors.append(f"food {food_code} uses unsupported nutrition_review_status")

        for alias in food.get("aliases_json") or []:
            normalized_alias = normalize_food_text(alias)
            if normalized_alias in broad_aliases:
                errors.append(f"food {food_code} has over-broad alias: {alias}")

        candidates = [food_code, food.get("name_zh"), *(food.get("aliases_json") or [])]
        for candidate in candidates:
            normalized = normalize_food_text(candidate)
            if not normalized:
                errors.append(f"food {food_code} has a blank match term")
                continue
            previous_food_code = food_match_terms.get(normalized)
            if previous_food_code and previous_food_code != food_code:
                errors.append(
                    f"normalized food term {normalized!r} maps to both "
                    f"{previous_food_code} and {food_code}"
                )
                continue
            food_match_terms[normalized] = food_code

    for source_code, source in source_map.items():
        if source["source_tier"] not in ALLOWED_SOURCE_TIERS:
            errors.append(f"source {source_code} tier {source['source_tier']} is not allowed in core seed")

    for mapping in dataset["mappings"]:
        if mapping["mapping_code"] in mapping_codes:
            errors.append(f"duplicate mapping_code: {mapping['mapping_code']}")
        mapping_codes.add(mapping["mapping_code"])
        if mapping["normalized_disease_code"] not in disease_codes:
            errors.append(f"mapping {mapping['mapping_code']} references unknown disease_code")

    for ruleset in dataset["rulesets"]:
        disease_code = ruleset["disease_code"]
        if disease_code not in disease_codes:
            errors.append(f"ruleset references unknown disease_code: {disease_code}")
        ruleset_food_codes: set[str] = set()
        duplicate_rule_food_codes: set[str] = set()
        for rule in ruleset["rules"]:
            food_code = rule["food_code"]
            if food_code in ruleset_food_codes:
                duplicate_rule_food_codes.add(food_code)
            ruleset_food_codes.add(food_code)

            rule_code = rule.get("rule_code") or f"rule::{disease_code}::{food_code}"
            if rule_code in rule_codes:
                errors.append(f"duplicate rule_code: {rule_code}")
            rule_codes.add(rule_code)

            if food_code not in food_codes:
                errors.append(f"rule {rule_code} references unknown food_code")
            if rule.get("recommendation_level") not in ALLOWED_RECOMMENDATION_LEVELS:
                errors.append(f"rule {rule_code} uses unknown recommendation_level")
            if rule.get("source_confidence") not in ALLOWED_RULE_CONFIDENCE:
                errors.append(f"rule {rule_code} uses unsupported source_confidence")
            if rule.get("highest_source_tier") not in ALLOWED_SOURCE_TIERS:
                errors.append(f"rule {rule_code} uses unsupported highest_source_tier")
            if rule.get("condition_scope", "GENERAL") not in ALLOWED_CONDITION_SCOPES:
                errors.append(f"rule {rule_code} uses unsupported condition_scope")
            if not rule.get("sources"):
                errors.append(f"rule {rule_code} has no source mappings")
                continue
            primary_count = 0
            for source_ref in rule["sources"]:
                source_code = source_ref["source_code"]
                if source_code not in source_map:
                    errors.append(f"rule {rule_code} references unknown source {source_code}")
                    continue
                if source_map[source_code]["source_tier"] not in ALLOWED_SOURCE_TIERS:
                    errors.append(f"rule {rule_code} uses non-core source {source_code}")
                if source_ref.get("is_primary"):
                    primary_count += 1
                if not source_ref.get("section_ref"):
                    errors.append(f"rule {rule_code} has source {source_code} without section_ref")
            if primary_count != 1:
                errors.append(f"rule {rule_code} must have exactly one primary source")
            if rule.get("source_confidence") == "LOW":
                errors.append(f"rule {rule_code} cannot use LOW source_confidence in core seed")

        if duplicate_rule_food_codes:
            errors.append(
                f"ruleset {disease_code} has duplicate food rules: {sorted(duplicate_rule_food_codes)}"
            )
        missing_food_codes = sorted(food_codes - ruleset_food_codes)
        if missing_food_codes:
            errors.append(f"ruleset {disease_code} missing rules for: {missing_food_codes}")

    if errors:
        raise ValueError("Dataset validation failed:\n- " + "\n- ".join(errors))


async def upsert_seed(dataset: dict[str, Any], *, dry_run: bool, disable_missing: bool) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    seed_version = dataset["dataset"]

    async with async_session_maker() as session:
        try:
            await _upsert_rows(
                session,
                model=Disease,
                rows=dataset["diseases"],
                key_fields=("disease_code",),
                summary=summary["diseases"],
                defaults={"seed_version": seed_version, "is_enabled": True},
            )
            await _upsert_rows(
                session,
                model=FoodItem,
                rows=dataset["foods"],
                key_fields=("food_code",),
                summary=summary["foods"],
                defaults={
                    "seed_version": seed_version,
                    "is_enabled": True,
                    "nutrition_source_code": DEFAULT_NUTRITION_SOURCE_CODE,
                    "nutrition_source_detail": DEFAULT_NUTRITION_SOURCE_DETAIL,
                    "nutrition_estimate_quality": DEFAULT_NUTRITION_ESTIMATE_QUALITY,
                    "nutrition_review_status": DEFAULT_NUTRITION_REVIEW_STATUS,
                },
            )
            await _upsert_rows(
                session,
                model=KnowledgeSource,
                rows=dataset["sources"],
                key_fields=("source_code",),
                summary=summary["sources"],
                defaults={"seed_version": seed_version, "is_enabled": True},
            )
            await _upsert_rows(
                session,
                model=HealthConditionMapping,
                rows=dataset["mappings"],
                key_fields=("mapping_code",),
                summary=summary["mappings"],
                defaults={"seed_version": seed_version, "is_enabled": True},
            )
            # Flush parent tables before child rules so a fresh database can
            # satisfy the foreign keys from rule -> disease/food/source.
            await session.flush()

            source_versions = {
                item["source_code"]: item.get("source_version")
                for item in dataset["sources"]
            }

            flattened_rules: list[dict[str, Any]] = []
            flattened_rule_maps: list[dict[str, Any]] = []
            for ruleset in dataset["rulesets"]:
                disease_code = ruleset["disease_code"]
                for rule in ruleset["rules"]:
                    rule_code = rule.get("rule_code") or f"rule::{disease_code}::{rule['food_code']}"
                    primary_source_code = next(
                        source_ref["source_code"] for source_ref in rule["sources"] if source_ref.get("is_primary")
                    )
                    flattened_rules.append(
                        {
                            "rule_code": rule_code,
                            "disease_code": disease_code,
                            "food_code": rule["food_code"],
                            "recommendation_level": rule["recommendation_level"],
                            "portion_guidance": rule.get("portion_guidance"),
                            "frequency_guidance": rule.get("frequency_guidance"),
                            "summary_note": rule["summary_note"],
                            "needs_warning": rule.get("needs_warning", False),
                            "is_enabled": True,
                            "source_confidence": rule["source_confidence"],
                            "conflict_note": rule.get("conflict_note"),
                            "caution_note": rule.get("caution_note"),
                            "highest_source_tier": rule["highest_source_tier"],
                            "primary_source_code": primary_source_code,
                            "condition_scope": rule.get("condition_scope", "GENERAL"),
                            "applicability_note": rule.get("applicability_note"),
                            "seed_version": seed_version,
                            "source_version_snapshot": source_versions.get(primary_source_code),
                        }
                    )
                    for source_ref in rule["sources"]:
                        flattened_rule_maps.append(
                            {
                                "rule_code": rule_code,
                                "source_code": source_ref["source_code"],
                                "citation_rank": source_ref.get("citation_rank", 1),
                                "section_ref": source_ref["section_ref"],
                                "source_note": source_ref.get("source_note"),
                                "is_primary": source_ref.get("is_primary", False),
                                "seed_version": seed_version,
                                "is_enabled": True,
                            }
                        )

            await _upsert_rows(
                session,
                model=DiseaseFoodRule,
                rows=flattened_rules,
                key_fields=("rule_code",),
                summary=summary["rules"],
                defaults={"seed_version": seed_version, "is_enabled": True},
            )
            # Flush rule rows before rule_source_maps references them.
            await session.flush()
            await _upsert_rows(
                session,
                model=RuleSourceMap,
                rows=flattened_rule_maps,
                key_fields=("rule_code", "source_code", "section_ref"),
                summary=summary["rule_source_maps"],
                defaults={"seed_version": seed_version, "is_enabled": True},
            )
            await session.flush()

            if disable_missing:
                await _disable_missing_records(
                    session,
                    seed_version=seed_version,
                    dataset=dataset,
                    summary=summary,
                )

            if dry_run:
                await session.rollback()
            else:
                await session.commit()
        except Exception:
            await session.rollback()
            raise

    return summary


async def _upsert_rows(
    session,
    *,
    model,
    rows: list[dict[str, Any]],
    key_fields: tuple[str, ...],
    summary: dict[str, int],
    defaults: dict[str, Any],
) -> None:
    for row in rows:
        payload = {**defaults, **row}
        stmt = select(model)
        for field in key_fields:
            stmt = stmt.where(getattr(model, field) == payload[field])
        existing = (await session.execute(stmt)).scalar_one_or_none()

        if existing is None:
            session.add(model(**payload))
            summary["created"] += 1
            continue

        changed = False
        for field, value in payload.items():
            if getattr(existing, field) != value:
                setattr(existing, field, value)
                changed = True
        summary["updated" if changed else "unchanged"] += 1


async def _disable_missing_records(session, *, seed_version: str, dataset: dict[str, Any], summary) -> None:
    await _disable_missing_for_model(
        session,
        model=Disease,
        seed_version=seed_version,
        keep_keys={item["disease_code"] for item in dataset["diseases"]},
        field_name="disease_code",
        summary=summary["diseases"],
    )
    await _disable_missing_for_model(
        session,
        model=FoodItem,
        seed_version=seed_version,
        keep_keys={item["food_code"] for item in dataset["foods"]},
        field_name="food_code",
        summary=summary["foods"],
    )
    await _disable_missing_for_model(
        session,
        model=KnowledgeSource,
        seed_version=seed_version,
        keep_keys={item["source_code"] for item in dataset["sources"]},
        field_name="source_code",
        summary=summary["sources"],
    )
    await _disable_missing_for_model(
        session,
        model=HealthConditionMapping,
        seed_version=seed_version,
        keep_keys={item["mapping_code"] for item in dataset["mappings"]},
        field_name="mapping_code",
        summary=summary["mappings"],
    )

    rule_keys = {
        (ruleset["disease_code"], rule["food_code"])
        for ruleset in dataset["rulesets"]
        for rule in ruleset["rules"]
    }
    rules = (
        await session.execute(
            select(DiseaseFoodRule).where(DiseaseFoodRule.seed_version == seed_version)
        )
    ).scalars().all()
    for item in rules:
        key = (item.disease_code, item.food_code)
        if key not in rule_keys and item.is_enabled:
            item.is_enabled = False
            summary["rules"]["disabled"] += 1

    map_keys = {
        (
            rule.get("rule_code") or f"rule::{ruleset['disease_code']}::{rule['food_code']}",
            source_ref["source_code"],
            source_ref["section_ref"],
        )
        for ruleset in dataset["rulesets"]
        for rule in ruleset["rules"]
        for source_ref in rule["sources"]
    }
    maps = (
        await session.execute(
            select(RuleSourceMap).where(RuleSourceMap.seed_version == seed_version)
        )
    ).scalars().all()
    for item in maps:
        key = (item.rule_code, item.source_code, item.section_ref)
        if key not in map_keys and item.is_enabled:
            item.is_enabled = False
            summary["rule_source_maps"]["disabled"] += 1


async def _disable_missing_for_model(
    session,
    *,
    model,
    seed_version: str,
    keep_keys: set[str],
    field_name: str,
    summary: dict[str, int],
) -> None:
    rows = (
        await session.execute(select(model).where(model.seed_version == seed_version))
    ).scalars().all()
    for item in rows:
        key = getattr(item, field_name)
        if key not in keep_keys and item.is_enabled:
            item.is_enabled = False
            summary["disabled"] += 1


def print_summary(summary: dict[str, dict[str, int]]) -> None:
    print("Seed summary:")
    for section, counts in summary.items():
        if not counts:
            continue
        ordered = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        print(f"- {section}: {ordered}")


async def async_main() -> None:
    args = parse_args()
    dataset = load_dataset(args.dataset)
    validate_dataset(dataset)

    if args.validate_only:
        print(f"Dataset '{args.dataset}' validation passed.")
        return

    try:
        summary = await upsert_seed(
            dataset,
            dry_run=args.dry_run,
            disable_missing=args.disable_missing_in_dataset,
        )
        if args.dry_run:
            print(f"Dry-run completed for dataset '{args.dataset}'. No changes were committed.")
        else:
            print(f"Seed completed for dataset '{args.dataset}'.")
        print_summary(summary)
    finally:
        await close_db()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
