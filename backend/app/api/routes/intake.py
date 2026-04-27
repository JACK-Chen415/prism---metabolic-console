"""Multimodal intake parsing and confirmation APIs."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.health_condition import HealthCondition
from app.schemas.intake import (
    IntakeConfirmRequest,
    IntakeConfirmResponse,
    IntakeDraftSessionResponse,
    PhotoParseRequest,
    VoiceParseRequest,
)
from app.services.intake import IntakeService


router = APIRouter(prefix="/intake", tags=["多模态录入"])
intake_service = IntakeService()


async def get_user_conditions(user_id: int, db: DbSession) -> list[HealthCondition]:
    result = await db.execute(select(HealthCondition).where(HealthCondition.user_id == user_id))
    return list(result.scalars().all())


@router.post("/voice/parse", response_model=IntakeDraftSessionResponse)
async def parse_voice_intake(
    data: VoiceParseRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)
    return await intake_service.parse_voice(
        db,
        user=current_user,
        conditions=conditions,
        data=data,
    )


@router.post("/photo/parse-result", response_model=IntakeDraftSessionResponse)
async def parse_photo_intake(
    data: PhotoParseRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)
    return await intake_service.parse_photo_result(
        db,
        user=current_user,
        conditions=conditions,
        data=data,
    )


@router.post("/confirm", response_model=IntakeConfirmResponse, status_code=status.HTTP_201_CREATED)
async def confirm_intake(
    data: IntakeConfirmRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)
    try:
        return await intake_service.confirm(
            db,
            user=current_user,
            conditions=conditions,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
