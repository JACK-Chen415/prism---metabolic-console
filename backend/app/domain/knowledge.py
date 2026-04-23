"""Disease and dietary-constraint domain skeletons for the future knowledge base."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class DiseaseCategory(str, Enum):
    CHRONIC = "chronic"
    ALLERGY = "allergy"
    METABOLIC = "metabolic"
    OTHER = "other"


class ConstraintLevel(str, Enum):
    AVOID = "avoid"
    LIMIT = "limit"
    PREFER = "prefer"
    MONITOR = "monitor"


class DiseaseEntity(BaseModel):
    code: str
    name: str
    category: DiseaseCategory


class DietaryConstraint(BaseModel):
    disease_code: str
    level: ConstraintLevel
    nutrient_code: Optional[str] = None
    food_id: Optional[str] = None
    rationale: Optional[str] = None
    source: Optional[str] = None
