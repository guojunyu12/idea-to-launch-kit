from __future__ import annotations

import hashlib
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.errors import AppError


FORMAT_BY_CONTENT_TYPE = {"image/jpeg": {"JPEG"}, "image/png": {"PNG"}, "image/webp": {"WEBP"}}


def validate_image(data: bytes, content_type: str, filename: str, max_bytes: int) -> str:
    if len(data) == 0 or len(data) > max_bytes:
        raise AppError("INVALID_UPLOAD", "图片为空或超过 10 MB 限制")
    if content_type not in FORMAT_BY_CONTENT_TYPE:
        raise AppError("INVALID_UPLOAD", "仅支持 JPG、PNG 或 WebP 图片")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise AppError("INVALID_UPLOAD", "文件扩展名不受支持")
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = (image.format or "").upper()
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise AppError("INVALID_UPLOAD", "文件不是有效图片") from exc
    if image_format not in FORMAT_BY_CONTENT_TYPE[content_type]:
        raise AppError("INVALID_UPLOAD", "声明的类型与图片真实格式不一致")
    return hashlib.sha256(data).hexdigest()


def store_upload(root: Path, upload_id: str, filename: str, data: bytes) -> Path:
    safe_name = Path(filename).name
    if safe_name != filename or safe_name in {"", ".", ".."}:
        raise AppError("INVALID_UPLOAD", "文件名不安全")
    destination = root / "uploads" / f"{upload_id}-{uuid.uuid4().hex}{Path(safe_name).suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return destination


def remove_file(path: str | Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
