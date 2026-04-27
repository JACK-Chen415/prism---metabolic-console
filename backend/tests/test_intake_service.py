from app.models.meal import FoodCategory, MealType
from app.services.intake import IntakeService


def test_split_voice_segments_handles_meal_sentence() -> None:
    service = IntakeService()

    segments = service._split_voice_segments("今天早上吃了一个鸡蛋和一杯无糖豆浆、半根玉米")

    assert segments == ["一个鸡蛋", "一杯无糖豆浆", "半根玉米"]


def test_extract_amount_and_food_name() -> None:
    service = IntakeService()

    amount_text, normalized_amount, unit, food_name = service._extract_amount("半碗米饭")

    assert amount_text == "半碗"
    assert normalized_amount == 0.5
    assert unit == "碗"
    assert food_name == "米饭"


def test_infer_meal_type_and_category() -> None:
    service = IntakeService()

    meal_type = service._infer_meal_type("中午半碗米饭和一份西兰花", None)
    category = service._resolve_category("无糖豆浆", None)

    assert meal_type == MealType.LUNCH
    assert category == FoodCategory.DRINK
