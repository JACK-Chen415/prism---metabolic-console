from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.routes import insights as insights_route
from app.models.health_condition import ConditionStatus, ConditionType, HealthCondition, TrendType
from app.models.knowledge import RecommendationLevel
from app.models.meal import FoodCategory, Meal, MealType
from app.models.message import AppMessage, MessageType
from app.models.user import Gender, User
from app.services.insights import SMART_INSIGHT_ATTRIBUTION_PREFIX, SmartInsightMessageService


TARGET_DATE = date(2026, 5, 24)


class FakeScalarResult:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class FakeExecuteResult:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        return FakeScalarResult(self.items)


class FakeDb:
    def __init__(self, *, user, conditions, meals, messages=None):
        self.user = user
        self.conditions = conditions
        self.meals = meals
        self.messages = list(messages or [])
        self.next_message_id = 100
        self.deleted = []

    async def execute(self, statement):
        statement_text = str(statement)
        if "FROM health_conditions" in statement_text:
            return FakeExecuteResult([item for item in self.conditions if item.user_id == self.user.id])
        if "FROM meals" in statement_text:
            return FakeExecuteResult(
                [
                    item
                    for item in self.meals
                    if item.user_id == self.user.id and item.record_date == TARGET_DATE
                ]
            )
        if "FROM app_messages" in statement_text:
            prefix = f"{SMART_INSIGHT_ATTRIBUTION_PREFIX}|date={TARGET_DATE.isoformat()}|"
            return FakeExecuteResult(
                [
                    item
                    for item in self.messages
                    if item.user_id == self.user.id and (item.attribution or "").startswith(prefix)
                ]
            )
        return FakeExecuteResult([])

    def add(self, item):
        if isinstance(item, AppMessage):
            item.id = self.next_message_id
            self.next_message_id += 1
            item.created_at = datetime(2026, 5, 24, 15, 0, tzinfo=timezone.utc)
            item.is_read = False
            self.messages.append(item)

    async def delete(self, item):
        self.deleted.append(item)
        self.messages.remove(item)

    async def flush(self):
        return None

    async def refresh(self, _item):
        return None


class FakeKnowledgeService:
    async def evaluate_food_for_user(
        self,
        db,
        *,
        user,
        conditions,
        food_name=None,
        food_code=None,
        explicit_condition_codes=None,
        manual_restrictions=None,
    ):
        return SimpleNamespace(
            food_name=food_name,
            recommendation_level=RecommendationLevel.AVOID,
            hard_blocks=["allergy: peanut"],
            summary="avoid peanut",
            conflict_note="peanut allergy conflict",
            caution_note=None,
            matched_disease_codes=["peanut"],
        )


def _user() -> User:
    return User(
        id=1,
        phone="13800138000",
        password_hash="x",
        gender=Gender.MALE,
        age=35,
        height=175,
        weight=70,
    )


def _condition() -> HealthCondition:
    return HealthCondition(
        id=10,
        user_id=1,
        condition_code="peanut",
        title="Peanut",
        icon="allergy",
        condition_type=ConditionType.ALLERGY,
        status=ConditionStatus.ACTIVE,
        trend=TrendType.STABLE,
    )


def _meal() -> Meal:
    return Meal(
        id=20,
        user_id=1,
        client_id="meal-20",
        name="peanut sauce",
        portion="1 bowl",
        calories=600,
        sodium=300,
        purine=50,
        meal_type=MealType.LUNCH,
        category=FoodCategory.STAPLE,
        record_date=TARGET_DATE,
    )


@pytest.mark.asyncio
async def test_refresh_today_persists_smart_messages_and_replaces_only_same_day_generated_rows():
    user = _user()
    old_generated = AppMessage(
        id=1,
        user_id=user.id,
        message_type=MessageType.BRIEF,
        title="old generated",
        content="old",
        attribution=f"{SMART_INSIGHT_ATTRIBUTION_PREFIX}|date={TARGET_DATE.isoformat()}|key=old",
    )
    old_generated.created_at = datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc)
    unrelated = AppMessage(
        id=2,
        user_id=user.id,
        message_type=MessageType.ADVICE,
        title="manual",
        content="keep me",
        attribution="manual",
    )
    unrelated.created_at = datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc)
    db = FakeDb(user=user, conditions=[_condition()], meals=[_meal()], messages=[old_generated, unrelated])
    service = SmartInsightMessageService(knowledge_service=FakeKnowledgeService())

    result = await service.refresh_today(
        db,
        user=user,
        target_date=TARGET_DATE,
        now=datetime(2026, 5, 24, 15, 0, tzinfo=timezone.utc),
    )

    assert result.generated_count == 1
    assert result.messages[0].message_type == MessageType.WARNING
    assert result.messages[0].attribution.startswith(
        f"{SMART_INSIGHT_ATTRIBUTION_PREFIX}|date={TARGET_DATE.isoformat()}|"
    )
    assert "category=CONDITION_CAUTION" in result.messages[0].attribution
    assert unrelated in db.messages
    assert old_generated not in db.messages

    second = await service.refresh_today(
        db,
        user=user,
        target_date=TARGET_DATE,
        now=datetime(2026, 5, 24, 15, 0, tzinfo=timezone.utc),
    )

    smart_messages = [
        item
        for item in db.messages
        if (item.attribution or "").startswith(f"{SMART_INSIGHT_ATTRIBUTION_PREFIX}|date={TARGET_DATE.isoformat()}|")
    ]
    assert second.generated_count == 1
    assert len(smart_messages) == 1
    assert unrelated in db.messages


class FakeRouteService:
    def __init__(self):
        self.message = AppMessage(
            id=50,
            user_id=1,
            message_type=MessageType.ADVICE,
            title="这顿午餐可以再补足一些",
            content="这顿午餐低于预期热量区间，可补充一份优质蛋白或适量主食。",
            attribution=f"{SMART_INSIGHT_ATTRIBUTION_PREFIX}|date={TARGET_DATE.isoformat()}|key=test",
        )
        self.message.created_at = datetime(2026, 5, 24, 15, 0, tzinfo=timezone.utc)
        self.message.is_read = False

    async def refresh_today(self, db, *, user):
        return SimpleNamespace(target_date=TARGET_DATE, generated_count=1, messages=[self.message])

    async def list_today(self, db, *, user):
        return [self.message]


@pytest.mark.asyncio
async def test_insight_routes_return_persisted_message_payloads(monkeypatch):
    monkeypatch.setattr(insights_route, "insight_message_service", FakeRouteService())
    user = _user()

    refresh = await insights_route.refresh_insights(user, object())
    today = await insights_route.get_today_insights(user, object())

    assert refresh.generated_count == 1
    assert refresh.target_date == TARGET_DATE.isoformat()
    assert refresh.messages[0].id == 50
    assert refresh.messages[0].message_type == MessageType.ADVICE
    assert today[0].id == 50
