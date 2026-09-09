"""Internal helpers for `ai_service.py`.

Pure / static helpers extracted so the facade class stays focused on
chat, streaming and food recognition flows.

Nothing here should import from `ai_service` to avoid circular imports.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def enum_value(value: Any) -> Any:
    """Return `.value` for Enum-like objects, else the value itself."""
    return getattr(value, "value", value)


def format_cloud_error(error: Exception) -> str:
    """Map a Doubao SDK exception to a user-friendly Chinese message."""
    detail = str(error).strip() or error.__class__.__name__
    lowered = detail.lower()
    if "403" in lowered or "accessdenied" in lowered or "forbidden" in lowered:
        return f"抱歉，AI 服务当前无访问权限，请检查豆包 endpoint 绑定、账号权限或 API key 所属项目。详细：{detail}"
    if "connection error" in lowered or "timed out" in lowered or "timeout" in lowered:
        return f"抱歉，AI 云端服务当前不可达，请检查网络连通性或豆包 endpoint 配置。详细：{detail}"
    if "unauthorized" in lowered or "authentication" in lowered or "api key" in lowered:
        return f"抱歉，AI 服务认证失败，请检查 ARK_API_KEY 或 endpoint 配置。详细：{detail}"
    return f"抱歉，服务暂时不可用：{detail}"


def normalize_image_type(image_type: Optional[str]) -> str:
    """Normalize image MIME subtype to one of: jpeg, png, webp, gif."""
    raw_type = (image_type or "jpeg").strip().lower()
    if raw_type in {"jpg", "jpeg"}:
        return "jpeg"
    if raw_type in {"png", "webp", "gif"}:
        return raw_type
    return "jpeg"


def image_data_url(image_base64: str, image_type: Optional[str] = None) -> str:
    """Wrap a base64 image payload as a data URL suitable for Doubao vision input."""
    cleaned = image_base64.strip()
    if cleaned.startswith("data:image/"):
        return cleaned
    return f"data:image/{normalize_image_type(image_type)};base64,{cleaned}"


def create_chat_completion(
    client: Any,
    *,
    messages: List[Dict[str, Any]],
    temperature: float,
    max_tokens: int,
    stream: bool = False,
) -> Any:
    """Create a chat completion through the single main multimodal model."""
    return client.chat.completions.create(
        model=settings.main_doubao_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream,
    )
