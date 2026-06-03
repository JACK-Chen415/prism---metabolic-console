from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status

from app.api.routes import reports as reports_route
from app.api.routes.reports import (
    MEDICAL_DISCLAIMER,
    _build_report,
    _monthly_period,
    _report_csv,
    _weekly_period,
)
from app.models.meal import FoodCategory, Meal, MealType
from app.models.user import SubscriptionPlan, SubscriptionStatus, User


class _EmptyScalars:
    def all(self):
        return []


class _EmptyResult:
    def scalars(self):
        return _EmptyScalars()


class _EmptyReportDb:
    async def execute(self, _statement):
        return _EmptyResult()


def _meal(day: date, *, sodium: float = 0, purine: float = 0, fiber: float = 0) -> Meal:
    return Meal(
        id=1,
        user_id=1,
        client_id=f"meal-{day.isoformat()}",
        name="test meal",
        portion="1份",
        calories=500,
        sodium=sodium,
        purine=purine,
        protein=20,
        carbs=50,
        fat=12,
        fiber=fiber,
        meal_type=MealType.LUNCH,
        category=FoodCategory.STAPLE,
        record_date=day,
    )


def test_weekly_period_is_last_seven_days_ending_target_date() -> None:
    start, end = _weekly_period(date(2026, 5, 30))

    assert start == date(2026, 5, 24)
    assert end == date(2026, 5, 30)


def test_monthly_period_uses_calendar_month() -> None:
    start, end = _monthly_period("2026-02")

    assert start == date(2026, 2, 1)
    assert end == date(2026, 2, 28)


def test_report_contains_disclaimer_daily_trends_and_conservative_risk_summary() -> None:
    report = _build_report(
        report_type="weekly",
        start_date=date(2026, 5, 24),
        end_date=date(2026, 5, 30),
        meals=[
            _meal(date(2026, 5, 24), sodium=3000, purine=700, fiber=5),
            _meal(date(2026, 5, 25), sodium=2600, purine=650, fiber=4),
        ],
        targets=SimpleNamespace(calories=100, recommended_calorie_target=100, sodium=100, purine=100),
        insights=[],
    )

    assert report.medical_disclaimer == MEDICAL_DISCLAIMER
    assert report.summary.day_count == 7
    assert report.summary.logged_days == 2
    assert report.summary.meal_count == 2
    assert len(report.daily_trends) == 7
    assert any("钠" in note for note in report.summary.risk_summary)
    assert any("嘌呤" in note for note in report.summary.risk_summary)

    csv_text = _report_csv(report)
    assert "disclaimer" in csv_text
    assert "2026-05-24" in csv_text
    assert "sodium_mg" in csv_text


@pytest.mark.asyncio
async def test_make_report_converts_entitlement_denial_to_403(monkeypatch):
    async def deny(_user, _feature):
        raise PermissionError("当前订阅不包含 REPORT_EXPORT 权益")

    monkeypatch.setattr(reports_route.entitlement_service, "ensure", deny)

    with pytest.raises(HTTPException) as exc_info:
        await reports_route._make_report(
            SimpleNamespace(),
            SimpleNamespace(id=1),
            report_type="weekly",
            start_date=date(2026, 5, 24),
            end_date=date(2026, 5, 30),
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "REPORT_EXPORT" in exc_info.value.detail


@pytest.mark.asyncio
async def test_free_user_report_export_is_blocked_by_server_entitlement_gate():
    user = User(
        id=1,
        phone="13800138000",
        password_hash="x",
        subscription_plan=SubscriptionPlan.FREE,
        subscription_status=SubscriptionStatus.INACTIVE,
    )

    with pytest.raises(HTTPException) as exc_info:
        await reports_route._make_report(
            _EmptyReportDb(),
            user,
            report_type="weekly",
            start_date=date(2026, 5, 24),
            end_date=date(2026, 5, 30),
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "REPORT_EXPORT" in exc_info.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("plan", [SubscriptionPlan.PRO, SubscriptionPlan.COACH])
async def test_paid_user_report_export_continues_when_report_export_entitlement_exists(plan):
    user = User(
        id=1,
        phone="13800138000",
        password_hash="x",
        subscription_plan=plan,
        subscription_status=SubscriptionStatus.ACTIVE,
    )

    report = await reports_route._make_report(
        _EmptyReportDb(),
        user,
        report_type="weekly",
        start_date=date(2026, 5, 24),
        end_date=date(2026, 5, 30),
    )

    assert report.report_type == "weekly"
    assert report.summary.meal_count == 0
