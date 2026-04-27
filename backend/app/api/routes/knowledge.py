"""Read-only knowledge and local rule APIs."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.health_condition import HealthCondition
from app.models.knowledge import Disease, FoodItem, KnowledgeSource
from app.schemas.knowledge import (
    DiseaseResponse,
    EvaluateFoodRequest,
    EvaluateFoodResponse,
    FoodItemResponse,
    KnowledgeSummaryRequest,
    KnowledgeSummaryResponse,
    RuleEvaluationResponse,
    RuleSourceResponse,
    SourceResponse,
)
from app.services.knowledge import KnowledgeService, write_knowledge_audit_log

router = APIRouter(prefix="/knowledge", tags=["知识库"])
knowledge_service = KnowledgeService()


async def _get_user_conditions(user_id: int, db: DbSession) -> list[HealthCondition]:
    return list(
        (
            await db.execute(select(HealthCondition).where(HealthCondition.user_id == user_id))
        ).scalars().all()
    )


def _food_to_response(food: FoodItem) -> FoodItemResponse:
    return FoodItemResponse(
        food_code=food.food_code,
        name_zh=food.name_zh,
        aliases=food.aliases_json or [],
        category=food.category,
        common_units=food.common_units_json or [],
        allergen_tags=food.allergen_tags_json or [],
        risk_tags=food.risk_tags_json or [],
        calories_per_100g=food.calories_per_100g,
        protein_per_100g=food.protein_per_100g,
        carbs_per_100g=food.carbs_per_100g,
        fat_per_100g=food.fat_per_100g,
        fiber_per_100g=food.fiber_per_100g,
        sodium_per_100g=food.sodium_per_100g,
        purine_per_100g=food.purine_per_100g,
    )


def _source_to_response(source: KnowledgeSource) -> SourceResponse:
    return SourceResponse(
        source_code=source.source_code,
        issuing_body=source.issuing_body,
        source_title=source.source_title,
        source_year=source.source_year,
        source_version=source.source_version,
        source_type=source.source_type,
        source_tier=source.source_tier,
        evidence_level=source.evidence_level,
        localization=source.localization,
        source_url=source.source_url,
        document_no=source.document_no,
        applicable_disease_codes=source.applicable_disease_codes_json or [],
        notes=source.notes,
    )


@router.get("/diseases", response_model=list[DiseaseResponse])
async def list_diseases(current_user: CurrentUser, db: DbSession):
    del current_user
    diseases = (
        await db.execute(
            select(Disease).where(Disease.is_enabled.is_(True)).order_by(Disease.id.asc())
        )
    ).scalars().all()
    return [
        DiseaseResponse(
            disease_code=disease.disease_code,
            name_zh=disease.name_zh,
            aliases=disease.aliases_json or [],
            summary=disease.summary,
            risk_note=disease.risk_note,
        )
        for disease in diseases
    ]


@router.get("/foods", response_model=list[FoodItemResponse])
async def list_foods(
    current_user: CurrentUser,
    db: DbSession,
    q: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    risk_tag: Optional[str] = Query(None),
):
    del current_user
    foods = (
        await db.execute(select(FoodItem).where(FoodItem.is_enabled.is_(True)))
    ).scalars().all()
    results = []
    q_norm = (q or "").strip().lower()
    risk_norm = (risk_tag or "").strip().lower()
    for food in foods:
        if category and food.category != category:
            continue
        if q_norm:
            candidates = [food.food_code, food.name_zh, *(food.aliases_json or [])]
            if not any(q_norm in str(candidate).lower() for candidate in candidates):
                continue
        if risk_norm and not any(risk_norm == str(tag).lower() for tag in food.risk_tags_json or []):
            continue
        results.append(_food_to_response(food))
    return results


@router.get("/foods/{food_code}", response_model=FoodItemResponse)
async def get_food_detail(food_code: str, current_user: CurrentUser, db: DbSession):
    del current_user
    food = (
        await db.execute(
            select(FoodItem).where(
                FoodItem.food_code == food_code,
                FoodItem.is_enabled.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not food:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="食物不存在")
    return _food_to_response(food)


@router.get("/rules/evaluate", response_model=RuleEvaluationResponse)
async def evaluate_rule_pair(
    disease_code: str,
    food_code: str,
    current_user: CurrentUser,
    db: DbSession,
):
    del current_user
    rule, citations = await knowledge_service.get_rule_for_pair(db, disease_code, food_code)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到规则")
    return RuleEvaluationResponse(
        rule_code=rule.rule_code,
        disease_code=rule.disease_code,
        food_code=rule.food_code,
        recommendation_level=rule.recommendation_level,
        portion_guidance=rule.portion_guidance,
        frequency_guidance=rule.frequency_guidance,
        summary_note=rule.summary_note,
        needs_warning=rule.needs_warning,
        source_confidence=rule.source_confidence,
        conflict_note=rule.conflict_note,
        caution_note=rule.caution_note,
        condition_scope=rule.condition_scope,
        applicability_note=rule.applicability_note,
        highest_source_tier=rule.highest_source_tier,
        sources=[
            RuleSourceResponse(
                rule_code=rule.rule_code,
                source_code=citation.source_code,
                citation_rank=index + 1,
                section_ref=citation.section_ref or "",
                is_primary=citation.is_primary,
                source=SourceResponse(
                    source_code=citation.source_code,
                    issuing_body=citation.issuing_body,
                    source_title=citation.source_title,
                    source_year=citation.source_year,
                    source_version=citation.source_version,
                    source_type=citation.source_type,
                    source_tier=citation.source_tier,
                    localization=citation.localization,
                ),
            )
            for index, citation in enumerate(citations)
        ],
    )


@router.get("/rules/{rule_code}/sources", response_model=list[RuleSourceResponse])
async def list_rule_sources(rule_code: str, current_user: CurrentUser, db: DbSession):
    del current_user
    citations = await knowledge_service.get_rule_sources(db, rule_code)
    if not citations:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到规则来源")
    return [
        RuleSourceResponse(
            rule_code=rule_code,
            source_code=citation.source_code,
            citation_rank=index + 1,
            section_ref=citation.section_ref or "",
            is_primary=citation.is_primary,
            source=SourceResponse(
                source_code=citation.source_code,
                issuing_body=citation.issuing_body,
                source_title=citation.source_title,
                source_year=citation.source_year,
                source_version=citation.source_version,
                source_type=citation.source_type,
                source_tier=citation.source_tier,
                localization=citation.localization,
            ),
        )
        for index, citation in enumerate(citations)
    ]


@router.get("/sources", response_model=list[SourceResponse])
async def list_sources(
    current_user: CurrentUser,
    db: DbSession,
    tier: Optional[str] = Query(None),
    disease_code: Optional[str] = Query(None),
    localization: Optional[str] = Query(None),
):
    del current_user
    sources = (
        await db.execute(select(KnowledgeSource).where(KnowledgeSource.is_enabled.is_(True)))
    ).scalars().all()
    results = []
    for source in sources:
        if tier and source.source_tier.value != tier:
            continue
        if localization and source.localization.value != localization:
            continue
        if disease_code and disease_code not in (source.applicable_disease_codes_json or []):
            continue
        results.append(_source_to_response(source))
    return results


@router.post("/evaluate-food", response_model=EvaluateFoodResponse)
async def evaluate_food_for_user(
    payload: EvaluateFoodRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await _get_user_conditions(current_user.id, db)
    decision = await knowledge_service.evaluate_food_for_user(
        db,
        user=current_user,
        conditions=conditions,
        food_name=payload.food_name,
        food_code=payload.food_code,
        explicit_condition_codes=payload.condition_codes,
        manual_restrictions=payload.manual_restrictions,
    )
    await write_knowledge_audit_log(
        db,
        user_id=current_user.id,
        route_name="/api/knowledge/evaluate-food",
        origin=decision.origin,
        fallback_status=decision.fallback_status,
        matched_disease_codes=decision.matched_disease_codes,
        matched_food_codes=[decision.food_code] if decision.food_code else [],
        unmapped_conditions=decision.unmapped_conditions,
        local_decision_level=decision.recommendation_level,
        called_cloud=False,
        cloud_blocked_reason=(
            "本地命中 AVOID/LIMIT/过敏约束，未触发云端"
            if decision.fallback_status.value == "LOCAL_BLOCKED_NO_CLOUD"
            else None
        ),
        query_excerpt=payload.food_name or payload.food_code,
    )
    return EvaluateFoodResponse(**decision.model_dump())


@router.post("/summarize", response_model=KnowledgeSummaryResponse)
async def summarize_knowledge(
    payload: KnowledgeSummaryRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await _get_user_conditions(current_user.id, db)
    summary = await knowledge_service.summarize_query_for_user(
        db,
        user=current_user,
        conditions=conditions,
        query=payload.query,
        explicit_condition_codes=payload.condition_codes,
        manual_restrictions=payload.manual_restrictions,
    )
    await write_knowledge_audit_log(
        db,
        user_id=current_user.id,
        route_name="/api/knowledge/summarize",
        origin=summary.origin,
        fallback_status=summary.fallback_status,
        matched_disease_codes=summary.matched_disease_codes,
        matched_food_codes=summary.matched_food_codes,
        unmapped_conditions=summary.unmapped_conditions,
        local_decision_level=summary.local_decisions[0].recommendation_level if summary.local_decisions else None,
        called_cloud=False,
        query_excerpt=payload.query,
    )
    return KnowledgeSummaryResponse(
        query=summary.query,
        matched_disease_codes=summary.matched_disease_codes,
        matched_food_codes=summary.matched_food_codes,
        summary=summary.summary,
        origin=summary.origin,
        fallback_status=summary.fallback_status,
        can_call_cloud=summary.can_call_cloud,
        local_decisions=[EvaluateFoodResponse(**decision.model_dump()) for decision in summary.local_decisions],
        citations=summary.citations,
        unmapped_conditions=summary.unmapped_conditions,
    )
