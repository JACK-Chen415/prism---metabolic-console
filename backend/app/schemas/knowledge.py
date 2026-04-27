"""Knowledge and local rule API schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.knowledge import (
    ConditionScopeField,
    FallbackStatus,
    KnowledgeOrigin,
    Localization,
    RecommendationLevel,
    SourceConfidence,
    SourceTier,
    SourceType,
)


class DiseaseResponse(BaseModel):
    disease_code: str
    name_zh: str
    aliases: list[str] = Field(default_factory=list)
    summary: str
    risk_note: Optional[str] = None


class FoodItemResponse(BaseModel):
    food_code: str
    name_zh: str
    aliases: list[str] = Field(default_factory=list)
    category: str
    common_units: list[str] = Field(default_factory=list)
    allergen_tags: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    calories_per_100g: Optional[float] = None
    protein_per_100g: Optional[float] = None
    carbs_per_100g: Optional[float] = None
    fat_per_100g: Optional[float] = None
    fiber_per_100g: Optional[float] = None
    sodium_per_100g: Optional[float] = None
    purine_per_100g: Optional[float] = None


class SourceResponse(BaseModel):
    source_code: str
    issuing_body: str
    source_title: str
    source_year: int
    source_version: Optional[str] = None
    source_type: SourceType
    source_tier: SourceTier
    evidence_level: Optional[str] = None
    localization: Localization
    source_url: Optional[str] = None
    document_no: Optional[str] = None
    applicable_disease_codes: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class RuleSourceResponse(BaseModel):
    rule_code: str
    source_code: str
    citation_rank: int
    section_ref: str
    source_note: Optional[str] = None
    is_primary: bool
    source: Optional[SourceResponse] = None


class RuleEvaluationResponse(BaseModel):
    rule_code: str
    disease_code: str
    food_code: str
    recommendation_level: RecommendationLevel
    portion_guidance: Optional[str] = None
    frequency_guidance: Optional[str] = None
    summary_note: str
    needs_warning: bool
    source_confidence: SourceConfidence
    conflict_note: Optional[str] = None
    caution_note: Optional[str] = None
    condition_scope: ConditionScopeField
    applicability_note: Optional[str] = None
    highest_source_tier: SourceTier
    sources: list[RuleSourceResponse] = Field(default_factory=list)


class EvaluateFoodRequest(BaseModel):
    food_name: Optional[str] = Field(None, max_length=100)
    food_code: Optional[str] = Field(None, max_length=100)
    condition_codes: list[str] = Field(default_factory=list)
    manual_restrictions: list[str] = Field(default_factory=list)


class CitationResponse(BaseModel):
    source_code: str
    source_title: str
    issuing_body: str
    source_year: int
    source_version: Optional[str] = None
    source_tier: SourceTier
    source_type: SourceType
    localization: Localization
    section_ref: Optional[str] = None
    is_primary: bool = False


class EvaluateFoodResponse(BaseModel):
    food_code: Optional[str] = None
    food_name: str
    recommendation_level: Optional[RecommendationLevel] = None
    matched_disease_codes: list[str] = Field(default_factory=list)
    hard_blocks: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    portion_guidance: Optional[str] = None
    frequency_guidance: Optional[str] = None
    summary: str
    origin: KnowledgeOrigin
    fallback_status: FallbackStatus
    conflict_note: Optional[str] = None
    caution_note: Optional[str] = None
    citations: list[CitationResponse] = Field(default_factory=list)
    unmapped_conditions: list[str] = Field(default_factory=list)


class KnowledgeSummaryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    condition_codes: list[str] = Field(default_factory=list)
    manual_restrictions: list[str] = Field(default_factory=list)


class KnowledgeSummaryResponse(BaseModel):
    query: str
    matched_disease_codes: list[str] = Field(default_factory=list)
    matched_food_codes: list[str] = Field(default_factory=list)
    summary: str
    origin: KnowledgeOrigin
    fallback_status: FallbackStatus
    can_call_cloud: bool
    conflict_note: Optional[str] = None
    caution_note: Optional[str] = None
    local_decisions: list[EvaluateFoodResponse] = Field(default_factory=list)
    citations: list[CitationResponse] = Field(default_factory=list)
    unmapped_conditions: list[str] = Field(default_factory=list)


class KnowledgeAuditLogResponse(BaseModel):
    id: int
    route_name: str
    origin: KnowledgeOrigin
    fallback_status: FallbackStatus
    matched_disease_codes: list[str] = Field(default_factory=list)
    matched_food_codes: list[str] = Field(default_factory=list)
    local_decision_level: Optional[RecommendationLevel] = None
    called_cloud: bool
    cloud_call_reason: Optional[str] = None
    cloud_blocked_reason: Optional[str] = None
    created_at: datetime
