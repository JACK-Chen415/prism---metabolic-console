"""Read-only knowledge and local rule APIs."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.health_condition import HealthCondition
from app.core.config import settings
from app.models.knowledge import (
    DEFAULT_NUTRITION_ESTIMATE_QUALITY,
    DEFAULT_NUTRITION_REVIEW_STATUS,
    DEFAULT_NUTRITION_SOURCE_CODE,
    DEFAULT_NUTRITION_SOURCE_DETAIL,
    Disease,
    FoodItem,
    FallbackStatus,
    KnowledgeOrigin,
    KnowledgeSource,
)
from app.schemas.knowledge import (
    DiseaseResponse,
    EvaluateFoodRequest,
    EvaluateFoodResponse,
    FoodItemResponse,
    KnowledgeSummaryRequest,
    KnowledgeSummaryResponse,
    PackagedFoodBarcodeLookupRequest,
    PackagedFoodCandidateResponse,
    PackagedFoodLabelNormalizeRequest,
    PackagedFoodLookupResponse,
    RuleEvaluationResponse,
    RuleSourceResponse,
    SourceResponse,
)
from app.services.knowledge import KnowledgeService, write_knowledge_audit_log
from app.services.knowledge.matcher import normalize_food_text
from app.services.packaged_food import (
    PACKAGED_FOOD_DISCLAIMER,
    PackagedFoodCandidate,
    PackagedFoodLookupService,
    PackagedFoodProviderRegistry,
    build_manual_label_candidate,
    normalize_barcode,
)

router = APIRouter(prefix="/knowledge", tags=["知识库"])
knowledge_service = KnowledgeService()
packaged_food_service = PackagedFoodLookupService(
    provider=PackagedFoodProviderRegistry(settings.packaged_food_provider).get_provider(),
    knowledge_service=knowledge_service,
)


async def _get_user_conditions(user_id: int, db: DbSession) -> list[HealthCondition]:
    return list(
        (
            await db.execute(select(HealthCondition).where(HealthCondition.user_id == user_id))
        ).scalars().all()
    )


def _food_to_response(food: FoodItem) -> FoodItemResponse:
    return FoodItemResponse(
        food_code=food.food_code,
        barcode=food.barcode,
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
        nutrition_source_code=food.nutrition_source_code or DEFAULT_NUTRITION_SOURCE_CODE,
        nutrition_source_detail=food.nutrition_source_detail or DEFAULT_NUTRITION_SOURCE_DETAIL,
        nutrition_estimate_quality=food.nutrition_estimate_quality or DEFAULT_NUTRITION_ESTIMATE_QUALITY,
        nutrition_review_status=food.nutrition_review_status or DEFAULT_NUTRITION_REVIEW_STATUS,
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


def _unique_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _packaged_review_reasons(candidate: PackagedFoodCandidate, decision: EvaluateFoodResponse) -> list[str]:
    reasons: list[str] = []
    if candidate.provider_status.value in {"mock", "planned"}:
        reasons.append("mock_or_planned_provider")
    if candidate.confidence < 0.85:
        reasons.append("provider_confidence_below_review_threshold")
    if candidate.nutrition_review_status != "REVIEWED":
        reasons.append("nutrition_label_needs_user_review")
    if decision.hard_blocks:
        reasons.append("hard_block_requires_review")
    decision_level = decision.recommendation_level.value if decision.recommendation_level else None
    if decision_level in {"AVOID", "LIMIT", "INSUFFICIENT"}:
        reasons.append("local_rule_requires_review")
    if candidate.risk_tags:
        reasons.append("risk_tags_present")
    return _unique_values(reasons)


def _packaged_candidate_to_response(
    candidate: PackagedFoodCandidate,
    decision: EvaluateFoodResponse,
) -> PackagedFoodCandidateResponse:
    review_reasons = _packaged_review_reasons(candidate, decision)
    return PackagedFoodCandidateResponse(
        barcode_last4=candidate.barcode_last4,
        food_name=candidate.food_name,
        brand=candidate.brand,
        category=candidate.category,
        serving_size=candidate.serving_size,
        serving_size_g=candidate.serving_size_g,
        calories_per_100g=candidate.calories_per_100g,
        protein_per_100g=candidate.protein_per_100g,
        carbs_per_100g=candidate.carbs_per_100g,
        fat_per_100g=candidate.fat_per_100g,
        fiber_per_100g=candidate.fiber_per_100g,
        sodium_per_100g=candidate.sodium_per_100g,
        sugar_per_100g=candidate.sugar_per_100g,
        purine_per_100g=candidate.purine_per_100g,
        ingredients=list(candidate.ingredients),
        allergen_tags=list(candidate.allergen_tags),
        risk_tags=list(candidate.risk_tags),
        nutrition_source_code=candidate.nutrition_source_code,
        nutrition_source_detail=candidate.nutrition_source_detail,
        nutrition_estimate_quality=candidate.nutrition_estimate_quality,
        nutrition_review_status=candidate.nutrition_review_status,
        provider=candidate.provider,
        provider_status=candidate.provider_status.value,
        confidence=candidate.confidence,
        review_required=bool(review_reasons),
        review_reasons=review_reasons,
        notes=list(candidate.notes),
        local_decision=decision,
        disclaimer=PACKAGED_FOOD_DISCLAIMER,
    )


def _strictest_fallback_status(items: list[EvaluateFoodResponse]):
    order = {
        "NO_LOCAL_MATCH_ALLOW_CLOUD": 0,
        "LOCAL_PARTIAL_ALLOW_CLOUD": 1,
        "LOCAL_COMPLETE": 2,
        "LOCAL_BLOCKED_NO_CLOUD": 3,
    }
    if not items:
        return None
    return max(items, key=lambda item: order.get(item.fallback_status.value, 0)).fallback_status


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
    q_norm = normalize_food_text(q)
    risk_norm = (risk_tag or "").strip().lower()
    for food in foods:
        if category and food.category != category:
            continue
        if q_norm:
            candidates = [food.food_code, food.name_zh, *(food.aliases_json or [])]
            normalized_candidates = [normalize_food_text(candidate) for candidate in candidates if candidate]
            if not any(q_norm in candidate for candidate in normalized_candidates):
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


@router.post("/packaged-food/barcode", response_model=PackagedFoodLookupResponse)
async def lookup_packaged_food_barcode(
    payload: PackagedFoodBarcodeLookupRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    try:
        normalized_barcode = normalize_barcode(payload.barcode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    conditions = await _get_user_conditions(current_user.id, db)
    results = await packaged_food_service.lookup_barcode(
        db,
        user=current_user,
        conditions=conditions,
        barcode=normalized_barcode,
        explicit_condition_codes=payload.condition_codes,
        manual_restrictions=payload.manual_restrictions,
    )
    responses = [
        _packaged_candidate_to_response(candidate, EvaluateFoodResponse(**decision.model_dump()))
        for candidate, decision in results
    ]
    fallback_status = _strictest_fallback_status([item.local_decision for item in responses])
    await write_knowledge_audit_log(
        db,
        user_id=current_user.id,
        route_name="/api/knowledge/packaged-food/barcode",
        origin=responses[0].local_decision.origin if responses else KnowledgeOrigin.LOCAL_KNOWLEDGE,
        fallback_status=fallback_status or FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
        matched_disease_codes=_unique_values([
            code
            for item in responses
            for code in item.local_decision.matched_disease_codes
        ]),
        matched_food_codes=_unique_values([
            item.local_decision.food_code
            for item in responses
            if item.local_decision.food_code
        ]),
        unmapped_conditions=_unique_values([
            code
            for item in responses
            for code in item.local_decision.unmapped_conditions
        ]),
        local_decision_level=responses[0].local_decision.recommendation_level if responses else None,
        called_cloud=False,
        cloud_blocked_reason="packaged_food_local_review_required" if any(item.review_required for item in responses) else None,
        query_excerpt=f"barcode_last4:{normalized_barcode[-4:]}",
    )
    return PackagedFoodLookupResponse(
        provider=packaged_food_service.provider.provider,
        provider_status=packaged_food_service.provider.status.value,
        barcode_last4=normalized_barcode[-4:],
        matched=bool(responses),
        candidates=responses,
        disclaimer=PACKAGED_FOOD_DISCLAIMER,
    )


@router.post("/packaged-food/label", response_model=PackagedFoodCandidateResponse)
async def normalize_packaged_food_label(
    payload: PackagedFoodLabelNormalizeRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    try:
        candidate = build_manual_label_candidate(
            product_name=payload.product_name,
            brand=payload.brand,
            barcode=payload.barcode,
            category=payload.category,
            serving_size=payload.serving_size,
            serving_size_g=payload.serving_size_g,
            calories_per_100g=payload.calories_per_100g,
            protein_per_100g=payload.protein_per_100g,
            carbs_per_100g=payload.carbs_per_100g,
            fat_per_100g=payload.fat_per_100g,
            fiber_per_100g=payload.fiber_per_100g,
            sodium_per_100g=payload.sodium_per_100g,
            sugar_per_100g=payload.sugar_per_100g,
            purine_per_100g=payload.purine_per_100g,
            ingredients=payload.ingredients,
            allergen_tags=payload.allergen_tags,
            risk_tags=payload.risk_tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    conditions = await _get_user_conditions(current_user.id, db)
    candidate, decision = await packaged_food_service.normalize_label(
        db,
        user=current_user,
        conditions=conditions,
        candidate=candidate,
        explicit_condition_codes=payload.condition_codes,
        manual_restrictions=payload.manual_restrictions,
    )
    response = _packaged_candidate_to_response(
        candidate,
        EvaluateFoodResponse(**decision.model_dump()),
    )
    await write_knowledge_audit_log(
        db,
        user_id=current_user.id,
        route_name="/api/knowledge/packaged-food/label",
        origin=response.local_decision.origin,
        fallback_status=response.local_decision.fallback_status,
        matched_disease_codes=response.local_decision.matched_disease_codes,
        matched_food_codes=[response.local_decision.food_code] if response.local_decision.food_code else [],
        unmapped_conditions=response.local_decision.unmapped_conditions,
        local_decision_level=response.local_decision.recommendation_level,
        called_cloud=False,
        cloud_blocked_reason="packaged_food_local_review_required" if response.review_required else None,
        query_excerpt=f"manual_label:{response.food_name}",
    )
    return response


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
