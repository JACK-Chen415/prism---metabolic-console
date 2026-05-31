from datetime import date

from app.api.routes.meals import _apply_meal_update
from app.models.meal import FoodCategory, Meal, MealType, SyncStatus
from app.schemas.meal import MealCreate, MealSyncOperation, MealSyncRequest, MealSyncResponse, MealUpdate


def _meal_create(client_id: str = "client-1") -> MealCreate:
    return MealCreate(
        client_id=client_id,
        name="米饭",
        portion="1碗",
        calories=230,
        sodium=5,
        purine=20,
        meal_type=MealType.LUNCH,
        category=FoodCategory.STAPLE,
        record_date=date(2026, 5, 30),
    )


def test_meal_sync_request_keeps_legacy_meals_and_accepts_operations() -> None:
    request = MealSyncRequest(
        meals=[_meal_create()],
        operations=[
            MealSyncOperation(
                op_type="update",
                client_id="server-client-1",
                server_id=12,
                changes=MealUpdate(portion="半碗", sodium=3),
            ),
            MealSyncOperation(
                op_type="delete",
                client_id="server-client-2",
                server_id=13,
            ),
        ],
    )

    assert request.meals[0].client_id == "client-1"
    assert request.operations[0].op_type == "update"
    assert request.operations[0].changes.portion == "半碗"
    assert request.operations[1].op_type == "delete"


def test_meal_sync_request_defaults_operations_for_old_clients() -> None:
    request = MealSyncRequest(meals=[_meal_create("legacy-client")])

    assert request.operations == []


def test_sync_status_includes_failed_for_offline_retry() -> None:
    assert SyncStatus.FAILED.value == "FAILED"
    assert "FAILED" in SyncStatus.__members__


def test_meal_sync_response_carries_deleted_client_ids() -> None:
    response = MealSyncResponse(synced_count=1, conflicts=[], deleted_client_ids=["client-del"], server_meals=[])

    assert response.deleted_client_ids == ["client-del"]


def test_apply_meal_update_updates_only_provided_fields() -> None:
    meal = Meal(
        user_id=1,
        client_id="client-1",
        name="米饭",
        portion="1碗",
        calories=230,
        sodium=5,
        purine=20,
        meal_type=MealType.LUNCH,
        category=FoodCategory.STAPLE,
        record_date=date(2026, 5, 30),
        sync_status=SyncStatus.SYNCED,
    )

    _apply_meal_update(meal, MealUpdate(portion="半碗", sodium=3).model_dump(exclude_unset=True))

    assert meal.name == "米饭"
    assert meal.portion == "半碗"
    assert meal.sodium == 3
