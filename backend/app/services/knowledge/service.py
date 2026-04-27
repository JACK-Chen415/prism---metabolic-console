"""Local-first knowledge service and rule engine."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health_condition import HealthCondition
from app.models.knowledge import (
    Disease,
    DiseaseFoodRule,
    FallbackStatus,
    FoodItem,
    KnowledgeOrigin,
    KnowledgeSource,
    RecommendationLevel,
    RuleSourceMap,
)
from app.models.user import User
from app.schemas.knowledge import CitationResponse
from app.services.knowledge.contracts import KnowledgeSummary, LocalDecision, NormalizedConditions
from app.services.knowledge.matcher import FoodMatcherService, normalize_food_text
from app.services.knowledge.normalizer import HealthConditionNormalizer


SEVERITY_ORDER = {
    RecommendationLevel.RECOMMEND: 0,
    RecommendationLevel.MODERATE: 1,
    RecommendationLevel.CONDITIONAL: 2,
    RecommendationLevel.INSUFFICIENT: 3,
    RecommendationLevel.LIMIT: 4,
    RecommendationLevel.AVOID: 5,
}


@dataclass
class RuleBundle:
    rule: DiseaseFoodRule
    citations: list[CitationResponse]


class KnowledgeService:
    def __init__(
        self,
        normalizer: Optional[HealthConditionNormalizer] = None,
        matcher: Optional[FoodMatcherService] = None,
    ):
        self.normalizer = normalizer or HealthConditionNormalizer()
        self.matcher = matcher or FoodMatcherService()

    async def normalize_conditions(
        self,
        db: AsyncSession,
        conditions: Sequence[HealthCondition],
        explicit_condition_codes: Optional[list[str]] = None,
    ) -> NormalizedConditions:
        return await self.normalizer.normalize(db, conditions, explicit_condition_codes)

    async def evaluate_food_for_user(
        self,
        db: AsyncSession,
        *,
        user: User,
        conditions: Sequence[HealthCondition],
        food_name: Optional[str] = None,
        food_code: Optional[str] = None,
        explicit_condition_codes: Optional[list[str]] = None,
        manual_restrictions: Optional[list[str]] = None,
    ) -> LocalDecision:
        normalized = await self.normalize_conditions(db, conditions, explicit_condition_codes)
        return await self.evaluate_food(
            db,
            normalized=normalized,
            food_name=food_name,
            food_code=food_code,
            manual_restrictions=manual_restrictions or [],
            user=user,
        )

    async def evaluate_food(
        self,
        db: AsyncSession,
        *,
        normalized: NormalizedConditions,
        food_name: Optional[str] = None,
        food_code: Optional[str] = None,
        manual_restrictions: Optional[list[str]] = None,
        user: Optional[User] = None,
    ) -> LocalDecision:
        food = await self.matcher.find_by_name_or_code(db, food_name=food_name, food_code=food_code)
        resolved_food_name = food.name_zh if food else (food_name or food_code or "未知食物")

        if food is None:
            return LocalDecision(
                food_name=resolved_food_name,
                summary="本地知识库暂未命中该食物，可在保留本地约束前提下补充云端查询。",
                origin=KnowledgeOrigin.LOCAL_KNOWLEDGE,
                fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
                unmapped_conditions=normalized.unmapped_conditions,
            )

        hard_blocks = self._resolve_hard_blocks(food, normalized, manual_restrictions or [])
        if hard_blocks:
            return LocalDecision(
                food_code=food.food_code,
                food_name=food.name_zh,
                recommendation_level=RecommendationLevel.AVOID,
                matched_disease_codes=normalized.disease_codes,
                hard_blocks=hard_blocks,
                risk_tags=food.risk_tags_json or [],
                summary=f"{food.name_zh} 命中过敏/显式忌口，本地规则直接阻断。",
                origin=KnowledgeOrigin.LOCAL_RULE,
                fallback_status=FallbackStatus.LOCAL_BLOCKED_NO_CLOUD,
                citations=[],
                caution_note="存在绝对约束项，云端只能解释原因或提供替代建议。",
                unmapped_conditions=normalized.unmapped_conditions,
            )

        bundles = await self._load_rule_bundles(db, normalized.disease_codes, food.food_code)
        if not bundles:
            return LocalDecision(
                food_code=food.food_code,
                food_name=food.name_zh,
                matched_disease_codes=normalized.disease_codes,
                risk_tags=food.risk_tags_json or [],
                summary=f"已识别食物为 {food.name_zh}，但本地规则尚未覆盖相关病种组合，可补充云端查询。",
                origin=KnowledgeOrigin.LOCAL_KNOWLEDGE,
                fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
                unmapped_conditions=normalized.unmapped_conditions,
            )

        strictest = max(bundles, key=lambda bundle: SEVERITY_ORDER[bundle.rule.recommendation_level])
        missing_disease_codes = [
            disease_code for disease_code in normalized.disease_codes if disease_code not in {bundle.rule.disease_code for bundle in bundles}
        ]
        fallback_status = self._determine_fallback_status(strictest.rule.recommendation_level, missing_disease_codes)

        citations = self._merge_citations([bundle.citations for bundle in bundles])
        summary = self._build_rule_summary(food, bundles, missing_disease_codes, user)
        conflict_notes = [bundle.rule.conflict_note for bundle in bundles if bundle.rule.conflict_note]
        caution_notes = [bundle.rule.caution_note for bundle in bundles if bundle.rule.caution_note]

        return LocalDecision(
            food_code=food.food_code,
            food_name=food.name_zh,
            recommendation_level=strictest.rule.recommendation_level,
            matched_disease_codes=self._unique([bundle.rule.disease_code for bundle in bundles]),
            risk_tags=food.risk_tags_json or [],
            portion_guidance=strictest.rule.portion_guidance,
            frequency_guidance=strictest.rule.frequency_guidance,
            summary=summary,
            origin=KnowledgeOrigin.LOCAL_RULE,
            fallback_status=fallback_status,
            citations=citations,
            conflict_note="；".join(conflict_notes) or None,
            caution_note="；".join(caution_notes) or None,
            unmapped_conditions=normalized.unmapped_conditions,
        )

    async def summarize_query_for_user(
        self,
        db: AsyncSession,
        *,
        user: User,
        conditions: Sequence[HealthCondition],
        query: str,
        explicit_condition_codes: Optional[list[str]] = None,
        manual_restrictions: Optional[list[str]] = None,
    ) -> KnowledgeSummary:
        normalized = await self.normalize_conditions(db, conditions, explicit_condition_codes)
        matched_foods = await self.matcher.match_many_from_text(db, query)
        disease_cards = await self._load_disease_cards(db, normalized.disease_codes)

        local_decisions: list[LocalDecision] = []
        for food in matched_foods:
            decision = await self.evaluate_food(
                db,
                normalized=normalized,
                food_code=food.food_code,
                manual_restrictions=manual_restrictions or [],
                user=user,
            )
            local_decisions.append(decision)

        summary_parts: list[str] = []
        citations = self._merge_citations([decision.citations for decision in local_decisions])

        if disease_cards:
            disease_lines = [f"{disease.name_zh}：{disease.summary}" for disease in disease_cards]
            summary_parts.append("；".join(disease_lines))

        if local_decisions:
            food_lines = [
                f"{decision.food_name}：{self._level_label(decision.recommendation_level)}，{decision.summary}"
                for decision in local_decisions
            ]
            summary_parts.append("；".join(food_lines))

        if normalized.unmapped_conditions:
            summary_parts.append(
                f"以下健康档案暂未标准化映射：{'、'.join(normalized.unmapped_conditions)}。"
            )

        if not summary_parts:
            summary_parts.append("本地知识库未命中明确病种或食物，可补充云端查询。")

        if any(decision.fallback_status == FallbackStatus.LOCAL_BLOCKED_NO_CLOUD for decision in local_decisions):
            fallback_status = FallbackStatus.LOCAL_BLOCKED_NO_CLOUD
            can_call_cloud = False
            origin = KnowledgeOrigin.LOCAL_RULE
        elif local_decisions and all(
            decision.fallback_status == FallbackStatus.LOCAL_COMPLETE for decision in local_decisions
        ):
            fallback_status = FallbackStatus.LOCAL_COMPLETE
            can_call_cloud = False
            origin = KnowledgeOrigin.LOCAL_RULE
        elif local_decisions:
            fallback_status = FallbackStatus.LOCAL_PARTIAL_ALLOW_CLOUD
            can_call_cloud = True
            origin = KnowledgeOrigin.MIXED
        elif normalized.disease_codes:
            fallback_status = FallbackStatus.LOCAL_PARTIAL_ALLOW_CLOUD
            can_call_cloud = True
            origin = KnowledgeOrigin.LOCAL_KNOWLEDGE
        else:
            fallback_status = FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD
            can_call_cloud = True
            origin = KnowledgeOrigin.CLOUD_SUPPLEMENT

        return KnowledgeSummary(
            query=query,
            matched_disease_codes=normalized.disease_codes,
            matched_food_codes=[food.food_code for food in matched_foods],
            summary=" ".join(summary_parts),
            origin=origin,
            fallback_status=fallback_status,
            can_call_cloud=can_call_cloud,
            local_decisions=local_decisions,
            citations=citations,
            unmapped_conditions=normalized.unmapped_conditions,
        )

    async def get_rule_sources(self, db: AsyncSession, rule_code: str) -> list[CitationResponse]:
        bundles = await self._load_rule_bundles_by_rule_codes(db, [rule_code])
        return bundles.get(rule_code, [])

    async def get_rule_for_pair(
        self,
        db: AsyncSession,
        disease_code: str,
        food_code: str,
    ) -> Tuple[Optional[DiseaseFoodRule], list[CitationResponse]]:
        result = await db.execute(
            select(DiseaseFoodRule).where(
                DiseaseFoodRule.disease_code == disease_code,
                DiseaseFoodRule.food_code == food_code,
                DiseaseFoodRule.is_enabled.is_(True),
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            return None, []
        citations = await self.get_rule_sources(db, rule.rule_code)
        return rule, citations

    async def _load_rule_bundles(
        self,
        db: AsyncSession,
        disease_codes: Iterable[str],
        food_code: str,
    ) -> list[RuleBundle]:
        codes = list(disease_codes)
        if not codes:
            return []
        rules = (
            await db.execute(
                select(DiseaseFoodRule).where(
                    DiseaseFoodRule.disease_code.in_(codes),
                    DiseaseFoodRule.food_code == food_code,
                    DiseaseFoodRule.is_enabled.is_(True),
                )
            )
        ).scalars().all()
        citations_map = await self._load_rule_bundles_by_rule_codes(db, [rule.rule_code for rule in rules])
        return [RuleBundle(rule=rule, citations=citations_map.get(rule.rule_code, [])) for rule in rules]

    async def _load_rule_bundles_by_rule_codes(
        self,
        db: AsyncSession,
        rule_codes: list[str],
    ) -> dict[str, list[CitationResponse]]:
        if not rule_codes:
            return {}

        maps = (
            await db.execute(
                select(RuleSourceMap).where(
                    RuleSourceMap.rule_code.in_(rule_codes),
                    RuleSourceMap.is_enabled.is_(True),
                )
            )
        ).scalars().all()
        source_codes = [item.source_code for item in maps]
        sources = (
            await db.execute(
                select(KnowledgeSource).where(
                    KnowledgeSource.source_code.in_(source_codes),
                    KnowledgeSource.is_enabled.is_(True),
                )
            )
        ).scalars().all()
        source_map = {source.source_code: source for source in sources}
        grouped: dict[str, list[CitationResponse]] = defaultdict(list)
        for item in sorted(maps, key=lambda m: (m.rule_code, m.citation_rank, m.id)):
            source = source_map.get(item.source_code)
            if not source:
                continue
            grouped[item.rule_code].append(
                CitationResponse(
                    source_code=source.source_code,
                    source_title=source.source_title,
                    issuing_body=source.issuing_body,
                    source_year=source.source_year,
                    source_version=source.source_version,
                    source_tier=source.source_tier,
                    source_type=source.source_type,
                    localization=source.localization,
                    section_ref=item.section_ref,
                    is_primary=item.is_primary,
                )
            )
        return grouped

    async def _load_disease_cards(self, db: AsyncSession, disease_codes: list[str]) -> list[Disease]:
        if not disease_codes:
            return []
        return list(
            (
                await db.execute(
                    select(Disease).where(
                        Disease.disease_code.in_(disease_codes),
                        Disease.is_enabled.is_(True),
                    )
                )
            ).scalars().all()
        )

    def _resolve_hard_blocks(
        self,
        food: FoodItem,
        normalized: NormalizedConditions,
        manual_restrictions: list[str],
    ) -> list[str]:
        normalized_food_tokens = {
            normalize_food_text(food.food_code),
            normalize_food_text(food.name_zh),
            *(normalize_food_text(alias) for alias in food.aliases_json or []),
            *(normalize_food_text(tag) for tag in food.allergen_tags_json or []),
        }
        reasons: list[str] = []
        for allergy in normalized.allergy_terms:
            if allergy in normalized_food_tokens or any(allergy in token for token in normalized_food_tokens):
                reasons.append(f"过敏约束命中：{allergy}")
        for restriction in manual_restrictions:
            restriction_norm = normalize_food_text(restriction)
            if restriction_norm in normalized_food_tokens or any(restriction_norm in token for token in normalized_food_tokens):
                reasons.append(f"显式忌口命中：{restriction}")
        return self._unique(reasons)

    def _determine_fallback_status(
        self,
        level: RecommendationLevel,
        missing_disease_codes: list[str],
    ) -> FallbackStatus:
        if level in {RecommendationLevel.AVOID, RecommendationLevel.LIMIT}:
            return FallbackStatus.LOCAL_BLOCKED_NO_CLOUD
        if missing_disease_codes:
            return FallbackStatus.LOCAL_PARTIAL_ALLOW_CLOUD
        return FallbackStatus.LOCAL_COMPLETE

    def _build_rule_summary(
        self,
        food: FoodItem,
        bundles: list[RuleBundle],
        missing_disease_codes: list[str],
        user: Optional[User],
    ) -> str:
        parts = [f"{food.name_zh} 的本地规则评估如下："]
        for bundle in bundles:
            parts.append(
                f"{bundle.rule.disease_code} -> {self._level_label(bundle.rule.recommendation_level)}；{bundle.rule.summary_note}"
            )
        if missing_disease_codes:
            parts.append(f"以下病种暂无本地细则：{'、'.join(missing_disease_codes)}。")
        if user and user.nickname:
            parts.append(f"已按用户 {user.nickname} 的健康档案保守聚合。")
        return " ".join(parts)

    def _merge_citations(self, groups: list[list[CitationResponse]]) -> list[CitationResponse]:
        seen: set[Tuple[str, Optional[str]]] = set()
        merged: list[CitationResponse] = []
        for group in groups:
            for citation in group:
                key = (citation.source_code, citation.section_ref)
                if key not in seen:
                    seen.add(key)
                    merged.append(citation)
        return merged

    @staticmethod
    def _unique(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    @staticmethod
    def _level_label(level: Optional[RecommendationLevel]) -> str:
        return level.value if level is not None else "未判定"

    def build_local_guardrail(self, summary: KnowledgeSummary) -> str:
        lines = [
            "以下内容来自本地规则与知识库，必须优先遵守：",
            f"- 来源类型：{summary.origin.value}",
            f"- 降级状态：{summary.fallback_status.value}",
        ]
        for decision in summary.local_decisions:
            lines.append(
                f"- {decision.food_name}: {self._level_label(decision.recommendation_level)}；{decision.summary}"
            )
            if decision.recommendation_level in {RecommendationLevel.AVOID, RecommendationLevel.LIMIT}:
                lines.append("- 该结论为本地约束上限，云端不得放宽，只能解释或给替代方案。")
        if summary.unmapped_conditions:
            lines.append(f"- 未标准化映射的健康档案：{'、'.join(summary.unmapped_conditions)}")
        return "\n".join(lines)

    def render_local_markdown(self, summary: KnowledgeSummary) -> str:
        risk_label = "✅ 安全"
        if any(
            decision.recommendation_level in {RecommendationLevel.AVOID, RecommendationLevel.LIMIT}
            for decision in summary.local_decisions
        ):
            risk_label = "🚫 存在限制"
        elif summary.local_decisions:
            risk_label = "⚠️ 需要条件说明"

        logic_lines = []
        for decision in summary.local_decisions:
            logic_lines.append(
                f"IF {decision.food_name} 命中 {','.join(decision.matched_disease_codes) or '本地知识'} THEN {self._level_label(decision.recommendation_level)}"
            )
        if not logic_lines:
            logic_lines.append("IF 本地知识未命中完整规则 THEN 允许云端补充")

        citations = []
        for citation in summary.citations[:4]:
            citations.append(f"- {citation.source_title}（{citation.issuing_body}）")

        decision_lines = []
        if summary.local_decisions:
            for item in summary.local_decisions:
                decision_lines.append(
                    f"1. **{item.food_name}**：{self._level_label(item.recommendation_level)}，{item.summary}"
                )
                if item.portion_guidance:
                    decision_lines.append(f"2. **份量建议**：{item.portion_guidance}")
                if item.frequency_guidance:
                    decision_lines.append(f"3. **频率建议**：{item.frequency_guidance}")
        else:
            decision_lines.append("1. **结论**：本地知识未命中完整规则，可补充云端查询。")

        return "\n".join(
            [
                "### 🧠 感知",
                summary.summary,
                "",
                "---",
                "",
                "### ⚡ 冲突检测",
                "```text",
                *logic_lines,
                "```",
                "",
                f"**{risk_label}**",
                "",
                "---",
                "",
                "### 📋 归因",
                *(citations if citations else ["- 本次结论主要来自本地规则表与知识库。"]),
                "",
                "---",
                "",
                "### ✅ 决策",
                *decision_lines,
            ]
        )
