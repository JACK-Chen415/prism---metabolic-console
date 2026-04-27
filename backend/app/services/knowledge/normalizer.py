"""Normalize user health conditions into canonical disease codes."""

from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health_condition import ConditionType, HealthCondition
from app.models.knowledge import HealthConditionMapping, MatchType, SourceField
from app.services.knowledge.contracts import NormalizedConditions


DEFAULT_ALIASES: dict[str, tuple[str, ...]] = {
    "hypertension": ("hypertension", "high_blood_pressure", "高血压", "血压高"),
    "hyperlipidemia": (
        "hyperlipidemia",
        "dyslipidemia",
        "hypercholesterolemia",
        "high_cholesterol",
        "高脂血症",
        "血脂高",
        "高胆固醇",
        "高甘油三酯",
    ),
    "gout": ("gout", "hyperuricemia", "uric_acid_high", "高尿酸", "高尿酸血症", "痛风"),
    "type2_diabetes": (
        "type2_diabetes",
        "t2dm",
        "diabetes",
        "高血糖",
        "糖尿病",
        "2型糖尿病",
        "二型糖尿病",
    ),
}


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return "".join(str(value).strip().lower().split())


def match_default_disease_code(condition_code: Optional[str], title: Optional[str] = None) -> Optional[str]:
    normalized_title = _normalize_text(title)
    normalized_code = _normalize_text(condition_code)
    for disease_code, aliases in DEFAULT_ALIASES.items():
        normalized_aliases = [_normalize_text(alias) for alias in aliases]
        if normalized_code and normalized_code in normalized_aliases:
            return disease_code
        if normalized_title and normalized_title in normalized_aliases:
            return disease_code
        if normalized_title and any(alias and alias in normalized_title for alias in normalized_aliases):
            return disease_code
    return None


class HealthConditionNormalizer:
    """Resolve free-text or legacy condition data into stable disease codes."""

    async def normalize(
        self,
        db: AsyncSession,
        conditions: Iterable[HealthCondition],
        explicit_condition_codes: Optional[list[str]] = None,
    ) -> NormalizedConditions:
        mappings = await self._load_mappings(db)
        disease_codes: list[str] = []
        allergy_terms: list[str] = []
        unmapped_conditions: list[str] = []

        for code in explicit_condition_codes or []:
            matched = self._match_value(code, mappings, SourceField.CONDITION_CODE)
            if matched:
                disease_codes.append(matched)
            else:
                disease_codes.append(code)

        for condition in conditions:
            if condition.condition_type == ConditionType.ALLERGY:
                allergy_terms.extend(self._extract_allergy_terms(condition))
                continue

            matched_code = self._resolve_condition(condition, mappings)
            if matched_code:
                disease_codes.append(matched_code)
            else:
                label = condition.title or condition.condition_code
                if label:
                    unmapped_conditions.append(label)

        return NormalizedConditions(
            disease_codes=self._unique_preserve_order(disease_codes),
            allergy_terms=self._unique_preserve_order(allergy_terms),
            unmapped_conditions=self._unique_preserve_order(unmapped_conditions),
        )

    async def _load_mappings(self, db: AsyncSession) -> list[HealthConditionMapping]:
        result = await db.execute(
            select(HealthConditionMapping)
            .where(HealthConditionMapping.is_enabled.is_(True))
            .order_by(HealthConditionMapping.priority.desc(), HealthConditionMapping.id.asc())
        )
        return list(result.scalars().all())

    def _resolve_condition(
        self,
        condition: HealthCondition,
        mappings: list[HealthConditionMapping],
    ) -> Optional[str]:
        direct_code = self._match_value(condition.condition_code, mappings, SourceField.CONDITION_CODE)
        if direct_code:
            return direct_code

        title_match = self._match_value(condition.title, mappings, SourceField.TITLE)
        if title_match:
            return title_match

        normalized_title = _normalize_text(condition.title)
        del normalized_title
        return match_default_disease_code(condition.condition_code, condition.title)

    def _match_value(
        self,
        raw_value: Optional[str],
        mappings: list[HealthConditionMapping],
        field: SourceField,
    ) -> Optional[str]:
        normalized_value = _normalize_text(raw_value)
        if not normalized_value:
            return None

        for mapping in mappings:
            if mapping.source_field != field:
                continue

            mapped_value = _normalize_text(mapping.match_value)
            if mapping.match_type == MatchType.EXACT and raw_value == mapping.match_value:
                return mapping.normalized_disease_code
            if mapping.match_type == MatchType.NORMALIZED and normalized_value == mapped_value:
                return mapping.normalized_disease_code
            if mapping.match_type == MatchType.ALIAS and normalized_value == mapped_value:
                return mapping.normalized_disease_code
            if mapping.match_type == MatchType.CONTAINS and mapped_value and mapped_value in normalized_value:
                return mapping.normalized_disease_code
        return None

    def _extract_allergy_terms(self, condition: HealthCondition) -> list[str]:
        values = [condition.condition_code, condition.title]
        terms = []
        for value in values:
            normalized = _normalize_text(value)
            if normalized:
                terms.append(normalized)
        return terms

    @staticmethod
    def _unique_preserve_order(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result
