from io import BytesIO

import pytest
from PIL import Image, features

from app.services.upload_security import sanitize_image_upload


def _image_bytes(fmt: str = "JPEG", size: tuple[int, int] = (8, 8)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=(120, 80, 40)).save(buffer, format=fmt)
    return buffer.getvalue()


def _animated_webp_bytes() -> bytes:
    buffer = BytesIO()
    first = Image.new("RGB", (8, 8), color=(120, 80, 40))
    second = Image.new("RGB", (8, 8), color=(40, 80, 120))
    first.save(
        buffer,
        format="WEBP",
        save_all=True,
        append_images=[second],
        duration=100,
        loop=0,
    )
    return buffer.getvalue()


def test_sanitize_image_upload_reencodes_and_strips_metadata():
    raw = _image_bytes("JPEG")
    image = sanitize_image_upload(
        raw,
        content_type="image/jpeg",
        max_size_bytes=1024 * 1024,
    )

    assert image.format == "JPEG"
    assert image.mime_type == "image/jpeg"
    assert image.width == 8
    assert image.height == 8
    assert image.content.startswith(b"\xff\xd8\xff")


def test_sanitize_image_upload_rejects_mismatched_magic_bytes():
    with pytest.raises(ValueError, match="文件头"):
        sanitize_image_upload(
            b"not-an-image",
            content_type="image/jpeg",
            max_size_bytes=1024,
        )


def test_sanitize_image_upload_rejects_unsupported_mime_type():
    with pytest.raises(ValueError, match="JPEG、PNG 或 WebP"):
        sanitize_image_upload(
            _image_bytes("JPEG"),
            content_type="image/gif",
            max_size_bytes=1024 * 1024,
        )


def test_sanitize_image_upload_rejects_oversized_files():
    raw = _image_bytes("JPEG")

    with pytest.raises(ValueError, match="文件大小超过限制"):
        sanitize_image_upload(
            raw,
            content_type="image/jpeg",
            max_size_bytes=len(raw) - 1,
        )


def test_sanitize_image_upload_rejects_excessive_pixel_count():
    raw = _image_bytes("PNG", size=(9, 9))

    with pytest.raises(ValueError, match="图片像素超过限制"):
        sanitize_image_upload(
            raw,
            content_type="image/png",
            max_size_bytes=1024 * 1024,
            max_pixels=64,
        )



@pytest.mark.skipif(not features.check("webp_anim"), reason="Pillow WebP animation support unavailable")
def test_sanitize_image_upload_rejects_animated_webp():
    with pytest.raises(ValueError, match="多帧或动画"):
        sanitize_image_upload(
            _animated_webp_bytes(),
            content_type="image/webp",
            max_size_bytes=1024 * 1024,
        )
