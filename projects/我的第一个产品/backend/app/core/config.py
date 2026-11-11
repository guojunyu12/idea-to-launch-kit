from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PRODUCT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_root: Path
    template_library_path: Path
    max_upload_bytes: int = 10 * 1024 * 1024
    allowed_content_types: tuple[str, ...] = ("image/jpeg", "image/png", "image/webp")
    provider_mode: str = "mock"
    sensenova_api_key: str = ""
    sensenova_base_url: str = "https://token.sensenova.cn/v1"
    sensenova_model: str = "sensenova-u1-fast"
    sensenova_timeout_seconds: float = 120.0
    sensenova_max_retries: int = 2
    sensenova_retry_backoff_seconds: float = 1.0
    qwen_api_key: str = ""
    qwen_endpoint: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    qwen_model: str = "qwen-image-2.1-turbo"
    auth_mode: str = "dev_fixed"
    auth_dev_code: str = "000000"
    admin_emails: tuple[str, ...] = ()
    operator_emails: tuple[str, ...] = ()
    session_ttl_seconds: int = 60 * 60 * 24 * 7
    login_code_ttl_seconds: int = 600
    login_code_max_attempts: int = 5
    session_cookie_secure: bool = False


def build_settings(
    database_url: str | None = None,
    storage_root: str | Path | None = None,
    template_library_path: str | Path | None = None,
) -> Settings:
    root = PRODUCT_ROOT / "data"
    def csv_env(name: str) -> tuple[str, ...]:
        return tuple(item.strip().lower() for item in os.getenv(name, "").split(",") if item.strip())

    auth_mode = os.getenv("AUTH_MODE", "dev_fixed").lower()
    if auth_mode == "production":
        raise RuntimeError("生产环境禁止使用固定验证码模式")
    return Settings(
        database_url=database_url or os.getenv("TASK_DB_URL", f"sqlite:///{root / 'app.db'}"),
        storage_root=Path(storage_root or os.getenv("STORAGE_ROOT", root / "storage")),
        template_library_path=Path(
            template_library_path
            or os.getenv("TEMPLATE_LIBRARY_PATH", root / "templates.json")
        ),
        provider_mode=os.getenv("GEN_PROVIDER_MODE", "mock").lower(),
        sensenova_api_key=os.getenv("SENSENOVA_API_KEY", ""),
        sensenova_base_url=os.getenv("SENSENOVA_BASE_URL", "https://token.sensenova.cn/v1"),
        sensenova_model=os.getenv("SENSENOVA_MODEL", "sensenova-u1-fast"),
        sensenova_timeout_seconds=float(os.getenv("SENSENOVA_TIMEOUT_SECONDS", "120")),
        sensenova_max_retries=int(os.getenv("SENSENOVA_MAX_RETRIES", "2")),
        sensenova_retry_backoff_seconds=float(os.getenv("SENSENOVA_RETRY_BACKOFF_SECONDS", "1")),
        qwen_api_key=os.getenv("QWEN_IMAGE_API_KEY", os.getenv("DASHSCOPE_API_KEY", "")),
        qwen_endpoint=os.getenv("QWEN_IMAGE_ENDPOINT", "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"),
        qwen_model=os.getenv("QWEN_IMAGE_MODEL", "qwen-image-2.1-turbo"),
        auth_mode=auth_mode,
        auth_dev_code=os.getenv("AUTH_DEV_CODE", "000000"),
        admin_emails=csv_env("ADMIN_EMAILS"),
        operator_emails=csv_env("OPERATOR_EMAILS"),
        session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", str(60 * 60 * 24 * 7))),
        login_code_ttl_seconds=int(os.getenv("LOGIN_CODE_TTL_SECONDS", "600")),
        login_code_max_attempts=int(os.getenv("LOGIN_CODE_MAX_ATTEMPTS", "5")),
        session_cookie_secure=os.getenv("SESSION_COOKIE_SECURE", "0").lower() in {"1", "true", "yes"},
    )
