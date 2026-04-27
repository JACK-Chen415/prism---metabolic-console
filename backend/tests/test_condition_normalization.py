from app.models.health_condition import ConditionStatus, ConditionType, HealthCondition, TrendType
from app.models.user import Gender, User
from app.services.knowledge.normalizer import match_default_disease_code
from app.services.target_service import calculate_daily_targets


def test_match_default_disease_code_handles_free_text_title():
    assert match_default_disease_code("cond_171717", "高血压") == "hypertension"
    assert match_default_disease_code("cond_171718", "血脂高") == "hyperlipidemia"
    assert match_default_disease_code("cond_171719", "痛风") == "gout"
    assert match_default_disease_code("cond_171720", "2型糖尿病") == "type2_diabetes"


def test_daily_targets_use_normalized_condition_title():
    user = User(
        phone="13800138000",
        password_hash="hashed",
        gender=Gender.MALE,
        age=32,
        height=175,
        weight=75,
    )
    condition = HealthCondition(
        user_id=1,
        condition_code="cond_171717",
        title="高血压",
        icon="monitor_heart",
        condition_type=ConditionType.CHRONIC,
        status=ConditionStatus.ACTIVE,
        trend=TrendType.STABLE,
    )

    targets = calculate_daily_targets(user, [condition])
    assert targets.sodium == 1500
