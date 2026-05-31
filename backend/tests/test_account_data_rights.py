from datetime import datetime, timedelta, timezone
import json

from app.api.routes import account as account_route
from app.models.security import DeviceSession
from app.models.user import SubscriptionPlan, SubscriptionStatus, User, UserRole


def test_account_state_export_includes_consent_and_subscription_without_secrets() -> None:
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    user = User(
        id=7,
        phone="13800138000",
        password_hash="super-secret-password-hash",
        role=UserRole.COACH,
        subscription_plan=SubscriptionPlan.PRO,
        subscription_status=SubscriptionStatus.ACTIVE,
        subscription_updated_at=now,
        consent_version="2026-05-30",
        consent_accepted_at=now,
        consent_terms_accepted=True,
        consent_privacy_accepted=True,
        consent_ai_use_accepted=True,
        consent_health_disclaimer_accepted=True,
        is_active=True,
        is_verified=True,
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )

    exported = account_route._export_account_state(user)
    serialized = json.dumps(exported, ensure_ascii=False)

    assert exported["role"] == "COACH"
    assert exported["subscription_plan"] == "PRO"
    assert exported["subscription_status"] == "active"
    assert exported["consent_version"] == "2026-05-30"
    assert exported["consents"] == {
        "terms": True,
        "privacy": True,
        "ai_use": True,
        "health_disclaimer": True,
    }
    assert "password" not in serialized.lower()
    assert "super-secret-password-hash" not in serialized
    assert "token" in exported["retention_note"]


def test_device_session_export_omits_token_and_network_hash_material() -> None:
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    session = DeviceSession(
        id=3,
        user_id=7,
        session_id="sid-visible-to-user",
        refresh_jti_hash="refresh-jti-secret-hash",
        device_label="Chrome on Windows",
        user_agent_hash="ua-secret-hash",
        ip_hash="ip-secret-hash",
        is_current=False,
        expires_at=now + timedelta(days=7),
        revoked_at=now,
        revoke_reason="user_revocation",
        created_at=now,
        last_seen_at=now,
    )

    exported = account_route._device_session_export_item(session)
    serialized = json.dumps(exported, ensure_ascii=False)

    assert exported["session_id"] == "sid-visible-to-user"
    assert exported["device_label"] == "Chrome on Windows"
    assert exported["is_current"] is False
    assert exported["is_revoked"] is True
    assert exported["revoke_reason"] == "user_revocation"
    assert "refresh-jti-secret-hash" not in serialized
    assert "ua-secret-hash" not in serialized
    assert "ip-secret-hash" not in serialized
    assert "token" not in serialized.lower()
