"""Audit logging helpers for local knowledge decisions."""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import FallbackStatus, KnowledgeAuditLog, KnowledgeOrigin, RecommendationLevel


async def write_knowledge_audit_log(
    db: AsyncSession,
    *,
    user_id: Optional[int],
    route_name: str,
    origin: KnowledgeOrigin,
    fallback_status: FallbackStatus,
    matched_disease_codes: list[str],
    matched_food_codes: list[str],
    unmapped_conditions: Optional[list[str]] = None,
    local_decision_level: Optional[RecommendationLevel] = None,
    called_cloud: bool = False,
    cloud_call_reason: Optional[str] = None,
    cloud_blocked_reason: Optional[str] = None,
    query_excerpt: Optional[str] = None,
    chat_session_id: Optional[int] = None,
    chat_message_id: Optional[int] = None,
) -> KnowledgeAuditLog:
    log = KnowledgeAuditLog(
        user_id=user_id,
        route_name=route_name,
        chat_session_id=chat_session_id,
        chat_message_id=chat_message_id,
        query_excerpt=(query_excerpt or "")[:500] or None,
        origin=origin,
        fallback_status=fallback_status,
        matched_disease_codes_json=matched_disease_codes,
        matched_food_codes_json=matched_food_codes,
        unmapped_conditions_json=unmapped_conditions or [],
        local_decision_level=local_decision_level,
        called_cloud=called_cloud,
        cloud_call_reason=cloud_call_reason,
        cloud_blocked_reason=cloud_blocked_reason,
    )
    db.add(log)
    await db.flush()
    return log
