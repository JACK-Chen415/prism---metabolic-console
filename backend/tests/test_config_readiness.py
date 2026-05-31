import pytest
from types import SimpleNamespace
from fastapi import Response, status

from app import main as app_main
from app.core.config import Settings


def _production_settings_kwargs(**overrides):
    data = {
        "_env_file": None,
        "app_env": "production",
        "debug": False,
        "jwt_secret_key": "prod-secret-key-at-least-32-characters-long",
        "otp_provider": "audit_only",
        "cors_origins": ["https://app.example.com"],
        "database_url": "postgresql+asyncpg://prism:secret@db.example.com:5432/prism",
        "ark_api_key": "ark_prod_configured_value",
        "doubao_model": "ep-prod-multimodal",
        "admin_phone_hashes": ["test-admin-phone-hash"],
    }
    data.update(overrides)
    return data


def test_readiness_snapshot_is_sanitized_and_warns_for_local_placeholders():
    settings = Settings(
        _env_file=None,
        app_env="development",
        ark_api_key="your_ark_api_key",
        doubao_model="ep-xxxxxxxxxx",
        otp_provider="dev",
    )

    snapshot = settings.readiness_snapshot()
    serialized = str(snapshot)

    assert snapshot["status"] == "ok"
    assert snapshot["is_production"] is False
    assert snapshot["ai_key_configured"] is False
    assert snapshot["ai_model_configured"] is False
    assert "non_production_environment" in snapshot["warnings"]
    assert "ai_key_placeholder_or_missing" in snapshot["warnings"]
    assert "ai_model_placeholder_or_missing" in snapshot["warnings"]
    assert "dev_otp_provider" in snapshot["warnings"]
    assert "your_ark_api_key" not in serialized
    assert "ep-xxxxxxxxxx" not in serialized


def test_settings_distinguishes_development_and_non_development_envs():
    development = Settings(_env_file=None, app_env="development")
    staging = Settings(_env_file=None, app_env="staging")

    assert development.is_development is True
    assert development.is_production is False
    assert staging.is_development is False
    assert staging.is_production is False


def test_settings_normalizes_and_validates_otp_provider():
    settings = Settings(_env_file=None, otp_provider="audit-only")

    assert settings.otp_provider == "audit_only"
    assert settings.readiness_snapshot()["otp_provider"] == "audit_only"
    assert "otp_provider_audit_only" in settings.readiness_snapshot()["warnings"]

    with pytest.raises(ValueError, match="OTP_PROVIDER"):
        Settings(_env_file=None, otp_provider="sms")


def test_readiness_snapshot_reports_ok_for_real_production_config_without_secrets():
    settings = Settings(**_production_settings_kwargs())

    snapshot = settings.readiness_snapshot()
    serialized = str(snapshot)

    assert snapshot["status"] == "ok"
    assert snapshot["is_production"] is True
    assert snapshot["warnings"] == ["otp_provider_audit_only", "mock_billing_provider", "entitlement_limits_soft_only"]
    assert snapshot["blocking"] == []
    assert snapshot["ai_key_configured"] is True
    assert snapshot["ai_model_configured"] is True
    assert snapshot["otp_provider"] == "audit_only"
    assert snapshot["jwt_algorithm"] == "HS256"
    assert snapshot["jwt_access_token_expire_minutes"] == 30
    assert snapshot["jwt_refresh_token_expire_days"] == 7
    assert snapshot["billing_provider"] == "mock"
    assert snapshot["entitlement_enforce_limits"] is False
    assert "mock_billing_provider" in snapshot["warnings"]
    assert "entitlement_limits_soft_only" in snapshot["warnings"]
    assert "ark_prod_configured_value" not in serialized
    assert "ep-prod-multimodal" not in serialized
    assert "prod-secret-key-at-least-32-characters-long" not in serialized
    assert "test-admin-phone-hash" not in serialized


def test_readiness_snapshot_warns_when_production_admin_bootstrap_allowlist_is_missing():
    settings = Settings(**_production_settings_kwargs(admin_phone_hashes=[]))

    snapshot = settings.readiness_snapshot()
    serialized = str(snapshot)

    assert snapshot["status"] == "ok"
    assert snapshot["is_production"] is True
    assert "admin_bootstrap_allowlist_missing" in snapshot["warnings"]
    assert snapshot["blocking"] == []
    assert snapshot["admin_bootstrap_allowlist_count"] == 0
    assert "admin_bootstrap_allowlist_missing" in serialized


def test_readiness_snapshot_exposes_entitlement_enforcement_without_soft_limit_warning():
    settings = Settings(**_production_settings_kwargs(entitlement_enforce_limits=True))

    snapshot = settings.readiness_snapshot()

    assert snapshot["status"] == "ok"
    assert snapshot["entitlement_enforce_limits"] is True
    assert "entitlement_limits_soft_only" not in snapshot["warnings"]
    assert "mock_billing_provider" in snapshot["warnings"]


class _ReadyConn:
    async def exec_driver_sql(self, _sql):
        return None


class _ReadyBegin:
    async def __aenter__(self):
        return _ReadyConn()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _ReadyEngine:
    def begin(self):
        return _ReadyBegin()


class _FailingBegin:
    async def __aenter__(self):
        raise RuntimeError("database unavailable")

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FailingEngine:
    def begin(self):
        return _FailingBegin()


@pytest.mark.asyncio
async def test_ready_endpoint_returns_503_when_database_is_unavailable(monkeypatch):
    monkeypatch.setattr(app_main, "engine", _FailingEngine())
    monkeypatch.setattr(
        app_main,
        "settings",
        SimpleNamespace(
            readiness_snapshot=lambda: {
                "status": "ok",
                "blocking": [],
                "warnings": [],
            }
        ),
    )
    response = Response()

    payload = await app_main.ready_check(response)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert payload["status"] == "degraded"
    assert payload["checks"]["database"].startswith("error:")


@pytest.mark.asyncio
async def test_ready_endpoint_returns_503_when_config_is_blocked(monkeypatch):
    monkeypatch.setattr(app_main, "engine", _ReadyEngine())
    monkeypatch.setattr(
        app_main,
        "settings",
        SimpleNamespace(
            readiness_snapshot=lambda: {
                "status": "blocked",
                "blocking": ["dev_otp_provider"],
                "warnings": [],
            }
        ),
    )
    response = Response()

    payload = await app_main.ready_check(response)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert payload["status"] == "degraded"
    assert payload["checks"]["config"] == "blocked"


@pytest.mark.asyncio
async def test_ready_endpoint_allows_sanitized_warnings(monkeypatch):
    monkeypatch.setattr(app_main, "engine", _ReadyEngine())
    monkeypatch.setattr(
        app_main,
        "settings",
        SimpleNamespace(
            readiness_snapshot=lambda: {
                "status": "ok",
                "blocking": [],
                "warnings": ["mock_billing_provider"],
            }
        ),
    )
    response = Response()

    payload = await app_main.ready_check(response)

    assert response.status_code == status.HTTP_200_OK
    assert payload["status"] == "ready"
    assert payload["checks"]["config_details"]["warnings"] == ["mock_billing_provider"]



def test_readiness_snapshot_flags_upload_limits_above_reviewed_cap():
    settings = Settings(
        _env_file=None,
        app_env="development",
        max_upload_size_mb=25,
        max_upload_image_pixels=25_000_000,
    )

    snapshot = settings.readiness_snapshot()

    assert snapshot["status"] == "ok"
    assert "upload_limits_exceed_reviewed_cap" in snapshot["warnings"]
    assert snapshot["max_upload_size_mb"] == 25
    assert snapshot["max_upload_image_pixels"] == 25_000_000


def test_production_rejects_upload_limits_above_reviewed_cap():
    with pytest.raises(ValueError, match="MAX_UPLOAD_SIZE_MB"):
        Settings(**_production_settings_kwargs(max_upload_size_mb=11))

    with pytest.raises(ValueError, match="MAX_UPLOAD_IMAGE_PIXELS"):
        Settings(**_production_settings_kwargs(max_upload_image_pixels=20_000_001))


def test_production_readiness_snapshot_exposes_only_allowlist_count():
    settings = Settings(**_production_settings_kwargs(admin_phone_hashes=["hash-one", "hash-two"]))

    snapshot = settings.readiness_snapshot()
    serialized = str(snapshot)

    assert snapshot["status"] == "ok"
    assert snapshot["admin_bootstrap_allowlist_count"] == 2
    assert "admin_bootstrap_allowlist_missing" not in snapshot["warnings"]
    assert "hash-one" not in serialized
    assert "hash-two" not in serialized


def test_readiness_snapshot_flags_jwt_lifetimes_above_reviewed_cap_outside_production():
    settings = Settings(
        _env_file=None,
        app_env="development",
        jwt_access_token_expire_minutes=120,
        jwt_refresh_token_expire_days=45,
    )

    snapshot = settings.readiness_snapshot()

    assert snapshot["status"] == "ok"
    assert "jwt_access_token_exceeds_reviewed_cap" in snapshot["warnings"]
    assert "jwt_refresh_token_exceeds_reviewed_cap" in snapshot["warnings"]
    assert snapshot["jwt_access_token_expire_minutes"] == 120
    assert snapshot["jwt_refresh_token_expire_days"] == 45


def test_settings_normalizes_jwt_algorithm_case():
    settings = Settings(_env_file=None, jwt_algorithm="hs512")

    assert settings.jwt_algorithm == "HS512"
    assert settings.readiness_snapshot()["jwt_algorithm"] == "HS512"


def test_settings_rejects_unsupported_jwt_algorithm_and_non_positive_lifetimes():
    with pytest.raises(ValueError, match="JWT_ALGORITHM"):
        Settings(_env_file=None, jwt_algorithm="none")

    with pytest.raises(ValueError, match="JWT_ACCESS_TOKEN_EXPIRE_MINUTES"):
        Settings(_env_file=None, jwt_access_token_expire_minutes=0)

    with pytest.raises(ValueError, match="JWT_REFRESH_TOKEN_EXPIRE_DAYS"):
        Settings(_env_file=None, jwt_refresh_token_expire_days=0)


def test_production_rejects_jwt_lifetimes_above_reviewed_cap():
    with pytest.raises(ValueError, match="JWT_ACCESS_TOKEN_EXPIRE_MINUTES"):
        Settings(**_production_settings_kwargs(jwt_access_token_expire_minutes=61))

    with pytest.raises(ValueError, match="JWT_REFRESH_TOKEN_EXPIRE_DAYS"):
        Settings(**_production_settings_kwargs(jwt_refresh_token_expire_days=31))


def test_production_rejects_long_placeholder_jwt_secret():
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(**_production_settings_kwargs(jwt_secret_key="your-super-secret-key-change-in-production-at-least-32-characters"))
