"""Schemas for multimodal intake parsing and confirmation."""

from datetime import date
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.knowledge import FallbackStatus, KnowledgeOrigin, RecommendationLevel
from app.models.meal import FoodCategory, MealType
from app.schemas.chat import FoodRecognitionResult
from app.schemas.knowledge import CitationResponse
from app.schemas.meal import MealResponse


class IntakeSource(str, Enum):
    MANUAL = "manual"
    VOICE = "voice"
    PHOTO = "photo"
    AI_QUICK_LOG = "ai_quick_log"


class VoiceParseRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=1000)
    meal_time_hint: Optional[str] = Field(None, max_length=50)
    record_date: Optional[date] = None


class PhotoParseRequest(BaseModel):
    recognized_foods: list[FoodRecognitionResult] = Field(default_factory=list)
    ai_response: Optional[str] = Field(None, max_length=4000)
    meal_time_hint: Optional[str] = Field(None, max_length=50)
    record_date: Optional[date] = None


class IntakeCandidate(BaseModel):
    draft_id: str
    source: IntakeSource
    meal_type: MealType
    category: FoodCategory
    food_name: str
    food_code: Optional[str] = None
    amount_text: str = "1份"
    normalized_amount: Optional[float] = None
    unit: Optional[str] = None
    time_hint: Optional[str] = None
    note: Optional[str] = None
    confidence: float = 0.0
    ingredients: list[str] = Field(default_factory=list)
    cooking_method: Optional[str] = None
    calories: Optional[float] = None
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    fiber: Optional[float] = None
    sodium: Optional[float] = None
    sugar: Optional[float] = None
    purine: Optional[float] = None
    allergen_tags: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    estimated_fields: list[str] = Field(default_factory=list)
    estimated_notes: list[str] = Field(default_factory=list)
    local_rule_hit: bool = False
    matched_disease_codes: list[str] = Field(default_factory=list)
    recommendation_level: Optional[RecommendationLevel] = None
    warnings: list[str] = Field(default_factory=list)
    citations: list[CitationResponse] = Field(default_factory=list)
    origin: KnowledgeOrigin
    fallback_status: FallbackStatus
    conflict_note: Optional[str] = None
    caution_note: Optional[str] = None


class IntakeDraftSessionResponse(BaseModel):
    source: IntakeSource
    raw_input_text: Optional[str] = None
    raw_summary: Optional[str] = None
    record_date: date
    meal_time_hint: Optional[str] = None
    candidates: list[IntakeCandidate] = Field(default_factory=list)
    summary_warning: Optional[str] = None


class IntakeConfirmItem(BaseModel):
    draft_id: str
    source: IntakeSource
    meal_type: MealType
    category: FoodCategory
    food_name: str = Field(..., min_length=1, max_length=100)
    food_code: Optional[str] = Field(None, max_length=100)
    amount_text: Optional[str] = Field(None, max_length=50)
    normalized_amount: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = Field(None, max_length=20)
    note: Optional[str] = Field(None, max_length=500)
    confidence: Optional[float] = Field(None, ge=0, le=1)
    ingredients: list[str] = Field(default_factory=list)
    cooking_method: Optional[str] = Field(None, max_length=100)
    calories: Optional[float] = Field(None, ge=0)
    protein: Optional[float] = Field(None, ge=0)
    carbs: Optional[float] = Field(None, ge=0)
    fat: Optional[float] = Field(None, ge=0)
    fiber: Optional[float] = Field(None, ge=0)
    sodium: Optional[float] = Field(None, ge=0)
    sugar: Optional[float] = Field(None, ge=0)
    purine: Optional[float] = Field(None, ge=0)
    allergen_tags: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    estimated_fields: list[str] = Field(default_factory=list)
    estimated_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    origin: KnowledgeOrigin
    fallback_status: FallbackStatus
    citations: list[CitationResponse] = Field(default_factory=list)
    recognition_meta: Optional[dict[str, Any]] = None


class IntakeConfirmRequest(BaseModel):
    source: IntakeSource
    raw_input_text: Optional[str] = Field(None, max_length=2000)
    raw_summary: Optional[str] = Field(None, max_length=4000)
    record_date: Optional[date] = None
    candidates: list[IntakeConfirmItem] = Field(default_factory=list)


class IntakeConfirmFailure(BaseModel):
    draft_id: str
    food_name: str
    reason: str


class IntakeConfirmResponse(BaseModel):
    meals: list[MealResponse] = Field(default_factory=list)
    meal_ids: list[int] = Field(default_factory=list)
    warning_summary: list[str] = Field(default_factory=list)
    failed_items: list[IntakeConfirmFailure] = Field(default_factory=list)
    should_refresh_log: bool = True
    should_refresh_home: bool = True
