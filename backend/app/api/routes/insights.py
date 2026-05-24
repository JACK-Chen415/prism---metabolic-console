"""Smart insight API routes."""

from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.api.routes.messages import MessageResponse
from app.services.insights import SmartInsightMessageService


class InsightRefreshResponse(BaseModel):
    target_date: str
    generated_count: int
    messages: List[MessageResponse]


router = APIRouter(prefix="/insights", tags=["智能洞察"])
insight_message_service = SmartInsightMessageService()


@router.post("/refresh", response_model=InsightRefreshResponse)
async def refresh_insights(current_user: CurrentUser, db: DbSession):
    """Regenerate today's smart insight messages for the current user."""
    result = await insight_message_service.refresh_today(db, user=current_user)
    return InsightRefreshResponse(
        target_date=result.target_date.isoformat(),
        generated_count=result.generated_count,
        messages=[MessageResponse.model_validate(message) for message in result.messages],
    )


@router.get("/today", response_model=List[MessageResponse])
async def get_today_insights(current_user: CurrentUser, db: DbSession):
    """Return persisted smart insight messages for today."""
    messages = await insight_message_service.list_today(db, user=current_user)
    return [MessageResponse.model_validate(message) for message in messages]
