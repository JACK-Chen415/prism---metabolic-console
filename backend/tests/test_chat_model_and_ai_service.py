from app.models.chat import ChatMessage, MessageRole
from app.core.config import Settings
from app.services.ai_service import DoubaoAIService


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


def test_main_doubao_model_prefers_unified_multimodal_model() -> None:
    settings = Settings(_env_file=None, doubao_model="main-multimodal", doubao_endpoint_id="legacy-text")
    assert settings.main_doubao_model == "main-multimodal"


def test_main_doubao_model_keeps_legacy_text_endpoint_fallback() -> None:
    settings = Settings(_env_file=None, doubao_endpoint_id="legacy-main")
    assert settings.main_doubao_model == "legacy-main"


def test_image_data_url_uses_input_media_type() -> None:
    assert DoubaoAIService._image_data_url("abc", "png") == "data:image/png;base64,abc"


def test_extract_json_object_accepts_markdown_fence() -> None:
    payload = DoubaoAIService._extract_json_object('```json\n{"foods": []}\n```')
    assert payload == {"foods": []}
