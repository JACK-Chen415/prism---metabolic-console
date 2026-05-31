"""Multimodal intake parsing and confirmation APIs."""

import base64
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.health_condition import HealthCondition
from app.schemas.intake import (
    IntakeCandidate,
    IntakeConfirmItem,
    IntakeConfirmRequest,
    IntakeConfirmResponse,
    IntakeDraftSessionResponse,
    PhotoParseRequest,
    TextParseRequest,
    VoiceAutoLogRequest,
    VoiceParseRequest,
)
from app.services.ai_service import doubao_service
from app.services.intake import IntakeService
from app.services.upload_security import sanitize_image_upload


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


@router.post("/text/parse", response_model=IntakeDraftSessionResponse)
async def parse_text_intake(
    data: TextParseRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)
    return await intake_service.parse_text(
        db,
        user=current_user,
        conditions=conditions,
        data=data,
    )


@router.post("/voice/auto-log", response_model=IntakeConfirmResponse, status_code=status.HTTP_201_CREATED)
async def auto_log_voice_intake(
    data: VoiceAutoLogRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)

    try:
        return await intake_service.voice_auto_log(
            db,
            user=current_user,
            conditions=conditions,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/candidate/reevaluate", response_model=IntakeCandidate)
async def reevaluate_intake_candidate(
    data: IntakeConfirmItem,
    current_user: CurrentUser,
    db: DbSession,
):
    conditions = await get_user_conditions(current_user.id, db)

    try:
        return await intake_service.reevaluate_confirm_item(
            db,
            user=current_user,
            conditions=conditions,
            item=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


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


@router.post("/photo/recognize-parse-upload", response_model=IntakeDraftSessionResponse)
async def recognize_and_parse_photo_upload(
    file: UploadFile = File(...),
    prompt: Optional[str] = Form(None),
    meal_time_hint: Optional[str] = Form(None),
    record_date: Optional[str] = Form(None),
    fast: bool = Form(True),
    current_user: CurrentUser = None,
    db: DbSession = None,
):
    """
    拍照识别 + 结构化候选项的一步式接口。

    优化点：
    1. 前端直接上传压缩后的图片文件，避免 base64 JSON 大包；
    2. 后端只请求一次多模态模型；
    3. 本地知识规则只在 parse 阶段执行一次。
    """
    content = await file.read()
    from app.core.config import settings

    max_size = settings.max_upload_size_mb * 1024 * 1024
    try:
        image = sanitize_image_upload(
            content,
            content_type=file.content_type or "",
            max_size_bytes=max_size,
            max_pixels=settings.max_upload_image_pixels,
        )
    except ValueError as exc:
        status_code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if "大小超过限制" in str(exc) or "像素超过限制" in str(exc)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail=str(exc),
        ) from exc

    conditions = await get_user_conditions(current_user.id, db)
    image_base64 = base64.b64encode(image.content).decode("utf-8")
    image_type = "jpeg" if image.format == "JPEG" else "png"

    foods, ai_response = await doubao_service.recognize_food(
        image_base64=image_base64,
        user=current_user,
        conditions=conditions,
        image_type=image_type,
        user_prompt=prompt,
        fast=fast,
    )

    if not foods:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ai_response or "未识别到可记录的食物，请换个角度重新拍摄",
        )

    parse_request = PhotoParseRequest(
        recognized_foods=foods,
        ai_response=ai_response,
        meal_time_hint=meal_time_hint,
        record_date=record_date,
    )
    return await intake_service.parse_photo_result(
        db,
        user=current_user,
        conditions=conditions,
        data=parse_request,
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
