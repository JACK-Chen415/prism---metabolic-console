from types import SimpleNamespace

from app.api.routes import chat as chat_route
from app.models.knowledge import FallbackStatus, RecommendationLevel, KnowledgeOrigin
from app.models.chat import ChatMessage, MessageRole
from app.core.config import Settings
from app.services.knowledge.severity import pick_strictest_recommendation_level
from app.services.ai_service import DoubaoAIService
from app.services.knowledge.service import KnowledgeService


def test_message_role_enum_uses_persisted_lowercase_values() -> None:
    enum_type = ChatMessage.__table__.c.role.type
    assert enum_type.enums == [member.value for member in MessageRole]


def test_format_cloud_error_connection_message_is_actionable() -> None:
    message = DoubaoAIService._format_cloud_error(RuntimeError("Connection error., request_id: abc"))
    assert "AI 云端服务当前不可达" in message
    assert "request_id: abc" in message


def test_format_cloud_error_access_denied_message_is_actionable() -> None:
    message = DoubaoAIService._format_cloud_error(
        RuntimeError("Error code: 403 - {'error': {'code': 'AccessDenied', 'type': 'Forbidden'}}")
    )
    assert "无访问权限" in message


def test_format_cloud_error_redacts_sensitive_provider_details() -> None:
    raw_error = "Unauthorized api key sk-prod-secret token abc123 endpoint ep-prod-secret-model"

    message = DoubaoAIService._format_cloud_error(RuntimeError(raw_error))

    assert "认证失败" in message
    assert "上游错误细节已隐藏" in message
    assert "sk-prod-secret" not in message
    assert "abc123" not in message
    assert "ep-prod-secret-model" not in message


def test_main_doubao_model_prefers_unified_multimodal_model() -> None:
    settings = Settings(_env_file=None, doubao_model="main-multimodal", doubao_endpoint_id="legacy-text")
    assert settings.main_doubao_model == "main-multimodal"


def test_main_doubao_model_keeps_legacy_text_endpoint_fallback() -> None:
    settings = Settings(_env_file=None, doubao_endpoint_id="legacy-main")
    assert settings.main_doubao_model == "legacy-main"


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
        "billing_provider": "wechat_pay",
        "entitlement_enforce_limits": True,
    }
    data.update(overrides)
    return data


def test_production_settings_accept_real_ai_configuration() -> None:
    settings = Settings(**_production_settings_kwargs())

    assert settings.is_production is True
    assert settings.main_doubao_model == "ep-prod-multimodal"


def test_production_settings_reject_placeholder_ark_api_key() -> None:
    import pytest

    with pytest.raises(ValueError, match="ARK_API_KEY"):
        Settings(**_production_settings_kwargs(ark_api_key="your_ark_api_key"))


def test_production_settings_reject_placeholder_doubao_model() -> None:
    import pytest

    with pytest.raises(ValueError, match="DOUBAO_MODEL"):
        Settings(**_production_settings_kwargs(doubao_model="ep-xxxxxxxxxx"))


def test_image_data_url_uses_input_media_type() -> None:
    assert DoubaoAIService._image_data_url("abc", "png") == "data:image/png;base64,abc"


def test_assistant_preference_context_describes_mode_and_intensity() -> None:
    context = DoubaoAIService._assistant_preference_context(
        {
            "ai_mode": "gentle",
            "intervention_intensity": "high",
        }
    )

    assert "教练模式" in context
    assert "强干预" in context
    assert "不能弱化风险和限制" in context


def test_assistant_preference_context_omits_section_when_unspecified() -> None:
    context = DoubaoAIService._assistant_preference_context({})

    assert context == ""


def test_extract_json_object_accepts_markdown_fence() -> None:
    payload = DoubaoAIService._extract_json_object('```json\n{"foods": []}\n```')
    assert payload == {"foods": []}


def test_pick_strictest_recommendation_level_handles_empty_levels() -> None:
    assert pick_strictest_recommendation_level([]) is None
    assert pick_strictest_recommendation_level([SimpleNamespace(recommendation_level=None)]) is None


def test_pick_strictest_recommendation_level_uses_highest_severity() -> None:
    decisions = [
        SimpleNamespace(recommendation_level=RecommendationLevel.RECOMMEND),
        SimpleNamespace(recommendation_level=None),
        SimpleNamespace(recommendation_level=RecommendationLevel.LIMIT),
        SimpleNamespace(recommendation_level=RecommendationLevel.MODERATE),
    ]

    assert pick_strictest_recommendation_level(decisions) == RecommendationLevel.LIMIT


def test_enforce_llm_output_safety_blocks_relaxing_language_for_avoid_rules() -> None:
    service = KnowledgeService()
    reviewed = service.enforce_llm_output_safety(
        "这个食物可以放心吃，影响不大。",
        local_decisions=[
            SimpleNamespace(
                food_name="虾仁",
                recommendation_level=RecommendationLevel.AVOID,
                hard_blocks=["虾过敏"],
                warnings=["本地规则：虾仁 -> AVOID"],
                summary="虾仁命中过敏/显式忌口，本地规则直接阻断。",
                caution_note="存在绝对约束项，云端只能解释原因或提供替代建议。",
                conflict_note=None,
            )
        ],
        fallback_status=FallbackStatus.LOCAL_BLOCKED_NO_CLOUD,
        context_label="AI 回复",
    )

    assert "本地规则复核" in reviewed
    assert "不能把禁忌或限制说成可放心食用" in reviewed
    assert "这个食物可以放心吃" not in reviewed


def test_chat_telemetry_attachment_exposes_only_sanitized_metrics() -> None:
    telemetry = {
        "cloud_called": True,
        "chat_total_ms": 128.4,
        "doubao_total_ms": 88.2,
        "response_chars": 42,
        "prompt_chars": 120,
        "message_count": 3,
        "error": "TimeoutError",
    }

    attachment = chat_route._chat_telemetry_attachment(telemetry)
    serialized = str(attachment)

    assert attachment["estimated_cost_usd"] is None
    assert attachment["cost_status"] == "unconfigured"
    assert attachment["cost_source"] == "ai_cost_usd_per_1k_tokens_not_configured"
    assert attachment["cloud_called"] is True
    assert attachment["chat_total_ms"] == 128.4
    assert attachment["doubao_total_ms"] == 88.2
    assert "prompt" in serialized
    assert "content" not in serialized.lower()


def test_chat_telemetry_attachment_estimates_cost_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_route,
        "settings",
        SimpleNamespace(ai_cost_usd_per_1k_tokens=0.02, ai_cost_estimate_chars_per_token=2.0),
    )
    attachment = chat_route._chat_telemetry_attachment(
        {
            "cloud_called": True,
            "prompt_chars": 120,
            "response_chars": 80,
        }
    )

    assert attachment["cost_status"] == "estimated"
    assert attachment["cost_source"] == "char_based_estimate"
    assert attachment["estimated_tokens"] == 100.0
    assert attachment["estimated_cost_usd"] == 0.002
