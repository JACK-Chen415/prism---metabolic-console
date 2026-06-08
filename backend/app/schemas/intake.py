"""Schemas for multimodal intake parsing and confirmation."""

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.feedback import AIFeedbackType
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


class IntakeParseStatus(str, Enum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    REFUSED = "refused"


REVIEW_TELEMETRY_SOURCE_KEYS = {"manual", "voice", "photo", "ai_quick_log", "unknown"}
REVIEW_TELEMETRY_STATUS_KEYS = {"PENDING_REVIEW", "IN_REVIEW"}


def _validate_count_map(value: dict[str, int], allowed_keys: set[str]) -> dict[str, int]:
    clean: dict[str, int] = {}
    for key, count in (value or {}).items():
        normalized_key = str(key).strip()
        if normalized_key not in allowed_keys:
            raise ValueError(f"unsupported telemetry key: {normalized_key}")
        normalized_count = int(count)
        if normalized_count < 0 or normalized_count > 5000:
            raise ValueError("telemetry counts must be between 0 and 5000")
        if normalized_count:
            clean[normalized_key] = normalized_count
    return clean


class IntakeReviewTelemetryRequest(BaseModel):
    total_count: int = Field(0, ge=0, le=5000)
    pending_review_count: int = Field(0, ge=0, le=5000)
    in_review_count: int = Field(0, ge=0, le=5000)
    low_confidence_count: int = Field(0, ge=0, le=5000)
    high_risk_count: int = Field(0, ge=0, le=5000)
    hard_block_count: int = Field(0, ge=0, le=5000)
    source_counts: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)

    @field_validator("source_counts")
    @classmethod
    def validate_source_counts(cls, value: dict[str, int]) -> dict[str, int]:
        return _validate_count_map(value, REVIEW_TELEMETRY_SOURCE_KEYS)

    @field_validator("status_counts")
    @classmethod
    def validate_status_counts(cls, value: dict[str, int]) -> dict[str, int]:
        return _validate_count_map(value, REVIEW_TELEMETRY_STATUS_KEYS)


class IntakeReviewTelemetryResponse(BaseModel):
    id: int
    received_at: datetime
    total_count: int
    pending_review_count: int
    in_review_count: int
    low_confidence_count: int
    high_risk_count: int
    hard_block_count: int
    source_counts: dict[str, int]
    status_counts: dict[str, int]
    notes: list[str] = Field(default_factory=list)


INTAKE_CANDIDATE_FEEDBACK_TYPES = {
    AIFeedbackType.RECOGNITION_CORRECTION,
    AIFeedbackType.CORRECTION,
    AIFeedbackType.KNOWLEDGE_GAP,
}


class IntakeCandidateFeedbackRequest(BaseModel):
    draft_id: str = Field(..., min_length=1, max_length=120)
    source: IntakeSource
    feedback_type: AIFeedbackType = AIFeedbackType.RECOGNITION_CORRECTION
    rating: Optional[int] = Field(1, ge=1, le=5)
    tags: list[str] = Field(default_factory=list, max_length=12)
    correction_text: str = Field(..., min_length=1, max_length=2000)
    metadata: Optional[dict[str, Any]] = None

    @field_validator("feedback_type")
    @classmethod
    def validate_feedback_type(cls, value: AIFeedbackType) -> AIFeedbackType:
        if value not in INTAKE_CANDIDATE_FEEDBACK_TYPES:
            raise ValueError("intake candidate feedback must be correction, recognition_correction, or knowledge_gap")
        return value


class VoiceParseRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=1000)
    meal_time_hint: Optional[str] = Field(None, max_length=50)
    record_date: Optional[date] = None


class TextParseRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    context_text: Optional[str] = Field(None, max_length=2000)
    meal_time_hint: Optional[str] = Field(None, max_length=50)
    record_date: Optional[date] = None


class VoiceAutoLogRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=1000)
    meal_time_hint: Optional[str] = Field(None, max_length=50)
    record_date: Optional[date] = None
    auto_confirm: bool = True


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
    seasonings: list[str] = Field(default_factory=list)
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
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    review_confirmed: bool = False


class IntakeDraftSessionResponse(BaseModel):
    source: IntakeSource
    status: IntakeParseStatus = IntakeParseStatus.READY
    raw_input_text: Optional[str] = None
    raw_summary: Optional[str] = None
    record_date: date
    meal_time_hint: Optional[str] = None
    candidates: list[IntakeCandidate] = Field(default_factory=list)
    summary_warning: Optional[str] = None
    missing_fields: list[str] = Field(default_factory=list)
    follow_up_prompt: Optional[str] = None
    refusal_reason: Optional[str] = None


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
    seasonings: list[str] = Field(default_factory=list, max_length=20)
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
    manual_restrictions: list[str] = Field(default_factory=list)
    origin: KnowledgeOrigin
    fallback_status: FallbackStatus
    citations: list[CitationResponse] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list, max_length=10)
    review_confirmed: bool = False
    recognition_meta: Optional[dict[str, Any]] = None


class IntakeCandidateAlternative(BaseModel):
    food_code: str
    food_name: str
    category: FoodCategory
    recommendation_level: Optional[RecommendationLevel] = None
    reason: str
    calories_per_100g: Optional[float] = None
    sodium_per_100g: Optional[float] = None
    purine_per_100g: Optional[float] = None
    allergen_tags: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    citations: list[CitationResponse] = Field(default_factory=list)


class IntakeCandidateAlternativesRequest(BaseModel):
    candidate: IntakeConfirmItem
    limit: int = Field(3, ge=1, le=5)


class IntakeCandidateAlternativesResponse(BaseModel):
    draft_id: str
    generated_at: datetime
    alternatives: list[IntakeCandidateAlternative] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class IntakeConfirmRequest(BaseModel):
    source: IntakeSource
    raw_input_text: Optional[str] = Field(None, max_length=2000)
    raw_summary: Optional[str] = Field(None, max_length=4000)
    record_date: Optional[date] = None
    candidates: list[IntakeConfirmItem] = Field(default_factory=list)


class IntakeConfirmPreviewRequest(BaseModel):
    record_date: Optional[date] = None
    candidates: list[IntakeConfirmItem] = Field(default_factory=list)


class IntakeConfirmImpactMetric(BaseModel):
    key: str
    label: str
    unit: str
    current: float = 0
    pending: float = 0
    projected: float = 0
    target: Optional[float] = None
    ratio: Optional[float] = None
    status: str


class IntakeConfirmPreviewResponse(BaseModel):
    record_date: date
    generated_at: datetime
    meal_count: int = 0
    metrics: list[IntakeConfirmImpactMetric] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    will_create_meal: bool = False


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
