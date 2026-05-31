from datetime import date, datetime, timedelta, timezone

from sqlalchemy.dialects import sqlite

from app.api.routes import admin as admin_route
from app.core.security import hash_sensitive_value
from app.models.chat import ChatMessage, ChatSession, MessageRole
from app.models.feedback import AIFeedback, AIFeedbackStatus, AIFeedbackType
from app.models.health_metric import HealthMetric, HealthMetricType
from app.models.knowledge import FallbackStatus, FoodItem, KnowledgeAuditLog, KnowledgeOrigin
from app.models.meal import FoodCategory, Meal, MealSource, MealType, SyncStatus
from app.models.security import SecurityAuditLog
from app.models.user import SubscriptionPlan, SubscriptionStatus, User, UserRole


def test_admin_user_requires_phone_hash_allowlist(monkeypatch):
    user = User(id=1, phone="13800138000", password_hash="x")

    monkeypatch.setattr(admin_route.settings, "admin_phone_hashes", [])
    assert admin_route._is_admin_user(user) is False

    monkeypatch.setattr(admin_route.settings, "admin_phone_hashes", [hash_sensitive_value(user.phone)])
    assert admin_route._is_admin_user(user) is True


def test_admin_user_accepts_persisted_admin_role(monkeypatch):
    user = User(id=1, phone="13800138000", password_hash="x", role=UserRole.ADMIN)

    monkeypatch.setattr(admin_route.settings, "admin_phone_hashes", [])

    assert admin_route._is_admin_user(user) is True


def test_knowledge_admin_item_hashes_query_excerpt():
    row = KnowledgeAuditLog(
        id=1,
        user_id=2,
        route_name="/api/chat",
        chat_session_id=3,
        chat_message_id=4,
        query_excerpt="痛风能不能喝啤酒",
        origin=KnowledgeOrigin.MIXED,
        fallback_status=FallbackStatus.LOCAL_PARTIAL_ALLOW_CLOUD,
        matched_disease_codes_json=["gout"],
        matched_food_codes_json=["beer"],
        unmapped_conditions_json=[],
        called_cloud=True,
        cloud_call_reason="cloud supplement",
    )
    row.created_at = datetime(2026, 5, 30, tzinfo=timezone.utc)

    item = admin_route._knowledge_item(row)

    assert item.query_excerpt_hash == hash_sensitive_value("痛风能不能喝啤酒")
    assert item.query_excerpt_hash != "痛风能不能喝啤酒"

    stored_hash = hash_sensitive_value("痛风能不能喝啤酒")
    row.query_excerpt = stored_hash
    assert admin_route._knowledge_item(row).query_excerpt_hash == stored_hash
    assert item.origin == "MIXED"
    assert item.fallback_status == "LOCAL_PARTIAL_ALLOW_CLOUD"


def test_feedback_admin_item_never_exposes_raw_correction_text():
    raw_correction = "识别错误：这不是虾。"
    row = AIFeedback(
        id=9,
        user_id=2,
        session_id=3,
        message_id=4,
        feedback_type=AIFeedbackType.RECOGNITION_CORRECTION,
        rating=2,
        tags_json=["recognition"],
        correction_text=raw_correction,
        correction_text_hash=hash_sensitive_value(raw_correction),
        metadata_json={"surface": "photo", "raw_note": raw_correction},
        status=AIFeedbackStatus.OPEN,
    )
    row.created_at = datetime(2026, 5, 30, tzinfo=timezone.utc)

    item = admin_route._feedback_item(row)
    serialized = item.model_dump_json()

    assert item.has_correction is True
    assert item.correction_text_hash == hash_sensitive_value(raw_correction)
    assert raw_correction not in serialized
    assert item.metadata_json is None
    assert item.metadata_keys == ["raw_note", "surface"]
    assert item.feedback_type == "recognition_correction"
    assert item.status == "open"


def test_security_audit_query_supports_safe_keyword_and_status_filters():
    statement = admin_route._build_security_audit_query(
        limit=20,
        q="otp",
        event_status="limited",
    )
    compiled = str(
        statement.compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "security_audit_logs.event_status = 'limited'" in compiled
    assert "%otp%" in compiled
    assert "security_audit_logs.event_type" in compiled
    assert "security_audit_logs.route_name" in compiled
    assert "security_audit_logs.event_status" in compiled
    assert "LIMIT 20" in compiled


def test_knowledge_audit_query_supports_structured_filters_without_raw_excerpt_search():
    statement = admin_route._build_knowledge_audit_query(
        limit=30,
        q="blocked",
        origin=admin_route.KnowledgeOrigin.LOCAL_RULE,
        fallback_status=admin_route.FallbackStatus.LOCAL_BLOCKED_NO_CLOUD,
        called_cloud=False,
    )
    compiled = str(
        statement.compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "knowledge_audit_logs.origin = 'LOCAL_RULE'" in compiled
    assert "knowledge_audit_logs.fallback_status = 'LOCAL_BLOCKED_NO_CLOUD'" in compiled
    assert "knowledge_audit_logs.called_cloud IS 0" in compiled
    assert "%blocked%" in compiled
    assert "knowledge_audit_logs.route_name" in compiled
    assert "knowledge_audit_logs.cloud_call_reason" in compiled
    assert "knowledge_audit_logs.cloud_blocked_reason" in compiled
    assert "query_excerpt ILIKE" not in compiled
    assert "LIMIT 30" in compiled


def test_knowledge_admin_item_hashes_unmapped_condition_labels():
    raw_condition_label = "用户手填的罕见慢病原文"
    row = KnowledgeAuditLog(
        id=2,
        user_id=2,
        route_name="/api/chat",
        query_excerpt="already-hashed",
        origin=KnowledgeOrigin.LOCAL_KNOWLEDGE,
        fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
        matched_disease_codes_json=["gout"],
        matched_food_codes_json=["beer"],
        unmapped_conditions_json=[raw_condition_label, "stable_condition_code"],
        called_cloud=True,
    )
    row.created_at = datetime(2026, 5, 30, tzinfo=timezone.utc)

    item = admin_route._knowledge_item(row)
    serialized = item.model_dump_json()

    assert raw_condition_label not in serialized
    assert f"hash:{hash_sensitive_value(raw_condition_label)[:16]}" in item.unmapped_conditions
    assert "stable_condition_code" in item.unmapped_conditions


def test_knowledge_backlog_summary_aggregates_without_sensitive_content():
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    raw_correction = "这条建议放宽了花生过敏限制"
    raw_query = "痛风用户能不能喝啤酒"
    raw_unmapped_condition = "用户手填的特殊健康档案"
    raw_tag = "我对虾严重过敏"
    raw_cloud_reason = "本地知识未命中，调用云端兜底。"
    raw_blocked_reason = "本地命中过敏、AVOID 或 LIMIT 约束，云端不得放宽。"

    feedback_rows = [
        AIFeedback(
            id=1,
            user_id=2,
            feedback_type=AIFeedbackType.KNOWLEDGE_GAP,
            status=AIFeedbackStatus.OPEN,
            tags_json=["coverage", raw_tag],
            correction_text=raw_correction,
            correction_text_hash=hash_sensitive_value(raw_correction),
            metadata_json={"surface": "chat", "raw_note": raw_correction},
        ),
        AIFeedback(
            id=2,
            user_id=2,
            feedback_type=AIFeedbackType.RECOGNITION_CORRECTION,
            status=AIFeedbackStatus.REVIEWED,
            tags_json=["recognition"],
            correction_text="识别错了",
            correction_text_hash=hash_sensitive_value("识别错了"),
            metadata_json={"candidate_count": 2},
        ),
    ]
    feedback_rows[0].created_at = now
    feedback_rows[1].created_at = now - timedelta(minutes=1)

    food_rows = [
        FoodItem(
            food_code="white_rice",
            name_zh="白米饭",
            aliases_json=["米饭"],
            category="STAPLE",
            common_units_json=["100g"],
            calories_per_100g=116,
            protein_per_100g=2.6,
            carbs_per_100g=25.9,
            fat_per_100g=0.3,
            fiber_per_100g=0.3,
            sodium_per_100g=2,
            purine_per_100g=7,
            nutrition_source_code="core_v1_food_composition_reference",
            nutrition_source_detail="Core v1 nutrition from public food composition references; values normalized to 100g.",
            nutrition_estimate_quality="STANDARD_REFERENCE",
            nutrition_review_status="REVIEWED",
            allergen_tags_json=[],
            risk_tags_json=["high_glycemic_load"],
            is_enabled=True,
        ),
        FoodItem(
            food_code="grilled_cold_noodles",
            name_zh="烤冷面",
            aliases_json=["铁板烤冷面"],
            category="STAPLE",
            common_units_json=["220g"],
            calories_per_100g=210,
            protein_per_100g=7,
            carbs_per_100g=28,
            fat_per_100g=8,
            fiber_per_100g=1.2,
            sodium_per_100g=720,
            purine_per_100g=30,
            nutrition_source_code="core_v1_recipe_estimate",
            nutrition_source_detail="Core v1 recipe estimate from common Chinese portions, ingredients, and cooking normalization.",
            nutrition_estimate_quality="RECIPE_ESTIMATE",
            nutrition_review_status="REVIEWED",
            allergen_tags_json=["wheat", "egg", "soy"],
            risk_tags_json=["egg", "soy", "starchy_staple", "high_glycemic_load", "high_sodium", "high_fat"],
            is_enabled=True,
        ),
    ]

    knowledge_rows = [
        KnowledgeAuditLog(
            id=10,
            user_id=2,
            route_name="/api/chat",
            query_excerpt=raw_query,
            origin=KnowledgeOrigin.CLOUD_SUPPLEMENT,
            fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
            matched_disease_codes_json=["gout"],
            matched_food_codes_json=["beer"],
            unmapped_conditions_json=[raw_unmapped_condition],
            called_cloud=True,
            cloud_call_reason=raw_cloud_reason,
        ),
        KnowledgeAuditLog(
            id=11,
            user_id=3,
            route_name="/api/intake/confirm",
            query_excerpt=hash_sensitive_value("already hashed query"),
            origin=KnowledgeOrigin.LOCAL_RULE,
            fallback_status=FallbackStatus.LOCAL_BLOCKED_NO_CLOUD,
            matched_disease_codes_json=["allergy"],
            matched_food_codes_json=["peanut"],
            unmapped_conditions_json=[],
            called_cloud=False,
            cloud_blocked_reason=raw_blocked_reason,
        ),
        KnowledgeAuditLog(
            id=12,
            user_id=3,
            route_name="/api/knowledge/evaluate-food",
            origin=KnowledgeOrigin.LOCAL_RULE,
            fallback_status=FallbackStatus.LOCAL_COMPLETE,
            matched_disease_codes_json=["hypertension"],
            matched_food_codes_json=["rice"],
            unmapped_conditions_json=[],
            called_cloud=False,
        ),
    ]
    for index, row in enumerate(knowledge_rows):
        row.created_at = now - timedelta(minutes=10 + index)

    summary = admin_route._build_knowledge_backlog_summary(
        feedback_rows=feedback_rows,
        knowledge_rows=knowledge_rows,
        food_rows=food_rows,
        limit=10,
        generated_at=now,
    )
    serialized = summary.model_dump_json()

    assert summary.feedback_followup_count == 2
    assert summary.feedback_open_count == 1
    assert summary.knowledge_audit_gap_count == 2
    assert summary.has_correction_count == 2
    assert summary.feedback_type_counts == {"knowledge_gap": 1, "recognition_correction": 1}
    assert summary.feedback_status_counts == {"open": 1, "reviewed": 1}
    assert summary.tag_counts["coverage"] == 1
    assert summary.correction_hash_counts[hash_sensitive_value(raw_correction)] == 1
    assert summary.fallback_status_counts["NO_LOCAL_MATCH_ALLOW_CLOUD"] == 1
    assert summary.fallback_status_counts["LOCAL_BLOCKED_NO_CLOUD"] == 1
    assert summary.cloud_call_reason_counts["no_local_match_cloud_fallback"] == 1
    assert summary.cloud_blocked_reason_counts["local_rule_safety_block"] == 1
    assert summary.matched_disease_counts["gout"] == 1
    assert summary.matched_food_counts["beer"] == 1
    assert summary.food_nutrition_source_counts["core_v1_food_composition_reference"] == 1
    assert summary.food_nutrition_source_counts["core_v1_recipe_estimate"] == 1
    assert summary.food_nutrition_quality_counts["STANDARD_REFERENCE"] == 1
    assert summary.food_nutrition_quality_counts["RECIPE_ESTIMATE"] == 1
    assert summary.food_nutrition_review_status_counts["REVIEWED"] == 2
    assert summary.food_nutrition_unreviewed_count == 0
    assert summary.unmapped_condition_counts[f"hash:{hash_sensitive_value(raw_unmapped_condition)[:16]}"] == 1
    assert len(summary.recent_items) == 4

    assert raw_correction not in serialized
    assert raw_query not in serialized
    assert raw_unmapped_condition not in serialized
    assert raw_tag not in serialized
    assert raw_cloud_reason not in serialized
    assert raw_blocked_reason not in serialized
    assert '"correction_text":' not in serialized
    assert "surface" in serialized
    assert hash_sensitive_value(raw_correction) in serialized


def test_feedback_query_supports_status_and_type_filters():
    statement = admin_route._build_feedback_query(
        limit=40,
        status=AIFeedbackStatus.OPEN,
        feedback_type=AIFeedbackType.KNOWLEDGE_GAP,
    )
    compiled = str(
        statement.compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "ai_feedback.status = 'open'" in compiled
    assert "ai_feedback.feedback_type = 'knowledge_gap'" in compiled
    assert "LIMIT 40" in compiled


def test_apply_feedback_status_sets_and_clears_review_time():
    row = AIFeedback(
        id=10,
        user_id=2,
        feedback_type=AIFeedbackType.UNSAFE,
        status=AIFeedbackStatus.OPEN,
    )

    admin_route._apply_feedback_status(row, AIFeedbackStatus.REVIEWED)

    assert row.status == AIFeedbackStatus.REVIEWED
    assert row.reviewed_at is not None

    admin_route._apply_feedback_status(row, AIFeedbackStatus.OPEN)

    assert row.status == AIFeedbackStatus.OPEN
    assert row.reviewed_at is None


def test_unsafe_feedback_must_be_reviewed_before_close():
    row = AIFeedback(
        id=11,
        user_id=2,
        feedback_type=AIFeedbackType.UNSAFE,
        status=AIFeedbackStatus.OPEN,
    )

    assert (
        admin_route._feedback_status_transition_rejection(row, AIFeedbackStatus.CLOSED)
        == "unsafe_requires_review_before_close"
    )
    assert admin_route._feedback_status_transition_rejection(row, AIFeedbackStatus.REVIEWED) is None

    admin_route._apply_feedback_status(row, AIFeedbackStatus.REVIEWED)

    assert admin_route._feedback_status_transition_rejection(row, AIFeedbackStatus.CLOSED) is None


def test_non_unsafe_feedback_can_be_closed_without_extra_review_step():
    row = AIFeedback(
        id=12,
        user_id=2,
        feedback_type=AIFeedbackType.KNOWLEDGE_GAP,
        status=AIFeedbackStatus.OPEN,
    )

    assert admin_route._feedback_status_transition_rejection(row, AIFeedbackStatus.CLOSED) is None


def test_admin_user_item_hashes_phone_and_keeps_role_subscription_fields():
    raw_phone = "13800138000"
    row = User(
        id=22,
        phone=raw_phone,
        password_hash="x",
        nickname="内测用户",
        role=UserRole.COACH,
        subscription_plan=SubscriptionPlan.COACH,
        subscription_status=SubscriptionStatus.ACTIVE,
        is_active=True,
        is_verified=True,
    )
    row.created_at = datetime(2026, 5, 30, tzinfo=timezone.utc)
    row.updated_at = datetime(2026, 5, 30, tzinfo=timezone.utc)

    item = admin_route._admin_user_item(row)
    serialized = item.model_dump_json()

    assert item.phone_hash == hash_sensitive_value(raw_phone)
    assert raw_phone not in serialized
    assert item.role == UserRole.COACH
    assert item.subscription_plan == SubscriptionPlan.COACH
    assert item.subscription_status == SubscriptionStatus.ACTIVE


def test_admin_user_query_supports_structured_filters_and_safe_search():
    statement = admin_route._build_user_query(
        limit=25,
        q="内测",
        role=UserRole.COACH,
        subscription_plan=SubscriptionPlan.PRO,
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    compiled = str(
        statement.compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "users.role = 'COACH'" in compiled
    assert "users.subscription_plan = 'PRO'" in compiled
    assert "users.subscription_status = 'active'" in compiled
    assert "%内测%" in compiled
    assert "users.nickname" in compiled
    assert "CAST(users.id AS VARCHAR)" in compiled or "CAST(users.id AS TEXT)" in compiled
    assert "LIMIT 25" in compiled


def test_admin_user_search_metadata_hashes_free_text():
    raw_query = "内测用户A"
    metadata = admin_route._safe_admin_search_metadata(raw_query)
    serialized = str(metadata)

    assert metadata["q_present"] is True
    assert metadata["q_hash"] == hash_sensitive_value(raw_query)
    assert metadata["q_length"] == len(raw_query)
    assert raw_query not in serialized

    empty_metadata = admin_route._safe_admin_search_metadata("  ")
    assert empty_metadata == {"q_present": False, "q_hash": None, "q_length": 0}


def test_admin_role_and_subscription_mutators_set_auditable_state():
    row = User(id=23, phone="13800138001", password_hash="x")

    admin_route._apply_user_role(row, UserRole.ADMIN)
    admin_route._apply_user_subscription(row, SubscriptionPlan.PRO, SubscriptionStatus.ACTIVE)

    assert row.role == UserRole.ADMIN
    assert row.subscription_plan == SubscriptionPlan.PRO
    assert row.subscription_status == SubscriptionStatus.ACTIVE
    assert row.subscription_updated_at is not None


def test_admin_activation_metrics_summary_aggregates_without_sensitive_content():
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    raw_phone = "13800138000"
    raw_chat = "我的体检和饮食隐私正文"
    raw_correction = "AI 放宽了过敏限制"
    users = [
        User(id=1, phone=raw_phone, password_hash="x", is_active=True, is_verified=True),
        User(
            id=2,
            phone="13800138001",
            password_hash="x",
            is_active=True,
            is_verified=False,
            subscription_plan=SubscriptionPlan.PRO,
            subscription_status=SubscriptionStatus.ACTIVE,
        ),
        User(id=3, phone="13800138002", password_hash="x", is_active=False, is_verified=False),
    ]
    users[0].created_at = now
    users[1].created_at = now - timedelta(days=1)
    users[2].created_at = now - timedelta(days=10)

    meals = [
        Meal(
            id=1,
            user_id=1,
            client_id="m1",
            name="番茄鸡蛋面",
            portion="1碗",
            calories=360,
            sodium=700,
            purine=50,
            meal_type=MealType.LUNCH,
            category=FoodCategory.STAPLE,
            record_date=date(2026, 5, 30),
            source=MealSource.PHOTO.value,
        ),
        Meal(
            id=2,
            user_id=2,
            client_id="m2",
            name="清粥",
            portion="1碗",
            calories=120,
            sodium=80,
            purine=10,
            meal_type=MealType.BREAKFAST,
            category=FoodCategory.STAPLE,
            record_date=date(2026, 5, 29),
            source=MealSource.AI_QUICK_LOG.value,
        ),
        Meal(
            id=3,
            user_id=3,
            client_id="old",
            name="旧记录",
            portion="1份",
            calories=100,
            sodium=100,
            purine=10,
            meal_type=MealType.SNACK,
            category=FoodCategory.SNACK,
            record_date=date(2026, 5, 20),
            source=MealSource.MANUAL.value,
        ),
    ]
    meals[0].created_at = now
    meals[1].created_at = now - timedelta(days=1)
    meals[2].created_at = now - timedelta(days=10)

    chat_sessions = [
        ChatSession(id=1, user_id=1, title="coach"),
        ChatSession(id=2, user_id=3, title="old"),
    ]
    chat_sessions[0].created_at = now
    chat_sessions[1].created_at = now - timedelta(days=10)
    assistant_messages = [
        ChatMessage(id=1, session_id=1, role=MessageRole.ASSISTANT, content=raw_chat),
        ChatMessage(id=2, session_id=2, role=MessageRole.ASSISTANT, content="old"),
    ]
    assistant_messages[0].created_at = now
    assistant_messages[1].created_at = now - timedelta(days=10)
    feedback_rows = [
        AIFeedback(
            id=1,
            user_id=1,
            feedback_type=AIFeedbackType.UNSAFE,
            status=AIFeedbackStatus.OPEN,
            correction_text=raw_correction,
            correction_text_hash=hash_sensitive_value(raw_correction),
        ),
        AIFeedback(id=2, user_id=2, feedback_type=AIFeedbackType.HELPFUL, status=AIFeedbackStatus.CLOSED),
    ]
    feedback_rows[0].created_at = now
    feedback_rows[1].created_at = now - timedelta(days=1)
    security_rows = [
        SecurityAuditLog(id=1, event_type="otp.login.send", event_status="limited"),
        SecurityAuditLog(id=2, event_type="auth.refresh", event_status="revoked_or_reused"),
        SecurityAuditLog(id=3, event_type="admin.access", event_status="denied"),
    ]
    for row in security_rows:
        row.created_at = now
    health_metrics = [
        HealthMetric(
            id=1,
            user_id=1,
            metric_type=HealthMetricType.WEIGHT,
            value=70.5,
            unit="kg",
            recorded_at=now - timedelta(days=30),
        )
    ]
    health_metrics[0].created_at = now

    summary = admin_route._build_activation_metrics_summary(
        users=users,
        meals=meals,
        chat_sessions=chat_sessions,
        assistant_messages=assistant_messages,
        feedback_rows=feedback_rows,
        security_rows=security_rows,
        health_metrics=health_metrics,
        window_days=2,
        generated_at=now,
    )
    serialized = summary.model_dump_json()

    assert summary.total_users == 3
    assert summary.active_users == 2
    assert summary.verified_users == 1
    assert summary.new_users == 2
    assert summary.paid_active_users == 1
    assert summary.meal_users == 2
    assert summary.meal_count == 2
    assert summary.photo_meal_count == 1
    assert summary.ai_quick_log_count == 1
    assert summary.chat_users == 1
    assert summary.chat_session_count == 1
    assert summary.assistant_message_count == 1
    assert summary.feedback_count == 2
    assert summary.open_feedback_count == 1
    assert summary.unsafe_open_feedback_count == 1
    assert summary.health_metric_users == 1
    assert summary.health_metric_count == 1
    assert summary.security_event_count == 3
    assert summary.auth_lockout_count == 1
    assert summary.refresh_reuse_count == 1
    assert summary.admin_denied_count == 1
    assert [row.date for row in summary.daily_activity] == [date(2026, 5, 29), date(2026, 5, 30)]
    assert summary.daily_activity[-1].meals == 1
    assert summary.daily_activity[-1].meal_users == 1
    assert raw_phone not in serialized
    assert raw_chat not in serialized
    assert raw_correction not in serialized


def test_admin_commercialization_summary_aggregates_safe_billing_and_usage_pressure():
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    raw_phone = "13800138000"
    raw_chat = "用户聊天隐私正文"
    raw_meal_name = "私密餐食名称"
    raw_payment_note = "用户支付备注和联系方式"
    users = [
        User(
            id=1,
            phone=raw_phone,
            password_hash="x",
            subscription_plan=SubscriptionPlan.FREE,
            subscription_status=SubscriptionStatus.INACTIVE,
        ),
        User(
            id=2,
            phone="13800138001",
            password_hash="x",
            subscription_plan=SubscriptionPlan.PRO,
            subscription_status=SubscriptionStatus.ACTIVE,
        ),
        User(
            id=3,
            phone="13800138002",
            password_hash="x",
            subscription_plan=SubscriptionPlan.PRO,
            subscription_status=SubscriptionStatus.CANCELED,
        ),
    ]
    billing_events = [
        SecurityAuditLog(
            id=1,
            event_type="billing.checkout",
            event_status="success",
            metadata_json={"raw_note": raw_payment_note},
        ),
        SecurityAuditLog(id=2, event_type="billing.subscription.cancel", event_status="success"),
        SecurityAuditLog(id=3, event_type="billing.usage.list", event_status="success"),
        SecurityAuditLog(id=4, event_type="auth.login", event_status="success"),
    ]
    for event in billing_events:
        event.created_at = now

    summary = admin_route._build_commercialization_summary(
        users=users,
        billing_events=billing_events,
        ai_chat_usage_by_user={1: 8, 2: 190, 3: 15},
        photo_usage_by_user={2: 600, 3: 19},
        window_days=30,
        billing_provider="mock",
        generated_at=now,
    )
    payload = summary.model_dump_json()
    pressure = {item.key: item for item in summary.usage_pressure}

    assert summary.billing_provider == "mock"
    assert summary.total_users == 3
    assert summary.active_paid_users == 1
    assert summary.canceled_paid_users == 1
    assert summary.plan_counts == {"FREE": 1, "PRO": 2, "COACH": 0}
    assert summary.status_counts == {"inactive": 1, "active": 1, "canceled": 1}
    assert summary.checkout_event_count == 1
    assert summary.cancel_event_count == 1
    assert summary.usage_snapshot_count == 1
    assert summary.event_type_counts["billing.checkout"] == 1
    assert "auth.login" not in summary.event_type_counts
    assert pressure["ai_chat_daily"].total_usage == 213
    assert pressure["ai_chat_daily"].usage_users == 3
    assert pressure["ai_chat_daily"].near_limit_users == 2
    assert pressure["ai_chat_daily"].over_limit_users == 1
    assert pressure["photo_recognition_monthly"].total_usage == 619
    assert pressure["photo_recognition_monthly"].near_limit_users == 1
    assert pressure["photo_recognition_monthly"].over_limit_users == 1
    assert raw_phone not in payload
    assert raw_chat not in payload
    assert raw_meal_name not in payload
    assert raw_payment_note not in payload



def test_admin_ai_telemetry_summary_uses_only_structured_attachments():
    raw_content = "我今晚吃了很多隐私内容"
    rows = [
        ChatMessage(
            id=1,
            session_id=1,
            role=MessageRole.ASSISTANT,
            content=raw_content,
            attachments={
                "knowledge": {
                    "origin": "MIXED",
                    "fallback_status": "NO_LOCAL_MATCH_ALLOW_CLOUD",
                    "called_cloud": True,
                },
                "telemetry": {
                    "cloud_called": True,
                    "chat_total_ms": 120.0,
                    "doubao_total_ms": 80.0,
                    "doubao_error": "TimeoutError",
                    "cost_status": "placeholder",
                },
            },
        ),
        ChatMessage(
            id=2,
            session_id=1,
            role=MessageRole.ASSISTANT,
            content="本地规则答复",
            attachments={
                "knowledge": {
                    "origin": "LOCAL_RULE",
                    "fallback_status": "LOCAL_BLOCKED_NO_CLOUD",
                    "called_cloud": False,
                },
                "telemetry": {
                    "cloud_called": False,
                    "chat_total_ms": 20.0,
                    "doubao_total_ms": 0,
                    "cost_status": "placeholder",
                },
            },
        ),
    ]

    summary = admin_route._build_ai_telemetry_summary(rows, limit=50)
    serialized = summary.model_dump_json()

    assert summary.sampled_messages == 2
    assert summary.cloud_call_count == 1
    assert summary.local_direct_count == 1
    assert summary.error_count == 1
    assert summary.avg_chat_total_ms == 70.0
    assert summary.avg_doubao_total_ms == 40.0
    assert summary.cost_status == "unconfigured"
    assert summary.origin_counts == {"MIXED": 1, "LOCAL_RULE": 1}
    assert summary.fallback_status_counts["LOCAL_BLOCKED_NO_CLOUD"] == 1
    assert summary.recent_error_types == ["TimeoutError"]
    assert raw_content not in serialized


def test_admin_release_readiness_blocks_on_unsafe_feedback_and_refresh_reuse():
    raw_correction = "这个 AI 回复放宽了花生过敏限制"
    feedback_rows = [
        AIFeedback(
            id=1,
            user_id=2,
            feedback_type=AIFeedbackType.UNSAFE,
            status=AIFeedbackStatus.OPEN,
            correction_text=raw_correction,
            correction_text_hash=hash_sensitive_value(raw_correction),
        ),
        AIFeedback(
            id=2,
            user_id=2,
            feedback_type=AIFeedbackType.KNOWLEDGE_GAP,
            status=AIFeedbackStatus.OPEN,
        ),
    ]
    security_rows = [
        SecurityAuditLog(id=1, event_type="auth.refresh", event_status="revoked_or_reused"),
        SecurityAuditLog(id=2, event_type="otp.login.send", event_status="limited"),
        SecurityAuditLog(id=3, event_type="admin.access", event_status="denied"),
    ]
    knowledge_rows = [
        KnowledgeAuditLog(
            id=1,
            route_name="/api/chat",
            origin=KnowledgeOrigin.CLOUD_SUPPLEMENT,
            fallback_status=FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD,
            matched_disease_codes_json=[],
            matched_food_codes_json=[],
            unmapped_conditions_json=["未知禁忌"],
            called_cloud=True,
        ),
    ]
    telemetry = admin_route._build_ai_telemetry_summary(
        [
            ChatMessage(
                id=1,
                session_id=1,
                role=MessageRole.ASSISTANT,
                content="raw health text must not leak",
                attachments={
                    "telemetry": {
                        "cloud_called": True,
                        "chat_total_ms": 120,
                        "doubao_error": "TimeoutError",
                    }
                },
            )
        ],
        limit=50,
    )

    summary = admin_route._build_release_readiness_summary(
        security_rows=security_rows,
        knowledge_rows=knowledge_rows,
        feedback_rows=feedback_rows,
        telemetry=telemetry,
        limit=50,
    )
    serialized = summary.model_dump_json()
    gate_statuses = {item.key: item.status for item in summary.gate_items}

    assert summary.status == "red"
    assert summary.blocker_count == 2
    assert gate_statuses["unsafe_feedback"] == "block"
    assert gate_statuses["refresh_reuse"] == "block"
    assert gate_statuses["ai_errors"] == "warn"
    assert [item.key for item in summary.action_items] == ["unsafe_feedback", "refresh_reuse", "ai_errors"]
    assert summary.signals["feedback_followup_open"] == 1
    assert summary.signals["knowledge_gap_count"] == 1
    assert raw_correction not in serialized
    assert "raw health text must not leak" not in serialized


def test_admin_release_readiness_green_when_no_gate_counts():
    summary = admin_route._build_release_readiness_summary(
        security_rows=[],
        knowledge_rows=[],
        feedback_rows=[],
        telemetry=admin_route._build_ai_telemetry_summary([], limit=50),
        limit=50,
    )

    assert summary.status == "green"
    assert summary.blocker_count == 0
    assert summary.warning_count == 0
    assert all(item.status == "pass" for item in summary.gate_items)
    assert summary.action_items == []


def test_admin_release_readiness_warns_on_unreviewed_food_nutrition_without_leaking_food_details():
    raw_food_name = "内部试验菜品-高钠版本"
    food_rows = [
        FoodItem(
            id=1,
            food_code="reviewed_food",
            name_zh="已复核食物",
            category="STAPLE",
            nutrition_source_code="core_v1_food_composition_reference",
            nutrition_source_detail="Reviewed public reference normalized to 100g.",
            nutrition_estimate_quality="STANDARD_REFERENCE",
            nutrition_review_status="REVIEWED",
            is_enabled=True,
        ),
        FoodItem(
            id=2,
            food_code="unreviewed_food",
            name_zh=raw_food_name,
            category="SNACK",
            nutrition_source_code="",
            nutrition_source_detail="",
            nutrition_estimate_quality="",
            nutrition_review_status="DRAFT",
            is_enabled=True,
        ),
    ]

    summary = admin_route._build_release_readiness_summary(
        security_rows=[],
        knowledge_rows=[],
        feedback_rows=[],
        food_rows=food_rows,
        telemetry=admin_route._build_ai_telemetry_summary([], limit=50),
        limit=50,
    )
    serialized = summary.model_dump_json()
    gate_statuses = {item.key: item.status for item in summary.gate_items}

    assert summary.status == "yellow"
    assert summary.blocker_count == 0
    assert summary.warning_count == 1
    food_gate = next(item for item in summary.gate_items if item.key == "food_nutrition_review")

    assert gate_statuses["food_nutrition_review"] == "warn"
    assert [item.key for item in summary.action_items] == ["food_nutrition_review"]
    assert food_gate.count == 1
    assert summary.signals["food_nutrition_problem_count"] == 1
    assert summary.signals["food_nutrition_missing_provenance_count"] == 1
    assert summary.signals["food_nutrition_unreviewed_count"] == 1
    assert summary.signals["sampled_food_items"] == 2
    assert raw_food_name not in serialized


def test_admin_release_readiness_warns_on_offline_sync_problems_without_leaking_meal_details():
    raw_meal_name = "家庭私房菜-备注不可泄漏"
    meal_rows = [
        Meal(
            id=1,
            user_id=2,
            client_id="offline-failed-1",
            name=raw_meal_name,
            portion="1份",
            meal_type=MealType.LUNCH,
            category=FoodCategory.STAPLE,
            record_date=date(2026, 5, 31),
            sync_status=SyncStatus.FAILED,
            note="raw offline note must not leak",
        ),
        Meal(
            id=2,
            user_id=2,
            client_id="offline-conflict-1",
            name="冲突餐",
            portion="1份",
            meal_type=MealType.DINNER,
            category=FoodCategory.MEAT,
            record_date=date(2026, 5, 31),
            sync_status=SyncStatus.CONFLICT,
        ),
    ]

    summary = admin_route._build_release_readiness_summary(
        security_rows=[],
        knowledge_rows=[],
        feedback_rows=[],
        meal_rows=meal_rows,
        telemetry=admin_route._build_ai_telemetry_summary([], limit=50),
        limit=50,
    )
    serialized = summary.model_dump_json()
    gate_statuses = {item.key: item.status for item in summary.gate_items}

    assert summary.status == "yellow"
    assert summary.blocker_count == 0
    assert summary.warning_count == 1
    assert gate_statuses["offline_sync_health"] == "warn"
    assert [item.key for item in summary.action_items] == ["offline_sync_health"]
    assert summary.signals["offline_sync_problem_count"] == 2
    assert summary.signals["offline_sync_failed_count"] == 1
    assert summary.signals["offline_sync_conflict_count"] == 1
    assert summary.signals["sampled_offline_sync_problem_meals"] == 2
    assert raw_meal_name not in serialized
    assert "raw offline note must not leak" not in serialized


def test_admin_release_readiness_blocks_when_offline_sync_problems_exceed_threshold():
    meal_rows = [
        Meal(
            id=index + 1,
            user_id=2,
            client_id=f"offline-problem-{index}",
            name="不会出现在 readiness payload",
            portion="1份",
            meal_type=MealType.LUNCH,
            category=FoodCategory.STAPLE,
            record_date=date(2026, 5, 31),
            sync_status=SyncStatus.FAILED if index % 2 else SyncStatus.CONFLICT,
        )
        for index in range(21)
    ]

    summary = admin_route._build_release_readiness_summary(
        security_rows=[],
        knowledge_rows=[],
        feedback_rows=[],
        meal_rows=meal_rows,
        telemetry=admin_route._build_ai_telemetry_summary([], limit=50),
        limit=50,
    )
    gate_statuses = {item.key: item.status for item in summary.gate_items}

    assert summary.status == "red"
    assert summary.blocker_count == 1
    assert gate_statuses["offline_sync_health"] == "block"
    assert [item.key for item in summary.action_items] == ["offline_sync_health"]
    assert summary.signals["offline_sync_problem_count"] == 21


def test_admin_release_readiness_blocks_on_config_snapshot_without_leaking_raw_values():
    raw_api_key = "sk-prod-secret-value"
    raw_model_id = "ep-prod-secret-model"
    raw_database_url = "postgresql+asyncpg://user:password@db.example.com:5432/prism"
    summary = admin_route._build_release_readiness_summary(
        security_rows=[],
        knowledge_rows=[],
        feedback_rows=[],
        telemetry=admin_route._build_ai_telemetry_summary([], limit=50),
        limit=50,
        config_snapshot={
            "status": "blocked",
            "blocking": ["ai_key_placeholder_or_missing", "database_not_ready"],
            "warnings": ["non_production_environment"],
            "ark_api_key": raw_api_key,
            "doubao_model": raw_model_id,
            "database_url": raw_database_url,
        },
    )
    serialized = summary.model_dump_json()
    gate_statuses = {item.key: item.status for item in summary.gate_items}

    assert summary.status == "red"
    assert summary.blocker_count == 1
    assert gate_statuses["config_readiness"] == "block"
    assert [item.key for item in summary.action_items] == ["config_readiness"]
    assert summary.signals["config_blocking_count"] == 2
    assert summary.signals["config_warning_count"] == 1
    assert raw_api_key not in serialized
    assert raw_model_id not in serialized
    assert raw_database_url not in serialized
    assert "API keys" in serialized
    assert "model IDs" in serialized
    assert "数据库凭据" in serialized
    assert "secrets" in serialized


def test_admin_release_readiness_warns_on_config_snapshot_warnings():
    summary = admin_route._build_release_readiness_summary(
        security_rows=[],
        knowledge_rows=[],
        feedback_rows=[],
        telemetry=admin_route._build_ai_telemetry_summary([], limit=50),
        limit=50,
        config_snapshot={
            "status": "ok",
            "blocking": [],
            "warnings": ["non_production_environment", "dev_otp_provider"],
        },
    )
    gate_statuses = {item.key: item.status for item in summary.gate_items}

    assert summary.status == "yellow"
    assert summary.blocker_count == 0
    assert summary.warning_count == 1
    assert gate_statuses["config_readiness"] == "warn"
    assert [item.key for item in summary.action_items] == ["config_readiness"]
    assert summary.signals["config_blocking_count"] == 0
    assert summary.signals["config_warning_count"] == 2
