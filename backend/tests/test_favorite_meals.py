import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.routes import meals as route
from app.models.meal import FavoriteMeal, FoodCategory, Meal, MealType
from app.schemas.meal import FavoriteMealResponse


def _favorite_meal(**overrides) -> FavoriteMeal:
    now = datetime(2026, 6, 7, 8, 30, tzinfo=timezone.utc)
    data = {
        "id": 7,
        "user_id": 1,
        "source_meal_id": 42,
        "name": "low-sodium chicken box",
        "portion": "1 box",
        "meal_type": MealType.LUNCH,
        "category": FoodCategory.MEAT,
        "note": "raw health note and meal text",
        "calories": 520,
        "sodium": 380,
        "purine": 120,
        "protein": 35,
        "carbs": 48,
        "fat": 16,
        "fiber": 6,
        "usage_count": 3,
        "last_used_at": datetime(2026, 6, 7, 9, 0, tzinfo=timezone.utc),
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return FavoriteMeal(**data)


def test_favorite_meal_model_and_schema_include_reuse_fields() -> None:
    assert {"usage_count", "last_used_at", "source_meal_id"}.issubset(FavoriteMeal.__table__.c.keys())

    favorite = _favorite_meal()
    response = FavoriteMealResponse.model_validate(favorite)
    payload = response.model_dump(mode="json")

    assert payload["source_meal_id"] == 42
    assert payload["usage_count"] == 3
    assert payload["last_used_at"] == "2026-06-07T09:00:00Z"
    assert payload["meal_type"] == "LUNCH"
    assert payload["category"] == "MEAT"


def test_favorite_audit_metadata_excludes_raw_food_and_health_text() -> None:
    favorite = _favorite_meal(
        name="raw meal name must stay private",
        note="uric acid flare and chest tightness must stay private",
    )

    metadata = route._favorite_audit_metadata(favorite)
    serialized = json.dumps(metadata, ensure_ascii=False)

    assert metadata == {
        "favorite_id": 7,
        "source_meal_id": 42,
        "meal_type": "LUNCH",
        "category": "MEAT",
        "usage_count": 3,
    }
    assert "raw meal name" not in serialized
    assert "uric acid" not in serialized
    assert "chest tightness" not in serialized
    assert "low-sodium chicken" not in serialized
    assert "note" not in metadata
    assert "name" not in metadata


class _FakeScalarResult:
    def __init__(self, item):
        self._item = item

    def scalar_one_or_none(self):
        return self._item


class _FakeFavoriteDb:
    def __init__(self, favorite: FavoriteMeal):
        self.favorite = favorite
        self.added = []
        self.flush_count = 0
        self.refresh_count = 0

    async def execute(self, statement):
        self.statement = statement
        return _FakeScalarResult(self.favorite)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flush_count += 1

    async def refresh(self, item):
        self.refresh_count += 1


@pytest.mark.asyncio
async def test_use_favorite_meal_updates_reuse_metadata_without_creating_meal(monkeypatch) -> None:
    favorite = _favorite_meal(usage_count=4, last_used_at=None)
    db = _FakeFavoriteDb(favorite)
    audit_calls = []

    async def fake_audit_security_event(*args, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(route, "audit_security_event", fake_audit_security_event)

    response = await route.use_favorite_meal(
        favorite_id=7,
        request=None,
        current_user=SimpleNamespace(id=1),
        db=db,
    )

    assert favorite.usage_count == 5
    assert favorite.last_used_at is not None
    assert favorite.last_used_at.tzinfo == timezone.utc
    assert response.usage_count == 5
    assert response.last_used_at == favorite.last_used_at
    assert db.flush_count == 1
    assert db.refresh_count == 1
    assert db.added == []
    assert not any(isinstance(item, Meal) for item in db.added)
    assert audit_calls[0]["event_type"] == "meal.favorite.use"
    assert audit_calls[0]["metadata"]["usage_count"] == 5
