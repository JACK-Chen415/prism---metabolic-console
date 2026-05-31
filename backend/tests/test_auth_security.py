import pytest
from pydantic import ValidationError
from datetime import datetime, timedelta, timezone
import inspect
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_token_payload, get_current_user, get_db
from app.core import security as security_core
from app.api.routes import auth as auth_route
from app.core.security import decode_token, get_password_hash
from app.models.security import DeviceSession
from app.schemas import user as user_schema
from app.models.user import SubscriptionPlan, SubscriptionStatus, User, UserRole
from app.services.verification_service import OTPDispatchResult
from app.services.auth_security import (
    assert_access_session_active,
    audit_security_event,
    create_session_token_pair,
    revoke_all_device_sessions,
    revoke_device_session,
    rotate_refresh_session,
)


class FakeSession:
    def __init__(self):
        self.added = []
        self.flush_count = 0

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flush_count += 1
        return None

    async def refresh(self, item):
        if isinstance(item, User):
            item.id = item.id or 42
            item.is_active = True if item.is_active is None else item.is_active
            item.is_verified = False if item.is_verified is None else item.is_verified
            item.role = item.role or UserRole.USER
            item.subscription_plan = item.subscription_plan or SubscriptionPlan.FREE
            item.subscription_status = item.subscription_status or SubscriptionStatus.INACTIVE
            item.created_at = item.created_at or datetime.now(timezone.utc)
        return None


class FakeScalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeResult:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row

    def scalars(self):
        if isinstance(self.row, list):
            return FakeScalars(self.row)
        return FakeScalars([self.row] if self.row is not None else [])


class FakeQuerySession(FakeSession):
    def __init__(self, row):
        super().__init__()
        self.row = row
        self.execute_count = 0

    async def execute(self, statement):
        self.execute_count += 1
        return FakeResult(self.row)




def _auth_test_client(db, *, user=None, token_payload=None):
    app = FastAPI()
    app.include_router(auth_route.router, prefix="/api")

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    if user is not None:
        async def override_get_current_user():
            return user

        app.dependency_overrides[get_current_user] = override_get_current_user
    if token_payload is not None:
        async def override_get_current_token_payload():
            return token_payload

        app.dependency_overrides[get_current_token_payload] = override_get_current_token_payload
    return TestClient(app)

@pytest.mark.asyncio
async def test_create_session_token_pair_persists_session_and_adds_sid_jti():
    db = FakeSession()
    user = User(id=42, phone="13800138000", password_hash="hash")

    access_token, refresh_token, device_session = await create_session_token_pair(
        db,
        user=user,
        request=None,
    )

    access_payload = decode_token(access_token)
    refresh_payload = decode_token(refresh_token)

    assert isinstance(device_session, DeviceSession)
    assert db.added == [device_session]
    assert access_payload["sub"] == "42"
    assert refresh_payload["sub"] == "42"
    assert access_payload["sid"] == device_session.session_id
    assert refresh_payload["sid"] == device_session.session_id
    assert refresh_payload["jti"]
    assert device_session.refresh_jti_hash


def test_device_session_response_marks_current_and_omits_hashes():
    now = datetime.now(timezone.utc)
    session = DeviceSession(
        user_id=42,
        session_id="sid-current",
        refresh_jti_hash="secret-jti-hash",
        device_label="Chrome on Windows",
        user_agent_hash="raw-ua-hash",
        ip_hash="raw-ip-hash",
        expires_at=now + timedelta(days=7),
        created_at=now,
        last_seen_at=now,
    )

    response = auth_route._device_session_response(session, current_session_id="sid-current")
    serialized = response.model_dump_json()

    assert response.session_id == "sid-current"
    assert response.is_current is True
    assert response.is_revoked is False
    assert "secret-jti-hash" not in serialized
    assert "raw-ua-hash" not in serialized
    assert "raw-ip-hash" not in serialized


@pytest.mark.asyncio
async def test_revoke_device_session_marks_session_without_touching_tokens():
    now = datetime.now(timezone.utc)
    session = DeviceSession(
        user_id=42,
        session_id="sid-old",
        refresh_jti_hash="jti-hash",
        expires_at=now + timedelta(days=7),
        created_at=now,
        last_seen_at=now,
    )
    db = FakeQuerySession(session)

    revoked = await revoke_device_session(
        db,
        user_id=42,
        session_id="sid-old",
        reason="user_revocation",
    )

    assert revoked is True
    assert session.revoked_at is not None
    assert session.revoke_reason == "user_revocation"
    assert db.flush_count == 1


@pytest.mark.asyncio
async def test_revoke_all_device_sessions_marks_every_active_session_after_password_change():
    now = datetime.now(timezone.utc)
    sessions = [
        DeviceSession(
            user_id=42,
            session_id="sid-1",
            refresh_jti_hash="jti-1",
            expires_at=now + timedelta(days=7),
            created_at=now,
            last_seen_at=now,
        ),
        DeviceSession(
            user_id=42,
            session_id="sid-2",
            refresh_jti_hash="jti-2",
            expires_at=now + timedelta(days=7),
            created_at=now,
            last_seen_at=now,
        ),
    ]
    db = FakeQuerySession(sessions)

    revoked_count = await revoke_all_device_sessions(db, user_id=42, reason="password_change")

    assert revoked_count == 2
    assert {session.revoke_reason for session in sessions} == {"password_change"}
    assert all(session.revoked_at is not None for session in sessions)
    assert db.flush_count == 1


def test_register_schema_requires_all_compliance_consents():
    payload = {
        "phone": "13800138000",
        "password": "secret123",
        "terms_accepted": True,
        "privacy_accepted": True,
        "ai_use_accepted": True,
        "health_disclaimer_accepted": False,
        "consent_version": "2026-05-30",
    }

    with pytest.raises(ValidationError):
        user_schema.UserRegister(**payload)

    payload["health_disclaimer_accepted"] = True
    data = user_schema.UserRegister(**payload)

    assert data.consent_version == "2026-05-30"


def test_send_code_payload_exposes_debug_code_only_in_development(monkeypatch):
    result = OTPDispatchResult(
        success=True,
        expires_in=300,
        provider_name="dev",
        message="验证码已发送",
        debug_code="123456",
    )

    monkeypatch.setattr(auth_route, "settings", SimpleNamespace(is_development=True))
    development_payload = auth_route._send_code_response_payload(result)

    assert development_payload["debug_code"] == "123456"
    assert "123456" in development_payload["message"]

    monkeypatch.setattr(auth_route, "settings", SimpleNamespace(is_development=False))
    non_development_payload = auth_route._send_code_response_payload(result)

    assert "debug_code" not in non_development_payload
    assert "123456" not in non_development_payload["message"]


@pytest.mark.asyncio
async def test_access_session_active_rejects_revoked_or_missing_session():
    now = datetime.now(timezone.utc)
    revoked_session = DeviceSession(
        user_id=42,
        session_id="sid-revoked",
        refresh_jti_hash="jti-hash",
        expires_at=now + timedelta(days=7),
        revoked_at=now,
        created_at=now,
        last_seen_at=now,
    )

    with pytest.raises(ValueError, match="会话已失效"):
        await assert_access_session_active(
            FakeQuerySession(revoked_session),
            user_id=42,
            token_payload={"sid": "sid-revoked"},
        )

    with pytest.raises(ValueError, match="会话已失效"):
        await assert_access_session_active(
            FakeQuerySession(None),
            user_id=42,
            token_payload={"sid": "sid-missing"},
        )


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_device_session():
    now = datetime.now(timezone.utc)
    session = DeviceSession(
        user_id=42,
        session_id="sid-refresh",
        refresh_jti_hash="known-good-jti-hash",
        expires_at=now + timedelta(days=7),
        created_at=now,
        last_seen_at=now,
    )

    with pytest.raises(ValueError, match="已轮换或被撤销"):
        await rotate_refresh_session(
            FakeQuerySession(session),
            user=User(id=42, phone="13800138000", password_hash="hash"),
            refresh_payload={"sid": "sid-refresh", "jti": "replayed-jti"},
            request=None,
        )

    assert session.revoked_at is not None
    assert session.revoke_reason == "refresh_reuse_detected"



def test_register_route_requires_and_persists_compliance_consents():
    db = FakeQuerySession(None)
    client = _auth_test_client(db)
    payload = {
        "phone": "13800138000",
        "password": "secret123",
        "terms_accepted": True,
        "privacy_accepted": True,
        "ai_use_accepted": True,
        "health_disclaimer_accepted": False,
        "consent_version": "2026-05-30",
    }

    rejected = client.post("/api/auth/register", json=payload)

    assert rejected.status_code == 422

    payload["health_disclaimer_accepted"] = True
    accepted = client.post("/api/auth/register", json=payload)

    assert accepted.status_code == 201
    created_user = next(item for item in db.added if isinstance(item, User))
    assert created_user.consent_version == "2026-05-30"
    assert created_user.consent_accepted_at is not None
    assert created_user.consent_terms_accepted is True
    assert created_user.consent_privacy_accepted is True
    assert created_user.consent_ai_use_accepted is True
    assert created_user.consent_health_disclaimer_accepted is True


def test_change_password_route_revokes_existing_sessions():
    now = datetime.now(timezone.utc)
    user = User(id=42, phone="13800138000", password_hash=get_password_hash("oldpass"))
    sessions = [
        DeviceSession(
            user_id=42,
            session_id="sid-current",
            refresh_jti_hash="jti-current",
            expires_at=now + timedelta(days=7),
            created_at=now,
            last_seen_at=now,
        ),
        DeviceSession(
            user_id=42,
            session_id="sid-other",
            refresh_jti_hash="jti-other",
            expires_at=now + timedelta(days=7),
            created_at=now,
            last_seen_at=now,
        ),
    ]
    db = FakeQuerySession(sessions)
    client = _auth_test_client(db, user=user, token_payload={"sub": "42", "sid": "sid-current", "type": "access"})

    response = client.post("/api/auth/change-password", json={"old_password": "oldpass", "new_password": "newpass123"})

    assert response.status_code == 200
    assert all(session.revoked_at is not None for session in sessions)
    assert {session.revoke_reason for session in sessions} == {"password_change"}
    assert any(getattr(item, "event_type", None) == "auth.change_password" for item in db.added)


def test_auth_session_routes_are_audited_and_confirmed():
    source = inspect.getsource(auth_route)
    schema_source = inspect.getsource(user_schema)

    for required in [
        '@router.get("/sessions"',
        '@router.delete("/sessions/{session_id}"',
        'DeviceSessionResponse',
        'RevokeSessionRequest',
        'auth.session.list',
        'auth.session.revoke',
        'revoke_all_device_sessions',
        'auth.reset_password',
        'auth.change_password',
        'consent_version',
        'consent_document_count',
        '请使用退出登录关闭当前会话',
    ]:
        assert required in source

    assert "REVOKE_SESSION" in schema_source
    assert "terms_accepted" in schema_source
    assert "health_disclaimer_accepted" in schema_source


@pytest.mark.asyncio
async def test_audit_security_event_redacts_sensitive_metadata():
    db = FakeSession()

    await audit_security_event(
        db,
        event_type="security.test",
        event_status="success",
        metadata={
            "provider": "audit_only",
            "request_id": "req-safe-123",
            "password": "plain-secret",
            "refresh_token": "eyJhbGciOiJIUzI1NiJ9.very-secret-token-payload.signature",
            "raw_health_note": "用户说这里是一段不应进入审计日志的健康原文",
            "nested": {
                "api_key": "sk-prod-secret-value",
                "count": 2,
            },
            "sections": ["profile", "meals"],
        },
    )

    audit_log = db.added[-1]
    metadata = audit_log.metadata_json
    serialized = str(metadata)

    assert db.flush_count == 1
    assert metadata["provider"] == "audit_only"
    assert metadata["request_id"] == "req-safe-123"
    assert metadata["password"] == "[redacted]"
    assert metadata["refresh_token"] == "[redacted]"
    assert metadata["raw_health_note"] == "[redacted]"
    assert metadata["nested"]["api_key"] == "[redacted]"
    assert metadata["nested"]["count"] == 2
    assert metadata["sections"] == ["profile", "meals"]
    assert "plain-secret" not in serialized
    assert "very-secret-token" not in serialized
    assert "sk-prod-secret-value" not in serialized
    assert "健康原文" not in serialized


def test_hash_sensitive_value_uses_server_secret_pepper(monkeypatch):
    monkeypatch.setattr(security_core, "settings", SimpleNamespace(jwt_secret_key="secret-one-at-least-32-characters-long"))
    first = security_core.hash_sensitive_value("13800138000")
    monkeypatch.setattr(security_core, "settings", SimpleNamespace(jwt_secret_key="secret-two-at-least-32-characters-long"))
    second = security_core.hash_sensitive_value("13800138000")

    assert first
    assert second
    assert len(first) == 64
    assert len(second) == 64
    assert first != second
