"""Image upload validation, sanitization, and re-encoding."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Optional

from PIL import Image, UnidentifiedImageError


ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_MIME_TYPES = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
MAGIC_PREFIXES = {
    "JPEG": (b"\xff\xd8\xff",),
    "PNG": (b"\x89PNG\r\n\x1a\n",),
    "WEBP": (b"RIFF",),
}


@dataclass
class SanitizedImage:
    content: bytes
    format: str
    mime_type: str
    width: int
    height: int
    original_format: Optional[str] = None


def _match_magic_bytes(content: bytes, expected_format: str) -> bool:
    signatures = MAGIC_PREFIXES.get(expected_format, ())
    if expected_format == "WEBP":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return any(content.startswith(signature) for signature in signatures)


def _reject_multiframe_image(image: Image.Image) -> None:
    if bool(getattr(image, "is_animated", False)) or int(getattr(image, "n_frames", 1) or 1) > 1:
        raise ValueError("不支持多帧或动画图片")


def sanitize_image_upload(
    content: bytes,
    *,
    content_type: str,
    max_size_bytes: int,
    max_pixels: Optional[int] = None,
) -> SanitizedImage:
    if not content:
        raise ValueError("图片内容为空")

    if len(content) > max_size_bytes:
        raise ValueError("文件大小超过限制")

    expected_format = ALLOWED_MIME_TYPES.get((content_type or "").lower())
    if expected_format is None:
        raise ValueError("请上传 JPEG、PNG 或 WebP 图片")

    if not _match_magic_bytes(content, expected_format):
        raise ValueError("图片文件头校验失败")

    try:
        with Image.open(BytesIO(content)) as image:
            _reject_multiframe_image(image)
            width, height = image.size
            if max_pixels and width * height > max_pixels:
                raise ValueError("图片像素超过限制")
            image.verify()
    except UnidentifiedImageError as exc:
        raise ValueError("无法识别图片文件") from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("图片文件校验失败") from exc

    with Image.open(BytesIO(content)) as image:
        _reject_multiframe_image(image)
        original_format = image.format
        width, height = image.size
        if original_format not in ALLOWED_IMAGE_FORMATS:
            raise ValueError("图片格式不受支持")

        if width <= 0 or height <= 0:
            raise ValueError("图片尺寸无效")
        if max_pixels and width * height > max_pixels:
            raise ValueError("图片像素超过限制")

        if image.mode not in {"RGB", "RGBA", "L"}:
            image = image.convert("RGB")

        if image.mode == "RGBA":
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background
            output_format = "JPEG"
        elif original_format == "PNG" and image.mode in {"RGBA", "LA"}:
            output_format = "PNG"
        else:
            image = image.convert("RGB")
            output_format = "JPEG"

        output = BytesIO()
        save_kwargs = {"optimize": True}
        if output_format == "JPEG":
            save_kwargs.update({"format": "JPEG", "quality": 92, "progressive": True})
        else:
            save_kwargs.update({"format": "PNG", "compress_level": 6})

        image.save(output, **save_kwargs)
        return SanitizedImage(
            content=output.getvalue(),
            format=output_format,
            mime_type="image/jpeg" if output_format == "JPEG" else "image/png",
            width=width,
            height=height,
            original_format=original_format,
        )
