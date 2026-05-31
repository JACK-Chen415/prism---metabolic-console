"""Metabolic report export endpoints."""

from __future__ import annotations

import csv
import io
from calendar import monthrange
from datetime import date, datetime, time, timezone, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.health_condition import HealthCondition
from app.models.meal import Meal
from app.models.message import AppMessage
from app.services.auth_security import audit_security_event
from app.services.entitlements import EntitlementKey, entitlement_service
from app.services.target_service import calculate_daily_targets


router = APIRouter(prefix="/reports", tags=["报告导出"])

MEDICAL_DISCLAIMER = (
    "Prism 报告仅基于用户自行记录的数据做营养估算和风险提示，"
    "不提供医疗诊断、治疗、处方或急救服务。"
)


class ReportNutrients(BaseModel):
    calories: float = 0
    sodium: float = 0
    purine: float = 0
    protein: float = 0
    carbs: float = 0
    fat: float = 0
    fiber: float = 0


class DailyTrendRow(ReportNutrients):
    date: date
    meal_count: int = 0


class ReportSummary(BaseModel):
    day_count: int
    logged_days: int
    meal_count: int
    totals: ReportNutrients
    averages_per_day: ReportNutrients
    targets: dict[str, float | int | None] = Field(default_factory=dict)
    risk_summary: list[str] = Field(default_factory=list)
    latest_insights: list[dict[str, str | bool | None]] = Field(default_factory=list)


class MetabolicReportResponse(BaseModel):
    report_type: Literal["weekly", "monthly"]
    start_date: date
    end_date: date
    generated_at: datetime
    medical_disclaimer: str
    summary: ReportSummary
    daily_trends: list[DailyTrendRow]
    csv_endpoint: str


async def _load_conditions(db: DbSession, user_id: int) -> list[HealthCondition]:
    result = await db.execute(select(HealthCondition).where(HealthCondition.user_id == user_id))
    return list(result.scalars().all())


async def _load_meals(db: DbSession, user_id: int, start_date: date, end_date: date) -> list[Meal]:
    result = await db.execute(
        select(Meal)
        .where(
            Meal.user_id == user_id,
            Meal.record_date >= start_date,
            Meal.record_date <= end_date,
        )
        .order_by(Meal.record_date.asc(), Meal.created_at.asc())
    )
    return list(result.scalars().all())


async def _load_recent_insights(
    db: DbSession,
    user_id: int,
    start_date: date,
    end_date: date,
) -> list[AppMessage]:
    start_at = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    result = await db.execute(
        select(AppMessage)
        .where(
            AppMessage.user_id == user_id,
            AppMessage.created_at >= start_at,
            AppMessage.created_at < end_at,
        )
        .order_by(AppMessage.created_at.desc())
        .limit(8)
    )
    return list(result.scalars().all())


def _weekly_period(end_date: Optional[date]) -> tuple[date, date]:
    end = end_date or date.today()
    return end - timedelta(days=6), end


def _monthly_period(target_month: Optional[str]) -> tuple[date, date]:
    if target_month:
        try:
            year, month = [int(part) for part in target_month.split("-", 1)]
            start = date(year, month, 1)
        except Exception as exc:
            raise ValueError("target_month 必须使用 YYYY-MM 格式") from exc
    else:
        today = date.today()
        start = date(today.year, today.month, 1)
    last_day = monthrange(start.year, start.month)[1]
    return start, date(start.year, start.month, last_day)


def _build_daily_trends(meals: list[Meal], start_date: date, end_date: date) -> list[DailyTrendRow]:
    rows: dict[date, DailyTrendRow] = {}
    current = start_date
    while current <= end_date:
        rows[current] = DailyTrendRow(date=current)
        current += timedelta(days=1)

    for meal in meals:
        row = rows.get(meal.record_date)
        if not row:
            continue
        row.meal_count += 1
        row.calories += float(meal.calories or 0)
        row.sodium += float(meal.sodium or 0)
        row.purine += float(meal.purine or 0)
        row.protein += float(meal.protein or 0)
        row.carbs += float(meal.carbs or 0)
        row.fat += float(meal.fat or 0)
        row.fiber += float(meal.fiber or 0)

    return [rows[key] for key in sorted(rows)]


def _sum_nutrients(rows: list[DailyTrendRow]) -> ReportNutrients:
    return ReportNutrients(
        calories=round(sum(row.calories for row in rows), 1),
        sodium=round(sum(row.sodium for row in rows), 1),
        purine=round(sum(row.purine for row in rows), 1),
        protein=round(sum(row.protein for row in rows), 1),
        carbs=round(sum(row.carbs for row in rows), 1),
        fat=round(sum(row.fat for row in rows), 1),
        fiber=round(sum(row.fiber for row in rows), 1),
    )


def _average_nutrients(totals: ReportNutrients, day_count: int) -> ReportNutrients:
    if day_count <= 0:
        return ReportNutrients()
    return ReportNutrients(
        calories=round(totals.calories / day_count, 1),
        sodium=round(totals.sodium / day_count, 1),
        purine=round(totals.purine / day_count, 1),
        protein=round(totals.protein / day_count, 1),
        carbs=round(totals.carbs / day_count, 1),
        fat=round(totals.fat / day_count, 1),
        fiber=round(totals.fiber / day_count, 1),
    )


def _build_risk_summary(averages: ReportNutrients, targets) -> list[str]:
    notes: list[str] = []
    calorie_target = getattr(targets, "recommended_calorie_target", None) or getattr(targets, "calories", None)
    sodium_limit = getattr(targets, "sodium", None)
    purine_limit = getattr(targets, "purine", None)

    if calorie_target and averages.calories > calorie_target * 1.1:
        notes.append("平均热量高于当前目标 10% 以上，建议下一阶段优先核对高能量食物和份量。")
    if sodium_limit and averages.sodium > sodium_limit:
        notes.append("平均钠摄入高于当前目标，建议优先关注咸味调料、加工食品和外食频率。")
    if purine_limit and averages.purine > purine_limit:
        notes.append("平均嘌呤摄入高于当前目标，建议保守处理海鲜、动物内脏、浓肉汤和酒精相关记录。")
    if averages.fiber and averages.fiber < 18:
        notes.append("平均膳食纤维偏低，可在可耐受前提下增加蔬菜、豆类或全谷物记录。")
    if not notes:
        notes.append("本周期未发现明显超过当前目标的汇总指标，请继续保持记录完整性。")
    return notes


def _insight_payload(messages: list[AppMessage]) -> list[dict[str, str | bool | None]]:
    return [
        {
            "type": getattr(message.message_type, "value", message.message_type),
            "title": message.title,
            "content": message.content,
            "attribution": message.attribution,
            "is_read": message.is_read,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }
        for message in messages[:5]
    ]


def _build_report(
    *,
    report_type: Literal["weekly", "monthly"],
    start_date: date,
    end_date: date,
    meals: list[Meal],
    targets,
    insights: list[AppMessage],
) -> MetabolicReportResponse:
    rows = _build_daily_trends(meals, start_date, end_date)
    day_count = len(rows)
    totals = _sum_nutrients(rows)
    averages = _average_nutrients(totals, day_count)
    targets_payload = {
        "calories": getattr(targets, "calories", None),
        "recommended_calorie_target": getattr(targets, "recommended_calorie_target", None),
        "sodium": getattr(targets, "sodium", None),
        "purine": getattr(targets, "purine", None),
    }

    csv_endpoint = (
        f"/api/reports/weekly.csv?end_date={end_date.isoformat()}"
        if report_type == "weekly"
        else f"/api/reports/monthly.csv?target_month={start_date.strftime('%Y-%m')}"
    )

    return MetabolicReportResponse(
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        generated_at=datetime.now(timezone.utc),
        medical_disclaimer=MEDICAL_DISCLAIMER,
        summary=ReportSummary(
            day_count=day_count,
            logged_days=sum(1 for row in rows if row.meal_count > 0),
            meal_count=sum(row.meal_count for row in rows),
            totals=totals,
            averages_per_day=averages,
            targets=targets_payload,
            risk_summary=_build_risk_summary(averages, targets),
            latest_insights=_insight_payload(insights),
        ),
        daily_trends=rows,
        csv_endpoint=csv_endpoint,
    )


def _report_csv(report: MetabolicReportResponse) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["disclaimer", report.medical_disclaimer])
    writer.writerow(["report_type", report.report_type])
    writer.writerow(["start_date", report.start_date.isoformat()])
    writer.writerow(["end_date", report.end_date.isoformat()])
    writer.writerow([])
    writer.writerow(["date", "meal_count", "calories", "sodium_mg", "purine_mg", "protein_g", "carbs_g", "fat_g", "fiber_g"])
    for row in report.daily_trends:
        writer.writerow([
            row.date.isoformat(),
            row.meal_count,
            row.calories,
            row.sodium,
            row.purine,
            row.protein,
            row.carbs,
            row.fat,
            row.fiber,
        ])
    return output.getvalue()


async def _make_report(
    db: DbSession,
    current_user: CurrentUser,
    *,
    report_type: Literal["weekly", "monthly"],
    start_date: date,
    end_date: date,
) -> MetabolicReportResponse:
    try:
        await entitlement_service.ensure(current_user, EntitlementKey.REPORT_EXPORT)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    conditions = await _load_conditions(db, current_user.id)
    meals = await _load_meals(db, current_user.id, start_date, end_date)
    insights = await _load_recent_insights(db, current_user.id, start_date, end_date)
    targets = calculate_daily_targets(current_user, conditions)
    return _build_report(
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        meals=meals,
        targets=targets,
        insights=insights,
    )


async def _audit_report_export(
    db: DbSession,
    request: Request,
    current_user: CurrentUser,
    *,
    report: MetabolicReportResponse,
    export_format: Literal["json", "csv"],
    route_name: str,
) -> None:
    await audit_security_event(
        db,
        event_type="report.export",
        event_status="success",
        user_id=current_user.id,
        request=request,
        route_name=route_name,
        metadata={
            "report_type": report.report_type,
            "format": export_format,
            "start_date": report.start_date.isoformat(),
            "end_date": report.end_date.isoformat(),
            "logged_days": report.summary.logged_days,
            "meal_count": report.summary.meal_count,
        },
    )


@router.get("/weekly", response_model=MetabolicReportResponse)
async def get_weekly_report(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    end_date: Optional[date] = Query(None, description="周报截止日期，默认今天"),
):
    start, end = _weekly_period(end_date)
    report = await _make_report(db, current_user, report_type="weekly", start_date=start, end_date=end)
    await _audit_report_export(
        db,
        request,
        current_user,
        report=report,
        export_format="json",
        route_name="/api/reports/weekly",
    )
    return report


@router.get("/monthly", response_model=MetabolicReportResponse)
async def get_monthly_report(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    target_month: Optional[str] = Query(None, description="月份，格式 YYYY-MM，默认本月"),
):
    try:
        start, end = _monthly_period(target_month)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    report = await _make_report(db, current_user, report_type="monthly", start_date=start, end_date=end)
    await _audit_report_export(
        db,
        request,
        current_user,
        report=report,
        export_format="json",
        route_name="/api/reports/monthly",
    )
    return report


@router.get("/weekly.csv")
async def get_weekly_report_csv(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    end_date: Optional[date] = Query(None, description="周报截止日期，默认今天"),
):
    start, end = _weekly_period(end_date)
    report = await _make_report(db, current_user, report_type="weekly", start_date=start, end_date=end)
    await _audit_report_export(
        db,
        request,
        current_user,
        report=report,
        export_format="csv",
        route_name="/api/reports/weekly.csv",
    )
    return Response(
        content="\ufeff" + _report_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="prism-weekly-report.csv"'},
    )


@router.get("/monthly.csv")
async def get_monthly_report_csv(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    target_month: Optional[str] = Query(None, description="月份，格式 YYYY-MM，默认本月"),
):
    try:
        start, end = _monthly_period(target_month)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    report = await _make_report(db, current_user, report_type="monthly", start_date=start, end_date=end)
    await _audit_report_export(
        db,
        request,
        current_user,
        report=report,
        export_format="csv",
        route_name="/api/reports/monthly.csv",
    )
    return Response(
        content="\ufeff" + _report_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="prism-monthly-report.csv"'},
    )
