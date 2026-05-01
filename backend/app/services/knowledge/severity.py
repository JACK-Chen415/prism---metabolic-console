"""Recommendation severity helpers shared by API routes and services."""

from typing import Optional

from app.models.knowledge import RecommendationLevel


RECOMMENDATION_SEVERITY_ORDER = {
    RecommendationLevel.RECOMMEND: 0,
    RecommendationLevel.MODERATE: 1,
    RecommendationLevel.CONDITIONAL: 2,
    RecommendationLevel.INSUFFICIENT: 3,
    RecommendationLevel.LIMIT: 4,
    RecommendationLevel.AVOID: 5,
}


def pick_strictest_recommendation_level(local_decisions) -> Optional[RecommendationLevel]:
    levels = [
        decision.recommendation_level
        for decision in local_decisions
        if decision.recommendation_level is not None
    ]
    if not levels:
        return None
    return max(levels, key=lambda level: RECOMMENDATION_SEVERITY_ORDER[level])
