"""Minimal admin operations API.

Admin access is intentionally strict: callers must be authenticated users with
a persisted ADMIN role or a phone hash in ADMIN_PHONE_HASHES. Responses avoid
raw phone numbers, tokens, OTPs, health text, and images; operational views use
hashes and structured metadata wherever possible.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from collections import Counter
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, or_, select

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.security import hash_sensitive_value
from app.models.chat import ChatMessage, ChatSession, MessageRole
from app.models.feedback import AIFeedback, AIFeedbackStatus, AIFeedbackType
from app.models.health_metric import HealthMetric
from app.models.intake_telemetry import IntakeReviewTelemetrySnapshot
from app.models.knowledge import FallbackStatus, FoodItem, KnowledgeAuditLog, KnowledgeOrigin
from app.models.meal import Meal, MealSource, SyncStatus
from app.models.security import SecurityAuditLog
from app.models.user import SubscriptionPlan, SubscriptionStatus, User, UserRole
from app.schemas.intake import REVIEW_TELEMETRY_SOURCE_KEYS, REVIEW_TELEMETRY_STATUS_KEYS
from app.services.auth_security import audit_security_event
from app.services.billing_providers import normalize_billing_provider
from app.services.entitlements import PLAN_LIMITS, PlanTier


router = APIRouter(prefix="/admin", tags=["运营后台"])


class SecurityAuditItem(BaseModel):
    id: int
    user_id: Optional[int] = None
    event_type: str
    event_status: str
    route_name: Optional[str] = None
    actor_hash: Optional[str] = None
    ip_hash: Optional[str] = None
    user_agent_hash: Optional[str] = None
    session_id: Optional[str] = None
    metadata_json: Optional[dict] = None
    created_at: datetime


class KnowledgeAuditItem(BaseModel):
    id: int
    user_id: Optional[int] = None
    route_name: str
    chat_session_id: Optional[int] = None
    chat_message_id: Optional[int] = None
    query_excerpt_hash: Optional[str] = None
    origin: str
    fallback_status: str
    matched_disease_codes: list[str]
    matched_food_codes: list[str]
    unmapped_conditions: list[str]
    local_decision_level: Optional[str] = None
    called_cloud: bool
    cloud_call_reason: Optional[str] = None
    cloud_blocked_reason: Optional[str] = None
    created_at: datetime


class FeedbackItem(BaseModel):
    id: int
    user_id: int
    session_id: Optional[int] = None
    message_id: Optional[int] = None
    app_message_id: Optional[int] = None
    feedback_type: str
    rating: Optional[int] = None
    tags: list[str]
    status: str
    has_correction: bool
    correction_text_hash: Optional[str] = None
    metadata_json: Optional[dict] = None
    metadata_keys: list[str] = Field(default_factory=list)
    created_at: datetime
    reviewed_at: Optional[datetime] = None


class KnowledgeBacklogItem(BaseModel):
    source: str
    id: int
    user_id: Optional[int] = None
    feedback_type: Optional[str] = None
    status: Optional[str] = None
    route_name: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata_keys: list[str] = Field(default_factory=list)
    has_correction: bool = False
    correction_text_hash: Optional[str] = None
    query_excerpt_hash: Optional[str] = None
    origin: Optional[str] = None
    fallback_status: Optional[str] = None
    matched_disease_codes: list[str] = Field(default_factory=list)
    matched_food_codes: list[str] = Field(default_factory=list)
    unmapped_condition_hashes: list[str] = Field(default_factory=list)
    called_cloud: Optional[bool] = None
    cloud_call_reason_code: Optional[str] = None
    cloud_blocked_reason_code: Optional[str] = None
    created_at: datetime


class KnowledgeBacklogSummary(BaseModel):
    generated_at: datetime
    window_limit: int
    feedback_followup_count: int
    feedback_open_count: int
    knowledge_audit_gap_count: int
    has_correction_count: int
    feedback_type_counts: dict[str, int]
    feedback_status_counts: dict[str, int]
    tag_counts: dict[str, int]
    correction_hash_counts: dict[str, int]
    fallback_status_counts: dict[str, int]
    cloud_call_reason_counts: dict[str, int]
    cloud_blocked_reason_counts: dict[str, int]
    matched_disease_counts: dict[str, int]
    matched_food_counts: dict[str, int]
    unmapped_condition_counts: dict[str, int]
    food_nutrition_source_counts: dict[str, int] = Field(default_factory=dict)
    food_nutrition_quality_counts: dict[str, int] = Field(default_factory=dict)
    food_nutrition_review_status_counts: dict[str, int] = Field(default_factory=dict)
    food_nutrition_unreviewed_count: int = 0
    recent_items: list[KnowledgeBacklogItem]
    notes: list[str]


class FeedbackStatusUpdate(BaseModel):
    status: AIFeedbackStatus


class AdminUserItem(BaseModel):
    id: int
    phone_hash: Optional[str] = None
    nickname: Optional[str] = None
    role: UserRole
    subscription_plan: SubscriptionPlan
    subscription_status: SubscriptionStatus
    subscription_updated_at: Optional[datetime] = None
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserSubscriptionUpdate(BaseModel):
    plan: SubscriptionPlan
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE


class AITelemetrySummary(BaseModel):
    window_limit: int
    sampled_messages: int
    telemetry_sample_count: int
    cloud_call_count: int
    local_direct_count: int
    error_count: int
    avg_chat_total_ms: Optional[float] = None
    avg_doubao_total_ms: Optional[float] = None
    p95_chat_total_ms: Optional[float] = None
    estimated_cost_usd: Optional[float] = None
    cost_status: str
    origin_counts: dict[str, int]
    fallback_status_counts: dict[str, int]
    recent_error_types: list[str]


class IntakeReviewTelemetryAggregate(BaseModel):
    snapshot_count: int = 0
    user_count: int = 0
    total_count: int = 0
    pending_review_count: int = 0
    in_review_count: int = 0
    low_confidence_count: int = 0
    high_risk_count: int = 0
    hard_block_count: int = 0
    source_counts: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)


class ReadinessGateItem(BaseModel):
    key: str
    label: str
    status: str
    count: int
    warn_threshold: int
    block_threshold: int
    message: str


class ReleaseReadinessSummary(BaseModel):
    status: str
    generated_at: datetime
    window_limit: int
    blocker_count: int
    warning_count: int
    gate_items: list[ReadinessGateItem]
    action_items: list[ReadinessGateItem] = Field(default_factory=list)
    signals: dict[str, int]
    notes: list[str]


class ActivationDailyMetric(BaseModel):
    date: date
    meals: int = 0
    meal_users: int = 0
    chat_sessions: int = 0
    assistant_messages: int = 0
    feedback: int = 0
    security_events: int = 0
    health_metrics: int = 0


class ActivationMetricsSummary(BaseModel):
    generated_at: datetime
    window_days: int
    total_users: int
    active_users: int
    verified_users: int
    new_users: int
    paid_active_users: int
    meal_users: int
    meal_count: int
    photo_meal_count: int
    ai_quick_log_count: int
    intake_review_telemetry: IntakeReviewTelemetryAggregate = Field(default_factory=IntakeReviewTelemetryAggregate)
    chat_users: int
    chat_session_count: int
    assistant_message_count: int
    feedback_count: int
    open_feedback_count: int
    unsafe_open_feedback_count: int
    health_metric_users: int
    health_metric_count: int
    security_event_count: int
    auth_lockout_count: int
    refresh_reuse_count: int
    admin_denied_count: int
    daily_activity: list[ActivationDailyMetric]
    notes: list[str]


class CommercializationUsagePressureItem(BaseModel):
    key: str
    label: str
    period: str
    total_usage: int
    usage_users: int
    near_limit_users: int
    over_limit_users: int


class CommercializationSummary(BaseModel):
    generated_at: datetime
    window_days: int
    billing_provider: str
    total_users: int
    active_paid_users: int
    canceled_paid_users: int
    plan_counts: dict[str, int]
    status_counts: dict[str, int]
    checkout_event_count: int
    cancel_event_count: int
    usage_snapshot_count: int
    usage_pressure: list[CommercializationUsagePressureItem]
    event_type_counts: dict[str, int]
    event_status_counts: dict[str, int]
    notes: list[str]


KNOWLEDGE_BACKLOG_FEEDBACK_TYPES = {
    AIFeedbackType.CORRECTION,
    AIFeedbackType.RECOGNITION_CORRECTION,
    AIFeedbackType.KNOWLEDGE_GAP,
}
KNOWLEDGE_BACKLOG_FALLBACK_STATUSES = {
    FallbackStatus.LOCAL_PARTIAL_ALLOW_CLOUD.value,
    FallbackStatus.LOCAL_BLOCKED_NO_CLOUD.value,
    FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD.value,
}


def _enum_value(value):
    return getattr(value, "value", value)


def _safe_code_or_hash(value: object) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.:")
    if len(normalized) <= 80 and all(ch in safe_chars for ch in normalized):
        return normalized
    return f"hash:{hash_sensitive_value(normalized)[:16]}"


def _safe_list(values: Optional[list[str]]) -> list[str]:
    safe_values: list[str] = []
    for value in values or []:
        safe = _safe_code_or_hash(value)
        if safe and safe not in safe_values:
            safe_values.append(safe)
    return safe_values


def _safe_reason_code(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    known_reasons = [
        ("本地命中过敏", "local_rule_safety_block"),
        ("AVOID", "local_rule_safety_block"),
        ("LIMIT", "local_rule_safety_block"),
        ("不得放宽", "local_rule_safety_block"),
        ("本地知识已足够", "local_complete_no_cloud"),
        ("本地已命中部分", "partial_local_cloud_supplement"),
        ("本地知识未命中", "no_local_match_cloud_fallback"),
        ("图片识别依赖", "vision_model_with_postcheck"),
        ("本地候选解析", "local_intake_only"),
        ("调用云端补充说明", "cloud_supplement"),
    ]
    for needle, code in known_reasons:
        if needle in normalized:
            return code
    safe = _safe_code_or_hash(normalized)
    if safe and safe.startswith("hash:"):
        return f"reason_{safe}"
    return safe


def _counter_dict(counter: Counter, *, limit: int = 12) -> dict[str, int]:
    return {key: count for key, count in counter.most_common(limit) if key}


def _metadata_keys(metadata: Optional[dict]) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    keys = []
    for key in sorted(metadata):
        safe = _safe_code_or_hash(key)
        if safe:
            keys.append(safe)
    return keys[:20]


def _numeric_telemetry_values(rows: list[tuple[ChatMessage, dict[str, object], dict[str, object]]], key: str) -> list[float]:
    values: list[float] = []
    for _message, telemetry, _knowledge in rows:
        value = telemetry.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return values


def _normalize_cost_status(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "placeholder":
        return "unconfigured"
    return normalized or "no_telemetry"


def _ai_cost_summary(
    rows: list[tuple[ChatMessage, dict[str, object], dict[str, object]]]
) -> tuple[Optional[float], str]:
    if not rows:
        return None, "no_samples"

    statuses = Counter(
        _normalize_cost_status(telemetry.get("cost_status"))
        for _row, telemetry, _knowledge in rows
        if telemetry
    )
    if not statuses:
        return None, "no_telemetry"

    cost_values = _numeric_telemetry_values(rows, "estimated_cost_usd")
    estimated_total = round(sum(cost_values), 6) if cost_values else None

    if statuses.get("estimated") and any(
        statuses.get(status)
        for status in {"unconfigured", "insufficient_usage_data", "no_telemetry"}
    ):
        return estimated_total, "partial_estimate"
    if statuses.get("estimated"):
        return estimated_total, "estimated"
    if set(statuses) == {"local_only"}:
        return 0.0, "local_only"
    if statuses.get("unconfigured"):
        return None, "unconfigured"
    if statuses.get("insufficient_usage_data"):
        return None, "insufficient_usage_data"
    return estimated_total, statuses.most_common(1)[0][0]


def _mean(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _p95(values: list[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
    return round(ordered[index], 2)


def _attachment_payload(row: ChatMessage) -> tuple[dict[str, object], dict[str, object]]:
    attachments = row.attachments if isinstance(row.attachments, dict) else {}
    telemetry = attachments.get("telemetry") if isinstance(attachments.get("telemetry"), dict) else {}
    knowledge = attachments.get("knowledge") if isinstance(attachments.get("knowledge"), dict) else {}
    return telemetry, knowledge


def _window_start(days: int) -> datetime:
    safe_days = max(1, min(days, 90))
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=safe_days - 1)).date()
    return datetime.combine(start_date, time.min, tzinfo=timezone.utc)


def _as_utc_date(value: datetime | date | None) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date()
        return value.astimezone(timezone.utc).date()
    return value


def _daily_rows(start_date: date, window_days: int) -> dict[date, ActivationDailyMetric]:
    return {
        start_date + timedelta(days=offset): ActivationDailyMetric(date=start_date + timedelta(days=offset))
        for offset in range(window_days)
    }


def _is_auth_lockout(row: SecurityAuditLog) -> bool:
    event_type = str(row.event_type)
    if event_type.startswith(("otp.", "auth.otp")) and row.event_status in {"limited", "failure_locked"}:
        return True
    return event_type == "auth.password_login" and row.event_status == "failure_locked"


def _effective_usage_plan_for_user(user: User) -> PlanTier:
    raw_plan = _enum_value(getattr(user, "subscription_plan", SubscriptionPlan.FREE))
    raw_status = _enum_value(getattr(user, "subscription_status", SubscriptionStatus.INACTIVE))
    if raw_status != SubscriptionStatus.ACTIVE.value:
        return PlanTier.FREE
    try:
        return PlanTier(str(raw_plan))
    except ValueError:
        return PlanTier.FREE


def _plan_limit(plan: PlanTier, key: str) -> Optional[int]:
    value = PLAN_LIMITS.get(plan, {}).get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def _commercial_usage_pressure_item(
    *,
    users: list[User],
    usage_by_user: dict[int, int],
    key: str,
    label: str,
    period: str,
) -> CommercializationUsagePressureItem:
    total_usage = sum(max(0, int(value or 0)) for value in usage_by_user.values())
    usage_users = sum(1 for value in usage_by_user.values() if int(value or 0) > 0)
    near_limit_users = 0
    over_limit_users = 0

    for user in users:
        current = max(0, int(usage_by_user.get(user.id, 0) or 0))
        if current <= 0:
            continue
        limit = _plan_limit(_effective_usage_plan_for_user(user), key)
        if limit is None:
            continue
        if current >= limit:
            over_limit_users += 1
        elif current >= max(1, int(limit * 0.8)):
            near_limit_users += 1

    return CommercializationUsagePressureItem(
        key=key,
        label=label,
        period=period,
        total_usage=total_usage,
        usage_users=usage_users,
        near_limit_users=near_limit_users,
        over_limit_users=over_limit_users,
    )


def _build_commercialization_summary(
    *,
    users: list[User],
    billing_events: list[SecurityAuditLog],
    ai_chat_usage_by_user: dict[int, int],
    photo_usage_by_user: dict[int, int],
    window_days: int,
    billing_provider: str,
    generated_at: Optional[datetime] = None,
) -> CommercializationSummary:
    safe_days = max(1, min(window_days, 90))
    generated = generated_at or datetime.now(timezone.utc)
    plan_counts = {plan.value: 0 for plan in SubscriptionPlan}
    status_counts = {status.value: 0 for status in SubscriptionStatus}

    for user in users:
        plan = _safe_code_or_hash(_enum_value(getattr(user, "subscription_plan", SubscriptionPlan.FREE))) or SubscriptionPlan.FREE.value
        status = _safe_code_or_hash(_enum_value(getattr(user, "subscription_status", SubscriptionStatus.INACTIVE))) or SubscriptionStatus.INACTIVE.value
        plan_counts[plan] = plan_counts.get(plan, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1

    billing_rows = [row for row in billing_events if str(row.event_type).startswith("billing.")]
    event_type_counts = Counter(
        _safe_code_or_hash(row.event_type)
        for row in billing_rows
        if _safe_code_or_hash(row.event_type)
    )
    event_status_counts = Counter(
        _safe_code_or_hash(row.event_status)
        for row in billing_rows
        if _safe_code_or_hash(row.event_status)
    )
    usage_pressure = [
        _commercial_usage_pressure_item(
            users=users,
            usage_by_user=ai_chat_usage_by_user,
            key="ai_chat_daily",
            label="每日 AI 对话",
            period="day",
        ),
        _commercial_usage_pressure_item(
            users=users,
            usage_by_user=photo_usage_by_user,
            key="photo_recognition_monthly",
            label="每月拍照识别",
            period="month",
        ),
    ]
    active_paid_users = sum(
        1
        for user in users
        if _enum_value(getattr(user, "subscription_status", None)) == SubscriptionStatus.ACTIVE.value
        and _enum_value(getattr(user, "subscription_plan", None)) in {SubscriptionPlan.PRO.value, SubscriptionPlan.COACH.value}
    )
    canceled_paid_users = sum(
        1
        for user in users
        if _enum_value(getattr(user, "subscription_status", None)) == SubscriptionStatus.CANCELED.value
        and _enum_value(getattr(user, "subscription_plan", None)) in {SubscriptionPlan.PRO.value, SubscriptionPlan.COACH.value}
    )

    notes = [
        "当前为灰度商业化观测面板，不执行真实扣费。",
        "仅展示聚合计数和趋势，不返回原始内容、文件、凭据或联系方式。",
    ]
    if any(item.over_limit_users for item in usage_pressure):
        notes.append("存在用户超过灰度软额度，放量前应复核套餐限制和提醒策略。")
    if canceled_paid_users:
        notes.append("存在已取消付费档位用户，访谈时应关注取消原因。")

    return CommercializationSummary(
        generated_at=generated,
        window_days=safe_days,
        billing_provider=normalize_billing_provider(billing_provider),
        total_users=len(users),
        active_paid_users=active_paid_users,
        canceled_paid_users=canceled_paid_users,
        plan_counts=plan_counts,
        status_counts=status_counts,
        checkout_event_count=event_type_counts.get("billing.checkout", 0),
        cancel_event_count=event_type_counts.get("billing.subscription.cancel", 0),
        usage_snapshot_count=event_type_counts.get("billing.usage.list", 0),
        usage_pressure=usage_pressure,
        event_type_counts=_counter_dict(event_type_counts),
        event_status_counts=_counter_dict(event_status_counts),
        notes=notes,
    )


def _safe_int_count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _snapshot_time(row: IntakeReviewTelemetrySnapshot) -> datetime:
    value = getattr(row, "generated_at", None) or getattr(row, "created_at", None)
    if isinstance(value, datetime):
        return value
    return datetime.min.replace(tzinfo=timezone.utc)


def _build_intake_review_telemetry_aggregate(
    rows: list[IntakeReviewTelemetrySnapshot],
) -> IntakeReviewTelemetryAggregate:
    latest_by_user: dict[int, IntakeReviewTelemetrySnapshot] = {}
    for row in rows:
        user_id = getattr(row, "user_id", None)
        if user_id is None:
            continue
        current = latest_by_user.get(int(user_id))
        if current is None or _snapshot_time(row) >= _snapshot_time(current):
            latest_by_user[int(user_id)] = row

    latest_rows = list(latest_by_user.values())
    source_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

    for row in latest_rows:
        for key, value in (getattr(row, "source_counts_json", None) or {}).items():
            normalized_key = str(key)
            if normalized_key in REVIEW_TELEMETRY_SOURCE_KEYS:
                source_counts[normalized_key] += _safe_int_count(value)
        for key, value in (getattr(row, "status_counts_json", None) or {}).items():
            normalized_key = str(key)
            if normalized_key in REVIEW_TELEMETRY_STATUS_KEYS:
                status_counts[normalized_key] += _safe_int_count(value)

    return IntakeReviewTelemetryAggregate(
        snapshot_count=len(rows),
        user_count=len(latest_rows),
        total_count=sum(_safe_int_count(getattr(row, "total_count", 0)) for row in latest_rows),
        pending_review_count=sum(_safe_int_count(getattr(row, "pending_review_count", 0)) for row in latest_rows),
        in_review_count=sum(_safe_int_count(getattr(row, "in_review_count", 0)) for row in latest_rows),
        low_confidence_count=sum(_safe_int_count(getattr(row, "low_confidence_count", 0)) for row in latest_rows),
        high_risk_count=sum(_safe_int_count(getattr(row, "high_risk_count", 0)) for row in latest_rows),
        hard_block_count=sum(_safe_int_count(getattr(row, "hard_block_count", 0)) for row in latest_rows),
        source_counts=_counter_dict(source_counts),
        status_counts=_counter_dict(status_counts),
    )


def _build_activation_metrics_summary(
    *,
    users: list[User],
    meals: list[Meal],
    chat_sessions: list[ChatSession],
    assistant_messages: list[ChatMessage],
    feedback_rows: list[AIFeedback],
    security_rows: list[SecurityAuditLog],
    health_metrics: list[HealthMetric],
    window_days: int,
    intake_review_rows: Optional[list[IntakeReviewTelemetrySnapshot]] = None,
    generated_at: Optional[datetime] = None,
) -> ActivationMetricsSummary:
    safe_days = max(1, min(window_days, 90))
    generated = generated_at or datetime.now(timezone.utc)
    start_date = (generated - timedelta(days=safe_days - 1)).date()
    daily = _daily_rows(start_date, safe_days)
    window_dates = set(daily)

    for meal in meals:
        key = _as_utc_date(meal.created_at)
        if key in daily:
            daily[key].meals += 1

    meal_users_by_day: dict[date, set[int]] = {key: set() for key in daily}
    for meal in meals:
        key = _as_utc_date(meal.created_at)
        if key in meal_users_by_day:
            meal_users_by_day[key].add(meal.user_id)

    for session in chat_sessions:
        key = _as_utc_date(session.created_at)
        if key in daily:
            daily[key].chat_sessions += 1

    for message in assistant_messages:
        key = _as_utc_date(message.created_at)
        if key in daily:
            daily[key].assistant_messages += 1

    for feedback in feedback_rows:
        key = _as_utc_date(feedback.created_at)
        if key in daily:
            daily[key].feedback += 1

    for event in security_rows:
        key = _as_utc_date(event.created_at)
        if key in daily:
            daily[key].security_events += 1

    for metric in health_metrics:
        key = _as_utc_date(metric.created_at)
        if key in daily:
            daily[key].health_metrics += 1

    for key, user_ids in meal_users_by_day.items():
        daily[key].meal_users = len(user_ids)

    meal_user_ids = {meal.user_id for meal in meals if _as_utc_date(meal.created_at) in window_dates}
    chat_user_ids = {session.user_id for session in chat_sessions if _as_utc_date(session.created_at) in window_dates}
    health_metric_user_ids = {metric.user_id for metric in health_metrics if _as_utc_date(metric.created_at) in window_dates}
    window_feedback = [row for row in feedback_rows if _as_utc_date(row.created_at) in window_dates]
    window_security = [row for row in security_rows if _as_utc_date(row.created_at) in window_dates]
    intake_review_telemetry = _build_intake_review_telemetry_aggregate(intake_review_rows or [])

    open_feedback_count = sum(1 for row in feedback_rows if _enum_value(row.status) == AIFeedbackStatus.OPEN.value)
    unsafe_open_feedback_count = sum(
        1
        for row in feedback_rows
        if _enum_value(row.status) == AIFeedbackStatus.OPEN.value
        and _enum_value(row.feedback_type) == AIFeedbackType.UNSAFE.value
    )
    notes = [
        "仅展示聚合计数和趋势，不展示手机号、聊天正文、反馈正文或健康指标明细。",
    ]
    if not meal_user_ids:
        notes.append("当前窗口内暂无记餐用户，内测激活可能不足。")
    if unsafe_open_feedback_count:
        notes.append("存在未关闭的 unsafe 反馈，放量前需运营复核。")
    if any(_is_auth_lockout(row) for row in window_security):
        notes.append("窗口内出现 OTP 限流或锁定事件，应关注验证码成本与攻击面。")
    if intake_review_telemetry.pending_review_count or intake_review_telemetry.in_review_count:
        notes.append("存在本地候选复核待办；运营只接收聚合计数，原始候选内容仍留在用户设备。")

    return ActivationMetricsSummary(
        generated_at=generated,
        window_days=safe_days,
        total_users=len(users),
        active_users=sum(1 for user in users if bool(user.is_active)),
        verified_users=sum(1 for user in users if bool(user.is_verified)),
        new_users=sum(1 for user in users if _as_utc_date(user.created_at) in window_dates),
        paid_active_users=sum(
            1
            for user in users
            if _enum_value(user.subscription_status) == SubscriptionStatus.ACTIVE.value
            and _enum_value(user.subscription_plan) in {SubscriptionPlan.PRO.value, SubscriptionPlan.COACH.value}
        ),
        meal_users=len(meal_user_ids),
        meal_count=sum(1 for meal in meals if _as_utc_date(meal.created_at) in window_dates),
        photo_meal_count=sum(
            1
            for meal in meals
            if _as_utc_date(meal.created_at) in window_dates
            and _enum_value(getattr(meal, "source", "")) == MealSource.PHOTO.value
        ),
        ai_quick_log_count=sum(
            1
            for meal in meals
            if _as_utc_date(meal.created_at) in window_dates
            and _enum_value(getattr(meal, "source", "")) == MealSource.AI_QUICK_LOG.value
        ),
        intake_review_telemetry=intake_review_telemetry,
        chat_users=len(chat_user_ids),
        chat_session_count=sum(1 for session in chat_sessions if _as_utc_date(session.created_at) in window_dates),
        assistant_message_count=sum(1 for message in assistant_messages if _as_utc_date(message.created_at) in window_dates),
        feedback_count=len(window_feedback),
        open_feedback_count=open_feedback_count,
        unsafe_open_feedback_count=unsafe_open_feedback_count,
        health_metric_users=len(health_metric_user_ids),
        health_metric_count=sum(1 for metric in health_metrics if _as_utc_date(metric.created_at) in window_dates),
        security_event_count=len(window_security),
        auth_lockout_count=sum(1 for row in window_security if _is_auth_lockout(row)),
        refresh_reuse_count=sum(1 for row in window_security if row.event_type == "auth.refresh" and row.event_status == "revoked_or_reused"),
        admin_denied_count=sum(1 for row in window_security if row.event_type == "admin.access" and row.event_status == "denied"),
        daily_activity=[daily[key] for key in sorted(daily)],
        notes=notes,
    )


def _build_ai_telemetry_summary(rows: list[ChatMessage], *, limit: int) -> AITelemetrySummary:
    payloads = [(row, *_attachment_payload(row)) for row in rows]
    telemetry_sample_count = sum(1 for _row, telemetry, _knowledge in payloads if telemetry)
    cloud_call_count = sum(
        1 for _row, telemetry, knowledge in payloads
        if bool(telemetry.get("cloud_called")) or bool(knowledge.get("called_cloud"))
    )
    error_types = sorted(
        {
            str(value)
            for _row, telemetry, _knowledge in payloads
            for value in (telemetry.get("error"), telemetry.get("audit_error"), telemetry.get("doubao_error"))
            if isinstance(value, str) and value.strip()
        }
    )
    error_count = sum(
        1
        for _row, telemetry, _knowledge in payloads
        if any(
            isinstance(value, str) and value.strip()
            for value in (telemetry.get("error"), telemetry.get("audit_error"), telemetry.get("doubao_error"))
        )
    )
    origin_counts = Counter(
        str(knowledge.get("origin"))
        for _row, _telemetry, knowledge in payloads
        if knowledge.get("origin")
    )
    fallback_status_counts = Counter(
        str(knowledge.get("fallback_status"))
        for _row, _telemetry, knowledge in payloads
        if knowledge.get("fallback_status")
    )
    chat_total_values = _numeric_telemetry_values(payloads, "chat_total_ms")
    doubao_total_values = _numeric_telemetry_values(payloads, "doubao_total_ms")
    estimated_cost_usd, cost_status = _ai_cost_summary(payloads)

    return AITelemetrySummary(
        window_limit=limit,
        sampled_messages=len(rows),
        telemetry_sample_count=telemetry_sample_count,
        cloud_call_count=cloud_call_count,
        local_direct_count=max(0, len(rows) - cloud_call_count),
        error_count=error_count,
        avg_chat_total_ms=_mean(chat_total_values),
        avg_doubao_total_ms=_mean(doubao_total_values),
        p95_chat_total_ms=_p95(chat_total_values),
        estimated_cost_usd=estimated_cost_usd,
        cost_status=cost_status,
        origin_counts=dict(origin_counts),
        fallback_status_counts=dict(fallback_status_counts),
        recent_error_types=error_types,
    )


def _gate_item(
    *,
    key: str,
    label: str,
    count: int,
    warn_threshold: int,
    block_threshold: int,
    ok_message: str,
    warn_message: str,
    block_message: Optional[str] = None,
) -> ReadinessGateItem:
    if count > block_threshold:
        status_value = "block"
        message = block_message or warn_message
    elif count > warn_threshold:
        status_value = "warn"
        message = warn_message
    else:
        status_value = "pass"
        message = ok_message

    return ReadinessGateItem(
        key=key,
        label=label,
        status=status_value,
        count=count,
        warn_threshold=warn_threshold,
        block_threshold=block_threshold,
        message=message,
    )


def _build_release_readiness_summary(
    *,
    security_rows: list[SecurityAuditLog],
    knowledge_rows: list[KnowledgeAuditLog],
    feedback_rows: list[AIFeedback],
    telemetry: AITelemetrySummary,
    limit: int,
    food_rows: Optional[list[FoodItem]] = None,
    meal_rows: Optional[list[Meal]] = None,
    intake_review_telemetry: IntakeReviewTelemetryAggregate | None = None,
    config_snapshot: dict[str, object] | None = None,
) -> ReleaseReadinessSummary:
    unsafe_open_count = sum(
        1
        for row in feedback_rows
        if _enum_value(row.status) == AIFeedbackStatus.OPEN.value
        and _enum_value(row.feedback_type) == AIFeedbackType.UNSAFE.value
    )
    feedback_followup_count = sum(
        1
        for row in feedback_rows
        if _enum_value(row.status) == AIFeedbackStatus.OPEN.value
        and _enum_value(row.feedback_type) in {
            AIFeedbackType.CORRECTION.value,
            AIFeedbackType.RECOGNITION_CORRECTION.value,
            AIFeedbackType.KNOWLEDGE_GAP.value,
        }
    )
    auth_lockout_count = sum(1 for row in security_rows if _is_auth_lockout(row))
    refresh_reuse_count = sum(
        1
        for row in security_rows
        if row.event_type == "auth.refresh" and row.event_status == "revoked_or_reused"
    )
    admin_denied_count = sum(
        1
        for row in security_rows
        if row.event_type == "admin.access" and row.event_status == "denied"
    )
    knowledge_gap_count = sum(
        1
        for row in knowledge_rows
        if _enum_value(row.fallback_status) == FallbackStatus.NO_LOCAL_MATCH_ALLOW_CLOUD.value
        or bool(row.unmapped_conditions_json)
    )
    cloud_blocked_count = sum(
        1
        for row in knowledge_rows
        if bool(row.cloud_blocked_reason)
    )
    food_rows = food_rows or []

    def _food_nutrition_missing_provenance(row: FoodItem) -> bool:
        return (
            not str(getattr(row, "nutrition_source_code", "") or "").strip()
            or not str(getattr(row, "nutrition_source_detail", "") or "").strip()
            or not str(getattr(row, "nutrition_estimate_quality", "") or "").strip()
        )

    def _food_nutrition_unreviewed(row: FoodItem) -> bool:
        return (
            str(getattr(row, "nutrition_review_status", "") or "").strip().upper()
            != "REVIEWED"
        )

    food_nutrition_missing_provenance_count = sum(
        1 for row in food_rows if _food_nutrition_missing_provenance(row)
    )
    food_nutrition_unreviewed_count = sum(
        1 for row in food_rows if _food_nutrition_unreviewed(row)
    )
    food_nutrition_problem_count = sum(
        1
        for row in food_rows
        if _food_nutrition_missing_provenance(row) or _food_nutrition_unreviewed(row)
    )
    meal_rows = meal_rows or []
    offline_sync_failed_count = sum(
        1
        for row in meal_rows
        if _enum_value(getattr(row, "sync_status", "")) == SyncStatus.FAILED.value
    )
    offline_sync_conflict_count = sum(
        1
        for row in meal_rows
        if _enum_value(getattr(row, "sync_status", "")) == SyncStatus.CONFLICT.value
    )
    offline_sync_problem_count = offline_sync_failed_count + offline_sync_conflict_count
    intake_review_telemetry = intake_review_telemetry or IntakeReviewTelemetryAggregate()
    intake_review_backlog_count = (
        intake_review_telemetry.pending_review_count + intake_review_telemetry.in_review_count
    )
    config_blocking = config_snapshot.get("blocking") if config_snapshot else []
    config_warnings = config_snapshot.get("warnings") if config_snapshot else []
    config_blocking_count = len(config_blocking) if isinstance(config_blocking, list) else 0
    config_warning_count = len(config_warnings) if isinstance(config_warnings, list) else 0

    if config_blocking_count:
        config_gate = ReadinessGateItem(
            key="config_readiness",
            label="生产配置 readiness",
            status="block",
            count=config_blocking_count,
            warn_threshold=0,
            block_threshold=0,
            message="配置 readiness 快照存在阻断项，应先修复生产配置再放量。",
        )
    elif config_warning_count:
        config_gate = ReadinessGateItem(
            key="config_readiness",
            label="生产配置 readiness",
            status="warn",
            count=config_warning_count,
            warn_threshold=0,
            block_threshold=config_warning_count,
            message="配置 readiness 快照存在警告项，灰度前需确认环境与占位配置。",
        )
    else:
        config_gate = ReadinessGateItem(
            key="config_readiness",
            label="生产配置 readiness",
            status="pass",
            count=0,
            warn_threshold=0,
            block_threshold=0,
            message="配置 readiness 快照未发现阻断或警告。",
        )

    gate_items = [
        config_gate,
        _gate_item(
            key="unsafe_feedback",
            label="未处理 unsafe AI 反馈",
            count=unsafe_open_count,
            warn_threshold=0,
            block_threshold=0,
            ok_message="未发现待处理 unsafe 反馈。",
            warn_message="存在待处理 unsafe 反馈，应暂停相关入口并完成复核。",
            block_message="存在待处理 unsafe 反馈，应暂停相关入口并完成复核。",
        ),
        _gate_item(
            key="refresh_reuse",
            label="Refresh Token 复用/撤销异常",
            count=refresh_reuse_count,
            warn_threshold=0,
            block_threshold=0,
            ok_message="未发现 refresh 复用或撤销异常。",
            warn_message="出现 refresh 复用或撤销异常，应检查会话安全。",
            block_message="出现 refresh 复用或撤销异常，应检查会话安全。",
        ),
        _gate_item(
            key="ai_errors",
            label="AI 调用错误",
            count=telemetry.error_count,
            warn_threshold=0,
            block_threshold=5,
            ok_message="最近 AI 样本未见结构化错误。",
            warn_message="最近 AI 样本存在错误，灰度前需观察趋势。",
            block_message="最近 AI 错误较多，应暂停放量并排查模型链路。",
        ),
        _gate_item(
            key="feedback_followup",
            label="识别/知识纠错待处理",
            count=feedback_followup_count,
            warn_threshold=0,
            block_threshold=10,
            ok_message="无待处理识别纠错或知识缺口反馈。",
            warn_message="存在待处理识别纠错或知识缺口反馈。",
            block_message="待处理纠错和知识缺口较多，应先完成运营复核。",
        ),
        _gate_item(
            key="auth_lockouts",
            label="OTP 限流/锁定",
            count=auth_lockout_count,
            warn_threshold=0,
            block_threshold=10,
            ok_message="最近未见 OTP 限流或锁定。",
            warn_message="存在 OTP 限流或锁定，需观察是否为攻击或测试噪声。",
            block_message="OTP 限流/锁定频繁，应暂停放量并检查防刷策略。",
        ),
        _gate_item(
            key="knowledge_coverage",
            label="知识库覆盖缺口",
            count=knowledge_gap_count + cloud_blocked_count,
            warn_threshold=0,
            block_threshold=10,
            ok_message="最近知识审计未显示明显覆盖缺口。",
            warn_message="最近存在知识覆盖缺口或云端阻断，应优先补规则或确认 fallback。",
            block_message="知识覆盖缺口较多，应暂停相关人群放量。",
        ),
        _gate_item(
            key="food_nutrition_review",
            label="食物营养来源审核",
            count=food_nutrition_problem_count,
            warn_threshold=0,
            block_threshold=20,
            ok_message="食物库营养来源、估算质量与复核状态已就绪。",
            warn_message="存在未复核或缺少来源的食物营养数据，灰度前应优先补齐高频食物。",
            block_message="未复核或缺少来源的食物营养数据较多，应暂停扩大灰度并完成知识库审核。",
        ),
        _gate_item(
            key="offline_sync_health",
            label="离线同步失败/冲突",
            count=offline_sync_problem_count,
            warn_threshold=0,
            block_threshold=20,
            ok_message="服务端最近未见 FAILED/CONFLICT 同步状态。",
            warn_message="存在离线同步失败或冲突，灰度前需引导用户重试或处理冲突。",
            block_message="离线同步失败/冲突较多，应暂停放量并检查同步协议。",
        ),
        _gate_item(
            key="intake_review_backlog",
            label="候选复核待处理",
            count=intake_review_backlog_count,
            warn_threshold=0,
            block_threshold=20,
            ok_message="最近聚合快照未见待复核候选积压。",
            warn_message="存在待复核候选，应确认低置信度和风险候选不会自动入库。",
            block_message="待复核候选积压较多，应暂停放量并优化确认流程。",
        ),
        _gate_item(
            key="admin_denied",
            label="后台拒绝访问",
            count=admin_denied_count,
            warn_threshold=0,
            block_threshold=10,
            ok_message="最近未见后台拒绝访问。",
            warn_message="存在后台拒绝访问，需确认是否为权限配置或异常尝试。",
            block_message="后台拒绝访问频繁，应检查管理员配置和访问来源。",
        ),
    ]

    blocker_count = sum(1 for item in gate_items if item.status == "block")
    warning_count = sum(1 for item in gate_items if item.status == "warn")
    status_value = "red" if blocker_count else "yellow" if warning_count else "green"
    severity_rank = {"block": 2, "warn": 1, "pass": 0}
    action_items = sorted(
        [item for item in gate_items if item.status in {"block", "warn"}],
        key=lambda item: (-severity_rank.get(item.status, 0), -item.count),
    )[:3]

    return ReleaseReadinessSummary(
        status=status_value,
        generated_at=datetime.now(timezone.utc),
        window_limit=limit,
        blocker_count=blocker_count,
        warning_count=warning_count,
        gate_items=gate_items,
        action_items=action_items,
        signals={
            "unsafe_open_feedback": unsafe_open_count,
            "feedback_followup_open": feedback_followup_count,
            "ai_error_count": telemetry.error_count,
            "auth_lockout_count": auth_lockout_count,
            "refresh_reuse_count": refresh_reuse_count,
            "admin_denied_count": admin_denied_count,
            "knowledge_gap_count": knowledge_gap_count,
            "cloud_blocked_count": cloud_blocked_count,
            "food_nutrition_problem_count": food_nutrition_problem_count,
            "food_nutrition_missing_provenance_count": food_nutrition_missing_provenance_count,
            "food_nutrition_unreviewed_count": food_nutrition_unreviewed_count,
            "offline_sync_problem_count": offline_sync_problem_count,
            "offline_sync_failed_count": offline_sync_failed_count,
            "offline_sync_conflict_count": offline_sync_conflict_count,
            "intake_review_snapshot_count": intake_review_telemetry.snapshot_count,
            "intake_review_user_count": intake_review_telemetry.user_count,
            "intake_review_total_count": intake_review_telemetry.total_count,
            "intake_review_pending_count": intake_review_telemetry.pending_review_count,
            "intake_review_in_review_count": intake_review_telemetry.in_review_count,
            "intake_review_low_confidence_count": intake_review_telemetry.low_confidence_count,
            "intake_review_high_risk_count": intake_review_telemetry.high_risk_count,
            "intake_review_hard_block_count": intake_review_telemetry.hard_block_count,
            "intake_review_backlog_count": intake_review_backlog_count,
            "config_blocking_count": config_blocking_count,
            "config_warning_count": config_warning_count,
            "sampled_ai_messages": telemetry.sampled_messages,
            "sampled_security_events": len(security_rows),
            "sampled_knowledge_events": len(knowledge_rows),
            "sampled_feedback_events": len(feedback_rows),
            "sampled_food_items": len(food_rows),
            "sampled_offline_sync_problem_meals": len(meal_rows),
        },
        notes=[
            "Readiness 仅基于结构化审计与反馈计数，不包含原始健康文本、手机号、token、验证码或图片内容。",
            "配置 readiness gate 来自 settings.readiness_snapshot() 的脱敏快照，不包含 API keys、model IDs、数据库凭据或其他 secrets。",
            "食物营养来源 gate 只统计来源/质量/审核状态计数，不返回食物备注、用户输入或健康敏感内容。",
            "离线同步 gate 只统计 FAILED/CONFLICT 状态数量，不返回餐名、备注、图片、营养值或客户端原始草稿。",
            "候选复核 gate 只接收用户设备提交的聚合计数，不上传食物名、备注、健康文本、图片或候选草稿。",
            "red 表示不建议放量；yellow 表示可控内测但需运营复核；green 表示当前窗口未见阻断项。",
        ],
    )


def _is_admin_user(user: User) -> bool:
    role = getattr(user, "role", None)
    if role == UserRole.ADMIN or role == UserRole.ADMIN.value:
        return True
    phone_hash = hash_sensitive_value(user.phone)
    return bool(phone_hash and phone_hash in settings.admin_phone_hashes)


def _admin_user_item(row: User) -> AdminUserItem:
    return AdminUserItem(
        id=row.id,
        phone_hash=hash_sensitive_value(row.phone),
        nickname=row.nickname,
        role=getattr(row.role, "value", row.role) or UserRole.USER,
        subscription_plan=getattr(row.subscription_plan, "value", row.subscription_plan) or SubscriptionPlan.FREE,
        subscription_status=getattr(row.subscription_status, "value", row.subscription_status) or SubscriptionStatus.INACTIVE,
        subscription_updated_at=row.subscription_updated_at,
        is_active=row.is_active,
        is_verified=row.is_verified,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_login_at=row.last_login_at,
    )


def _build_user_query(
    *,
    limit: int,
    q: Optional[str] = None,
    role: Optional[UserRole] = None,
    subscription_plan: Optional[SubscriptionPlan] = None,
    subscription_status: Optional[SubscriptionStatus] = None,
):
    query = select(User)
    if role is not None:
        query = query.where(User.role == role)
    if subscription_plan is not None:
        query = query.where(User.subscription_plan == subscription_plan)
    if subscription_status is not None:
        query = query.where(User.subscription_status == subscription_status)

    normalized_query = q.strip() if q else None
    if normalized_query:
        search_term = f"%{normalized_query}%"
        query = query.where(
            or_(
                User.nickname.ilike(search_term),
                cast(User.id, String).ilike(search_term),
            )
        )

    return query.order_by(User.id.desc()).limit(limit)


def _safe_admin_search_metadata(q: Optional[str]) -> dict[str, object]:
    normalized_query = q.strip() if q else ""
    if not normalized_query:
        return {"q_present": False, "q_hash": None, "q_length": 0}
    return {
        "q_present": True,
        "q_hash": hash_sensitive_value(normalized_query),
        "q_length": len(normalized_query),
    }


def _apply_user_role(row: User, role: UserRole) -> None:
    row.role = role


def _apply_user_subscription(row: User, plan: SubscriptionPlan, status: SubscriptionStatus) -> None:
    row.subscription_plan = plan
    row.subscription_status = status
    row.subscription_updated_at = datetime.now(timezone.utc)


async def require_admin_user(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
) -> User:
    if not _is_admin_user(current_user):
        await audit_security_event(
            db,
            event_type="admin.access",
            event_status="denied",
            user_id=current_user.id,
            request=request,
            actor=current_user.phone,
            route_name="/api/admin",
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")

    return current_user


AdminUser = Annotated[User, Depends(require_admin_user)]


def _security_item(row: SecurityAuditLog) -> SecurityAuditItem:
    return SecurityAuditItem(
        id=row.id,
        user_id=row.user_id,
        event_type=row.event_type,
        event_status=row.event_status,
        route_name=row.route_name,
        actor_hash=row.actor_hash,
        ip_hash=row.ip_hash,
        user_agent_hash=row.user_agent_hash,
        session_id=row.session_id,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
    )


def _build_security_audit_query(
    *,
    limit: int,
    q: Optional[str] = None,
    event_status: Optional[str] = None,
):
    query = select(SecurityAuditLog)
    normalized_query = q.strip() if q else None
    if event_status:
        query = query.where(SecurityAuditLog.event_status == event_status)
    if normalized_query:
        search_term = f"%{normalized_query}%"
        query = query.where(
            or_(
                SecurityAuditLog.event_type.ilike(search_term),
                SecurityAuditLog.route_name.ilike(search_term),
                SecurityAuditLog.event_status.ilike(search_term),
            )
        )
    return query.order_by(SecurityAuditLog.created_at.desc(), SecurityAuditLog.id.desc()).limit(limit)


def _knowledge_item(row: KnowledgeAuditLog) -> KnowledgeAuditItem:
    return KnowledgeAuditItem(
        id=row.id,
        user_id=row.user_id,
        route_name=row.route_name,
        chat_session_id=row.chat_session_id,
        chat_message_id=row.chat_message_id,
        query_excerpt_hash=_hashed_or_passthrough(row.query_excerpt),
        origin=getattr(row.origin, "value", row.origin),
        fallback_status=getattr(row.fallback_status, "value", row.fallback_status),
        matched_disease_codes=row.matched_disease_codes_json or [],
        matched_food_codes=row.matched_food_codes_json or [],
        unmapped_conditions=_safe_list(row.unmapped_conditions_json),
        local_decision_level=getattr(row.local_decision_level, "value", row.local_decision_level),
        called_cloud=row.called_cloud,
        cloud_call_reason=row.cloud_call_reason,
        cloud_blocked_reason=row.cloud_blocked_reason,
        created_at=row.created_at,
    )


def _build_knowledge_audit_query(
    *,
    limit: int,
    q: Optional[str] = None,
    origin: Optional[KnowledgeOrigin] = None,
    fallback_status: Optional[FallbackStatus] = None,
    called_cloud: Optional[bool] = None,
):
    query = select(KnowledgeAuditLog)
    normalized_query = q.strip() if q else None
    if origin is not None:
        query = query.where(KnowledgeAuditLog.origin == origin)
    if fallback_status is not None:
        query = query.where(KnowledgeAuditLog.fallback_status == fallback_status)
    if called_cloud is not None:
        query = query.where(KnowledgeAuditLog.called_cloud.is_(called_cloud))
    if normalized_query:
        search_term = f"%{normalized_query}%"
        query = query.where(
            or_(
                KnowledgeAuditLog.route_name.ilike(search_term),
                KnowledgeAuditLog.cloud_call_reason.ilike(search_term),
                KnowledgeAuditLog.cloud_blocked_reason.ilike(search_term),
            )
        )
    return query.order_by(KnowledgeAuditLog.created_at.desc(), KnowledgeAuditLog.id.desc()).limit(limit)


def _hashed_or_passthrough(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = value.strip().lower()
    if len(normalized) == 64 and all(ch in "0123456789abcdef" for ch in normalized):
        return normalized
    return hash_sensitive_value(value)


def _feedback_item(row: AIFeedback) -> FeedbackItem:
    return FeedbackItem(
        id=row.id,
        user_id=row.user_id,
        session_id=row.session_id,
        message_id=row.message_id,
        app_message_id=row.app_message_id,
        feedback_type=getattr(row.feedback_type, "value", row.feedback_type),
        rating=row.rating,
        tags=row.tags_json or [],
        status=getattr(row.status, "value", row.status),
        has_correction=bool(row.correction_text_hash),
        correction_text_hash=row.correction_text_hash,
        metadata_json=None,
        metadata_keys=_metadata_keys(row.metadata_json),
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
    )


def _is_knowledge_backlog_audit(row: KnowledgeAuditLog) -> bool:
    fallback_status = _enum_value(row.fallback_status)
    return (
        fallback_status in KNOWLEDGE_BACKLOG_FALLBACK_STATUSES
        or bool(row.unmapped_conditions_json)
        or bool(row.cloud_blocked_reason)
    )


def _knowledge_backlog_feedback_item(row: AIFeedback) -> KnowledgeBacklogItem:
    return KnowledgeBacklogItem(
        source="feedback",
        id=row.id,
        user_id=row.user_id,
        feedback_type=_enum_value(row.feedback_type),
        status=_enum_value(row.status),
        tags=_safe_list(row.tags_json),
        metadata_keys=_metadata_keys(row.metadata_json),
        has_correction=bool(row.correction_text_hash),
        correction_text_hash=row.correction_text_hash,
        created_at=row.created_at or datetime.now(timezone.utc),
    )


def _knowledge_backlog_audit_item(row: KnowledgeAuditLog) -> KnowledgeBacklogItem:
    return KnowledgeBacklogItem(
        source="knowledge_audit",
        id=row.id,
        user_id=row.user_id,
        route_name=row.route_name,
        query_excerpt_hash=_hashed_or_passthrough(row.query_excerpt),
        origin=_enum_value(row.origin),
        fallback_status=_enum_value(row.fallback_status),
        matched_disease_codes=_safe_list(row.matched_disease_codes_json),
        matched_food_codes=_safe_list(row.matched_food_codes_json),
        unmapped_condition_hashes=_safe_list(row.unmapped_conditions_json),
        called_cloud=row.called_cloud,
        cloud_call_reason_code=_safe_reason_code(row.cloud_call_reason),
        cloud_blocked_reason_code=_safe_reason_code(row.cloud_blocked_reason),
        created_at=row.created_at or datetime.now(timezone.utc),
    )


def _build_knowledge_backlog_summary(
    *,
    feedback_rows: list[AIFeedback],
    knowledge_rows: list[KnowledgeAuditLog],
    food_rows: Optional[list[FoodItem]] = None,
    limit: int,
    generated_at: Optional[datetime] = None,
) -> KnowledgeBacklogSummary:
    safe_limit = max(1, min(limit, 200))
    gap_rows = [row for row in knowledge_rows if _is_knowledge_backlog_audit(row)]

    feedback_type_counts = Counter(_enum_value(row.feedback_type) for row in feedback_rows)
    feedback_status_counts = Counter(_enum_value(row.status) for row in feedback_rows)
    tag_counts = Counter(tag for row in feedback_rows for tag in _safe_list(row.tags_json))
    correction_hash_counts = Counter(row.correction_text_hash for row in feedback_rows if row.correction_text_hash)

    fallback_status_counts = Counter(_enum_value(row.fallback_status) for row in gap_rows)
    cloud_call_reason_counts = Counter(
        _safe_reason_code(row.cloud_call_reason) for row in gap_rows if _safe_reason_code(row.cloud_call_reason)
    )
    cloud_blocked_reason_counts = Counter(
        _safe_reason_code(row.cloud_blocked_reason) for row in gap_rows if _safe_reason_code(row.cloud_blocked_reason)
    )
    matched_disease_counts = Counter(
        code for row in gap_rows for code in _safe_list(row.matched_disease_codes_json)
    )
    matched_food_counts = Counter(code for row in gap_rows for code in _safe_list(row.matched_food_codes_json))
    unmapped_condition_counts = Counter(
        code for row in gap_rows for code in _safe_list(row.unmapped_conditions_json)
    )

    food_rows = food_rows or []
    food_source_counts = Counter(
        str(row.nutrition_source_code or "unspecified") for row in food_rows
    )
    food_quality_counts = Counter(
        str(row.nutrition_estimate_quality or "unspecified") for row in food_rows
    )
    food_review_status_counts = Counter(
        str(row.nutrition_review_status or "unspecified") for row in food_rows
    )
    food_unreviewed_count = sum(
        1
        for row in food_rows
        if (row.nutrition_review_status or "").strip().upper() != "REVIEWED"
        or not (row.nutrition_source_code or "").strip()
        or not (row.nutrition_source_detail or "").strip()
    )

    recent_items = [
        *[_knowledge_backlog_feedback_item(row) for row in feedback_rows],
        *[_knowledge_backlog_audit_item(row) for row in gap_rows],
    ]
    recent_items.sort(key=lambda item: (item.created_at, item.source, item.id), reverse=True)

    notes = [
        "仅返回哈希、枚举、标签、metadata key 和聚合计数，不返回反馈正文、聊天正文、原始健康档案或图片内容。",
        "知识改进 backlog 用于定位 seed/rule 覆盖缺口；规则上线前仍需人工复核来源和免责声明。",
    ]
    if any(_enum_value(row.status) == AIFeedbackStatus.OPEN.value for row in feedback_rows):
        notes.append("存在未处理的知识缺口或纠错反馈，扩大灰度前建议先完成分流。")
    if gap_rows:
        notes.append("存在本地知识未覆盖、部分覆盖或本地阻断样本，应优先补充高频食物/病种组合。")
    if food_unreviewed_count:
        notes.append("存在未复核或缺少营养来源的食物条目，灰度前应先补齐 source 和 review 状态。")

    return KnowledgeBacklogSummary(
        generated_at=generated_at or datetime.now(timezone.utc),
        window_limit=safe_limit,
        feedback_followup_count=len(feedback_rows),
        feedback_open_count=sum(
            1 for row in feedback_rows if _enum_value(row.status) == AIFeedbackStatus.OPEN.value
        ),
        knowledge_audit_gap_count=len(gap_rows),
        has_correction_count=sum(1 for row in feedback_rows if bool(row.correction_text_hash)),
        feedback_type_counts=_counter_dict(feedback_type_counts),
        feedback_status_counts=_counter_dict(feedback_status_counts),
        tag_counts=_counter_dict(tag_counts),
        correction_hash_counts=_counter_dict(correction_hash_counts),
        fallback_status_counts=_counter_dict(fallback_status_counts),
        cloud_call_reason_counts=_counter_dict(cloud_call_reason_counts),
        cloud_blocked_reason_counts=_counter_dict(cloud_blocked_reason_counts),
        matched_disease_counts=_counter_dict(matched_disease_counts),
        matched_food_counts=_counter_dict(matched_food_counts),
        unmapped_condition_counts=_counter_dict(unmapped_condition_counts),
        food_nutrition_source_counts=_counter_dict(food_source_counts),
        food_nutrition_quality_counts=_counter_dict(food_quality_counts),
        food_nutrition_review_status_counts=_counter_dict(food_review_status_counts),
        food_nutrition_unreviewed_count=food_unreviewed_count,
        recent_items=recent_items[:safe_limit],
        notes=notes,
    )


def _build_feedback_query(
    *,
    limit: int,
    status: Optional[AIFeedbackStatus] = None,
    feedback_type: Optional[AIFeedbackType] = None,
):
    query = select(AIFeedback)
    if status is not None:
        query = query.where(AIFeedback.status == status)
    if feedback_type is not None:
        query = query.where(AIFeedback.feedback_type == feedback_type)
    return query.order_by(AIFeedback.created_at.desc(), AIFeedback.id.desc()).limit(limit)


def _feedback_status_transition_rejection(
    row: AIFeedback,
    target_status: AIFeedbackStatus,
) -> Optional[str]:
    current_status = _enum_value(row.status)
    target_status_value = _enum_value(target_status)
    feedback_type = _enum_value(row.feedback_type)

    if (
        feedback_type == AIFeedbackType.UNSAFE.value
        and current_status != AIFeedbackStatus.REVIEWED.value
        and target_status_value == AIFeedbackStatus.CLOSED.value
    ):
        return "unsafe_requires_review_before_close"
    return None


def _apply_feedback_status(row: AIFeedback, status_value: AIFeedbackStatus) -> None:
    row.status = status_value
    row.reviewed_at = datetime.now(timezone.utc) if status_value != AIFeedbackStatus.OPEN else None


@router.get("/audit/security", response_model=list[SecurityAuditItem])
async def list_security_audit(
    request: Request,
    admin_user: AdminUser,
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None, description="按事件类型、路由或状态关键词筛选"),
    event_status: Optional[str] = Query(None, description="按事件状态精确筛选"),
):
    result = await db.execute(_build_security_audit_query(limit=limit, q=q, event_status=event_status))
    rows = list(result.scalars().all())
    await audit_security_event(
        db,
        event_type="admin.audit.security.list",
        event_status="success",
        user_id=admin_user.id,
        request=request,
        actor=admin_user.phone,
        route_name="/api/admin/audit/security",
        metadata={
            "limit": limit,
            "returned": len(rows),
            **_safe_admin_search_metadata(q),
            "event_status": event_status,
        },
    )
    return [_security_item(row) for row in rows]


@router.get("/audit/knowledge", response_model=list[KnowledgeAuditItem])
async def list_knowledge_audit(
    request: Request,
    admin_user: AdminUser,
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None, description="按路由或结构化云端原因关键词筛选，不搜索原始健康文本"),
    origin: Optional[KnowledgeOrigin] = Query(None),
    fallback_status: Optional[FallbackStatus] = Query(None),
    called_cloud: Optional[bool] = Query(None),
):
    result = await db.execute(
        _build_knowledge_audit_query(
            limit=limit,
            q=q,
            origin=origin,
            fallback_status=fallback_status,
            called_cloud=called_cloud,
        )
    )
    rows = list(result.scalars().all())
    await audit_security_event(
        db,
        event_type="admin.audit.knowledge.list",
        event_status="success",
        user_id=admin_user.id,
        request=request,
        actor=admin_user.phone,
        route_name="/api/admin/audit/knowledge",
        metadata={
            "limit": limit,
            "returned": len(rows),
            **_safe_admin_search_metadata(q),
            "origin": origin.value if origin else None,
            "fallback_status": fallback_status.value if fallback_status else None,
            "called_cloud": called_cloud,
        },
    )
    return [_knowledge_item(row) for row in rows]


@router.get("/knowledge/backlog", response_model=KnowledgeBacklogSummary)
async def get_knowledge_backlog(
    request: Request,
    admin_user: AdminUser,
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
    include_closed: bool = Query(False, description="是否包含已关闭的纠错/知识缺口反馈"),
):
    feedback_query = select(AIFeedback).where(
        AIFeedback.feedback_type.in_(list(KNOWLEDGE_BACKLOG_FEEDBACK_TYPES))
    )
    if not include_closed:
        feedback_query = feedback_query.where(AIFeedback.status == AIFeedbackStatus.OPEN)
    feedback_result = await db.execute(
        feedback_query
        .order_by(AIFeedback.created_at.desc(), AIFeedback.id.desc())
        .limit(min(600, max(limit * 4, limit)))
    )
    knowledge_result = await db.execute(
        select(KnowledgeAuditLog)
        .order_by(KnowledgeAuditLog.created_at.desc(), KnowledgeAuditLog.id.desc())
        .limit(min(600, max(limit * 4, limit)))
    )
    food_result = await db.execute(
        select(FoodItem).where(FoodItem.is_enabled.is_(True)).order_by(FoodItem.food_code.asc())
    )
    feedback_rows = list(feedback_result.scalars().all())
    knowledge_rows = list(knowledge_result.scalars().all())
    food_rows = list(food_result.scalars().all())
    summary = _build_knowledge_backlog_summary(
        feedback_rows=feedback_rows,
        knowledge_rows=knowledge_rows,
        food_rows=food_rows,
        limit=limit,
    )

    await audit_security_event(
        db,
        event_type="admin.knowledge.backlog.list",
        event_status="success",
        user_id=admin_user.id,
        request=request,
        actor=admin_user.phone,
        route_name="/api/admin/knowledge/backlog",
        metadata={
            "limit": limit,
            "include_closed": include_closed,
            "feedback_followup_count": summary.feedback_followup_count,
            "knowledge_audit_gap_count": summary.knowledge_audit_gap_count,
            "food_nutrition_unreviewed_count": summary.food_nutrition_unreviewed_count,
            "returned": len(summary.recent_items),
        },
    )
    return summary


@router.get("/feedback", response_model=list[FeedbackItem])
async def list_feedback(
    request: Request,
    admin_user: AdminUser,
    db: DbSession,
    status: Optional[AIFeedbackStatus] = Query(None),
    feedback_type: Optional[AIFeedbackType] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    result = await db.execute(
        _build_feedback_query(limit=limit, status=status, feedback_type=feedback_type)
    )
    rows = list(result.scalars().all())
    await audit_security_event(
        db,
        event_type="admin.feedback.list",
        event_status="success",
        user_id=admin_user.id,
        request=request,
        actor=admin_user.phone,
        route_name="/api/admin/feedback",
        metadata={
            "limit": limit,
            "returned": len(rows),
            "status": status.value if status else None,
            "feedback_type": feedback_type.value if feedback_type else None,
        },
    )
    return [_feedback_item(row) for row in rows]


@router.patch("/feedback/{feedback_id}/status", response_model=FeedbackItem)
async def update_feedback_status(
    feedback_id: int,
    data: FeedbackStatusUpdate,
    request: Request,
    admin_user: AdminUser,
    db: DbSession,
):
    result = await db.execute(select(AIFeedback).where(AIFeedback.id == feedback_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")

    rejection_reason = _feedback_status_transition_rejection(row, data.status)
    if rejection_reason:
        await audit_security_event(
            db,
            event_type="admin.feedback.status_update",
            event_status="rejected",
            user_id=admin_user.id,
            request=request,
            actor=admin_user.phone,
            route_name="/api/admin/feedback/{feedback_id}/status",
            metadata={
                "feedback_id": feedback_id,
                "current_status": _enum_value(row.status),
                "requested_status": data.status.value,
                "feedback_type": _enum_value(row.feedback_type),
                "reason": rejection_reason,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="unsafe 反馈需先标记为已审阅后才能关闭",
        )

    _apply_feedback_status(row, data.status)
    await db.flush()
    await db.refresh(row)

    await audit_security_event(
        db,
        event_type="admin.feedback.status_update",
        event_status="success",
        user_id=admin_user.id,
        request=request,
        actor=admin_user.phone,
        route_name="/api/admin/feedback/{feedback_id}/status",
        metadata={
            "feedback_id": feedback_id,
            "status": data.status.value,
            "feedback_type": getattr(row.feedback_type, "value", row.feedback_type),
        },
    )

    return _feedback_item(row)


@router.get("/users", response_model=list[AdminUserItem])
async def list_users(
    request: Request,
    admin_user: AdminUser,
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None, description="按昵称或用户 ID 筛选"),
    role: Optional[UserRole] = Query(None),
    subscription_plan: Optional[SubscriptionPlan] = Query(None),
    subscription_status: Optional[SubscriptionStatus] = Query(None),
):
    result = await db.execute(
        _build_user_query(
            limit=limit,
            q=q,
            role=role,
            subscription_plan=subscription_plan,
            subscription_status=subscription_status,
        )
    )
    rows = list(result.scalars().all())
    await audit_security_event(
        db,
        event_type="admin.users.list",
        event_status="success",
        user_id=admin_user.id,
        request=request,
        actor=admin_user.phone,
        route_name="/api/admin/users",
        metadata={
            "limit": limit,
            "returned": len(rows),
            **_safe_admin_search_metadata(q),
            "role": role.value if role else None,
            "subscription_plan": subscription_plan.value if subscription_plan else None,
            "subscription_status": subscription_status.value if subscription_status else None,
        },
    )
    return [_admin_user_item(row) for row in rows]


@router.patch("/users/{user_id}/role", response_model=AdminUserItem)
async def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    request: Request,
    admin_user: AdminUser,
    db: DbSession,
):
    result = await db.execute(select(User).where(User.id == user_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    _apply_user_role(row, data.role)
    await db.flush()
    await db.refresh(row)

    await audit_security_event(
        db,
        event_type="admin.user.role_update",
        event_status="success",
        user_id=admin_user.id,
        request=request,
        actor=admin_user.phone,
        route_name="/api/admin/users/{user_id}/role",
        metadata={
            "target_user_id": user_id,
            "role": data.role.value,
            "target_phone_hash": hash_sensitive_value(row.phone),
        },
    )
    return _admin_user_item(row)


@router.patch("/users/{user_id}/subscription", response_model=AdminUserItem)
async def update_user_subscription(
    user_id: int,
    data: UserSubscriptionUpdate,
    request: Request,
    admin_user: AdminUser,
    db: DbSession,
):
    result = await db.execute(select(User).where(User.id == user_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    _apply_user_subscription(row, data.plan, data.status)
    await db.flush()
    await db.refresh(row)

    await audit_security_event(
        db,
        event_type="admin.user.subscription_update",
        event_status="success",
        user_id=admin_user.id,
        request=request,
        actor=admin_user.phone,
        route_name="/api/admin/users/{user_id}/subscription",
        metadata={
            "target_user_id": user_id,
            "plan": data.plan.value,
            "status": data.status.value,
            "target_phone_hash": hash_sensitive_value(row.phone),
        },
    )
    return _admin_user_item(row)


@router.get("/activation/metrics", response_model=ActivationMetricsSummary)
async def get_activation_metrics(
    request: Request,
    admin_user: AdminUser,
    db: DbSession,
    window_days: int = Query(7, ge=1, le=90),
):
    start_at = _window_start(window_days)
    start_date = start_at.date()

    users_result = await db.execute(select(User))
    meals_result = await db.execute(select(Meal).where(Meal.created_at >= start_at))
    sessions_result = await db.execute(select(ChatSession).where(ChatSession.created_at >= start_at))
    messages_result = await db.execute(
        select(ChatMessage).where(ChatMessage.role == MessageRole.ASSISTANT, ChatMessage.created_at >= start_at)
    )
    feedback_result = await db.execute(select(AIFeedback))
    security_result = await db.execute(select(SecurityAuditLog).where(SecurityAuditLog.created_at >= start_at))
    metrics_result = await db.execute(select(HealthMetric).where(HealthMetric.created_at >= start_at))
    intake_review_result = await db.execute(
        select(IntakeReviewTelemetrySnapshot).where(IntakeReviewTelemetrySnapshot.created_at >= start_at)
    )

    summary = _build_activation_metrics_summary(
        users=list(users_result.scalars().all()),
        meals=list(meals_result.scalars().all()),
        chat_sessions=list(sessions_result.scalars().all()),
        assistant_messages=list(messages_result.scalars().all()),
        feedback_rows=list(feedback_result.scalars().all()),
        security_rows=list(security_result.scalars().all()),
        health_metrics=list(metrics_result.scalars().all()),
        window_days=window_days,
        intake_review_rows=list(intake_review_result.scalars().all()),
    )

    await audit_security_event(
        db,
        event_type="admin.activation.metrics.list",
        event_status="success",
        user_id=admin_user.id,
        request=request,
        actor=admin_user.phone,
        route_name="/api/admin/activation/metrics",
        metadata={
            "window_days": summary.window_days,
            "total_users": summary.total_users,
            "meal_users": summary.meal_users,
            "chat_users": summary.chat_users,
            "unsafe_open_feedback_count": summary.unsafe_open_feedback_count,
            "intake_review_pending_count": summary.intake_review_telemetry.pending_review_count,
            "intake_review_high_risk_count": summary.intake_review_telemetry.high_risk_count,
        },
    )

    return summary


@router.get("/commercialization/summary", response_model=CommercializationSummary)
async def get_commercialization_summary(
    request: Request,
    admin_user: AdminUser,
    db: DbSession,
    window_days: int = Query(30, ge=1, le=90),
):
    now = datetime.now(timezone.utc)
    start_at = _window_start(window_days)
    day_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    month_end = (
        datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        if now.month == 12
        else datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    )

    users_result = await db.execute(select(User))
    billing_events_result = await db.execute(
        select(SecurityAuditLog).where(
            SecurityAuditLog.created_at >= start_at,
            SecurityAuditLog.event_type.like("billing.%"),
        )
    )
    ai_usage_result = await db.execute(
        select(ChatSession.user_id, func.count(ChatMessage.id))
        .select_from(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(
            ChatMessage.role == MessageRole.ASSISTANT,
            ChatMessage.created_at >= day_start,
            ChatMessage.created_at < day_end,
        )
        .group_by(ChatSession.user_id)
    )
    photo_usage_result = await db.execute(
        select(Meal.user_id, func.count(Meal.id))
        .where(
            Meal.source == MealSource.PHOTO.value,
            Meal.created_at >= month_start,
            Meal.created_at < month_end,
        )
        .group_by(Meal.user_id)
    )

    ai_usage_by_user = {
        int(user_id): int(count or 0)
        for user_id, count in ai_usage_result.all()
        if user_id is not None
    }
    photo_usage_by_user = {
        int(user_id): int(count or 0)
        for user_id, count in photo_usage_result.all()
        if user_id is not None
    }
    summary = _build_commercialization_summary(
        users=list(users_result.scalars().all()),
        billing_events=list(billing_events_result.scalars().all()),
        ai_chat_usage_by_user=ai_usage_by_user,
        photo_usage_by_user=photo_usage_by_user,
        window_days=window_days,
        billing_provider=settings.billing_provider,
    )

    await audit_security_event(
        db,
        event_type="admin.commercialization.summary.list",
        event_status="success",
        user_id=admin_user.id,
        request=request,
        actor=admin_user.phone,
        route_name="/api/admin/commercialization/summary",
        metadata={
            "window_days": summary.window_days,
            "total_users": summary.total_users,
            "active_paid_users": summary.active_paid_users,
            "checkout_event_count": summary.checkout_event_count,
            "cancel_event_count": summary.cancel_event_count,
            "provider": summary.billing_provider,
        },
    )

    return summary


@router.get("/ai/telemetry", response_model=AITelemetrySummary)
async def get_ai_telemetry(
    request: Request,
    admin_user: AdminUser,
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
):
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.role == MessageRole.ASSISTANT)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    summary = _build_ai_telemetry_summary(rows, limit=limit)

    await audit_security_event(
        db,
        event_type="admin.ai.telemetry.list",
        event_status="success",
        user_id=admin_user.id,
        request=request,
        actor=admin_user.phone,
        route_name="/api/admin/ai/telemetry",
        metadata={
            "limit": limit,
            "returned": len(rows),
            "telemetry_sample_count": summary.telemetry_sample_count,
            "cloud_call_count": summary.cloud_call_count,
        },
    )

    return summary


@router.get("/release/readiness", response_model=ReleaseReadinessSummary)
async def get_release_readiness(
    request: Request,
    admin_user: AdminUser,
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
):
    security_result = await db.execute(
        select(SecurityAuditLog)
        .order_by(SecurityAuditLog.created_at.desc(), SecurityAuditLog.id.desc())
        .limit(limit)
    )
    knowledge_result = await db.execute(
        select(KnowledgeAuditLog)
        .order_by(KnowledgeAuditLog.created_at.desc(), KnowledgeAuditLog.id.desc())
        .limit(limit)
    )
    feedback_result = await db.execute(
        select(AIFeedback)
        .order_by(AIFeedback.created_at.desc(), AIFeedback.id.desc())
        .limit(limit)
    )
    telemetry_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.role == MessageRole.ASSISTANT)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    )
    food_result = await db.execute(
        select(FoodItem)
        .where(FoodItem.is_enabled.is_(True))
        .order_by(FoodItem.id.desc())
    )
    meal_sync_result = await db.execute(
        select(Meal)
        .where(Meal.sync_status.in_([SyncStatus.FAILED, SyncStatus.CONFLICT]))
        .order_by(Meal.updated_at.desc(), Meal.id.desc())
        .limit(limit)
    )
    intake_review_result = await db.execute(
        select(IntakeReviewTelemetrySnapshot)
        .order_by(IntakeReviewTelemetrySnapshot.generated_at.desc(), IntakeReviewTelemetrySnapshot.id.desc())
        .limit(limit)
    )

    security_rows = list(security_result.scalars().all())
    knowledge_rows = list(knowledge_result.scalars().all())
    feedback_rows = list(feedback_result.scalars().all())
    food_rows = list(food_result.scalars().all())
    meal_rows = list(meal_sync_result.scalars().all())
    intake_review_telemetry = _build_intake_review_telemetry_aggregate(list(intake_review_result.scalars().all()))
    telemetry = _build_ai_telemetry_summary(list(telemetry_result.scalars().all()), limit=limit)
    summary = _build_release_readiness_summary(
        security_rows=security_rows,
        knowledge_rows=knowledge_rows,
        feedback_rows=feedback_rows,
        food_rows=food_rows,
        meal_rows=meal_rows,
        intake_review_telemetry=intake_review_telemetry,
        telemetry=telemetry,
        limit=limit,
        config_snapshot=settings.readiness_snapshot(),
    )

    await audit_security_event(
        db,
        event_type="admin.release.readiness.list",
        event_status="success",
        user_id=admin_user.id,
        request=request,
        actor=admin_user.phone,
        route_name="/api/admin/release/readiness",
        metadata={
            "limit": limit,
            "status": summary.status,
            "blocker_count": summary.blocker_count,
            "warning_count": summary.warning_count,
            "food_nutrition_unreviewed_count": summary.signals.get("food_nutrition_unreviewed_count", 0),
            "food_nutrition_missing_provenance_count": summary.signals.get("food_nutrition_missing_provenance_count", 0),
            "offline_sync_problem_count": summary.signals.get("offline_sync_problem_count", 0),
            "intake_review_backlog_count": summary.signals.get("intake_review_backlog_count", 0),
            "intake_review_high_risk_count": summary.signals.get("intake_review_high_risk_count", 0),
        },
    )

    return summary
