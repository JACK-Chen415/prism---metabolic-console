"""Rule-evaluation contracts reserved for recommendation safety checks."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class RecommendationSeverity(str, Enum):
    INFO = "info"
    CAUTION = "caution"
    BLOCK = "block"


class RuleCheckContext(BaseModel):
    user_id: int
    condition_codes: list[str] = []
    allergy_codes: list[str] = []


class RuleCheckResult(BaseModel):
    severity: RecommendationSeverity
    message: str
    source: Optional[str] = None
