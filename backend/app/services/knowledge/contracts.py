"""Internal contracts for local knowledge and rule evaluation."""

from typing import Optional

from pydantic import BaseModel, Field

from app.models.knowledge import FallbackStatus, KnowledgeOrigin, RecommendationLevel
from app.schemas.knowledge import CitationResponse


class NormalizedConditions(BaseModel):
    disease_codes: list[str] = Field(default_factory=list)
    allergy_terms: list[str] = Field(default_factory=list)
    unmapped_conditions: list[str] = Field(default_factory=list)


class LocalDecision(BaseModel):
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
    citations: list[CitationResponse] = Field(default_factory=list)
    conflict_note: Optional[str] = None
    caution_note: Optional[str] = None
    unmapped_conditions: list[str] = Field(default_factory=list)


class KnowledgeSummary(BaseModel):
    query: str
    matched_disease_codes: list[str] = Field(default_factory=list)
    matched_food_codes: list[str] = Field(default_factory=list)
    summary: str
    origin: KnowledgeOrigin
    fallback_status: FallbackStatus
    can_call_cloud: bool
    local_decisions: list[LocalDecision] = Field(default_factory=list)
    citations: list[CitationResponse] = Field(default_factory=list)
    conflict_note: Optional[str] = None
    caution_note: Optional[str] = None
    unmapped_conditions: list[str] = Field(default_factory=list)
