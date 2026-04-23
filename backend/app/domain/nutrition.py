"""
Nutrition domain skeleton.

This module intentionally contains only portable data contracts. The next phase
can back these contracts with a food database without changing API-facing code.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class FoodUnit(str, Enum):
    GRAM = "g"
    MILLILITER = "ml"
    SERVING = "serving"
    PIECE = "piece"


class NutrientCode(str, Enum):
    CALORIES = "calories"
    PROTEIN = "protein"
    CARBS = "carbs"
    FAT = "fat"
    FIBER = "fiber"
    SODIUM = "sodium"
    PURINE = "purine"


class FoodEntity(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    default_unit: FoodUnit = FoodUnit.GRAM
    source: Optional[str] = None


class NutrientProfile(BaseModel):
    food_id: str
    per_amount: float = Field(gt=0)
    unit: FoodUnit
    nutrients: dict[NutrientCode, float] = Field(default_factory=dict)
    source: Optional[str] = None
