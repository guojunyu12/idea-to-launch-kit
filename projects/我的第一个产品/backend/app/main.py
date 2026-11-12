from __future__ import annotations

import json
import hashlib
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import Settings, build_settings
from app.core.errors import (
    AppError,
    app_error_handler,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from app.db import (
    AuditEvent,
    GenerationRecord,
    LoginChallengeRecord,
    ModelConfigRecord,
    SessionRecord,
    TaskRecord,
    TemplateRecord,
    TemplateVersionRecord,
    UploadRecord,
    UserRecord,
    VersionRecord,
    create_session_factory,
)
from app.schemas import (
    AuditListOut,
    AuditOut,
    CreateTaskIn,
    EmailCodeRequest,
    EmailCodeVerify,
    GenerationCreateIn,
    GenerationListOut,
    GenerationOut,
    ModelListOut,
    ModelOut,
    RegenerateTaskIn,
    TaskOut,
    TemplateImportIn,
    TemplateListOut,
    TemplateOut,
    TemplateReviewIn,
    UploadOut,
    UserEnvelope,
    UserOut,
    VersionOut,
)
from app.services.mock_provider import MockProvider
from app.services.qwen_image_provider import QwenImageProvider
from app.services.sensenova_provider import SenseNovaProvider
from app.services.storage import remove_file, store_upload, validate_image
from app.services.templates import find_template, load_templates

ASPECT_RATIO_SIZES = {
    "1:1": (2048, 2048),
    "4:3": (2368, 1760),
    "3:2": (2496, 1664),
    "16:9": (2752, 1536),
    "3:4": (1760, 2368),
    "2:3": (1664, 2496),
    "4:5": (1824, 2272),
    "9:16": (1536, 2752),
    "9:19.5": (1179, 2556),
    "9:21": (1344, 3136),
}

SESSION_COOKIE = "aigc_session"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not EMAIL_RE.fullmatch(email):
        raise AppError("INVALID_EMAIL", "邮箱格式无效")
    return email


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _user_payload(user: UserRecord) -> dict:
    return {"id": user.id, "email": user.email_normalized, "role": user.role, "status": user.status}


def _template_payload(row: TemplateRecord, *, legacy_kind: bool = False) -> dict:
    kind = "wallpaper" if legacy_kind and row.module_kind == "mobile_wallpaper" else row.module_kind
    return {
        "template_id": row.id,
        "name": row.title,
        "kind": kind,
        "module_kind": row.module_kind,
        "target_width": row.target_width,
        "target_height": row.target_height,
        "prompt_key": row.prompt_key,
        "reference_image_url": row.reference_image_url,
        "default_aspect_ratio": row.default_aspect_ratio,
        "status": row.status,
        "version_no": row.version_no,
    }


def _model_payload(row: ModelConfigRecord) -> dict:
    return {
        "model_id": row.model_id,
        "name": row.name,
        "provider": row.provider,
        "enabled": row.enabled,
        "is_default": row.is_default,
        "module_bindings": json.loads(row.module_bindings_json or "[]"),
        "supported_ratios": json.loads(row.supported_ratios_json or "[]"),
        "points_per_success": row.points_per_success,
    }


def _generation_payload(row: GenerationRecord) -> dict:
    return {
        "generation_id": row.id,
        "template_id": row.template_id,
        "module_kind": row.module_kind,
        "status": row.status,
        "prompt": row.prompt_snapshot,
        "model_id": row.model_id,
        "provider": row.provider,
        "aspect_ratio": row.aspect_ratio,
        "output_width": row.output_width,
        "output_height": row.output_height,
        "asset_url": f"/api/v1/generations/{row.id}/asset" if row.status == "succeeded" and row.asset_path else None,
        "elapsed_ms": row.elapsed_ms,
        "cost_cents": row.cost_cents,
        "points_charged": row.points_charged,
        "free_quota_used": row.free_quota_used,
        "charge_status": row.charge_status,
        "error_code": row.error_code,
    }


def _seed_legacy_templates(session_factory, library_path: Path) -> None:
    """Import the legacy JSON catalog once so V7 can enforce publish state in the DB."""
    try:
        raw = json.loads(library_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    session = session_factory()
    try:
        if session.scalar(select(TemplateRecord.id).limit(1)) is not None:
            return
        now = _utcnow()
        for item in raw if isinstance(raw, list) else []:
            module_kind = "mobile_wallpaper" if item.get("kind") == "wallpaper" else item.get("kind", "sticker")
            row = TemplateRecord(
                id=str(item.get("template_id")),
                slug=str(item.get("template_id")),
                module_kind=module_kind,
                title=str(item.get("name", item.get("template_id"))),
                default_prompt="",
                target_width=int(item.get("target_width", 1)),
                target_height=int(item.get("target_height", 1)),
                default_aspect_ratio=item.get("default_aspect_ratio"),
                prompt_key=str(item.get("prompt_key", "")),
                reference_image_url=item.get("reference_image_url"),
                source_platform="legacy",
                source_type="legacy",
                rights_status="legacy_unverified",
                status="published",
                published_at=now,
                version_no=1,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.add(
                TemplateVersionRecord(
                    template_id=row.id,
                    version_no=1,
                    prompt_snapshot=row.default_prompt,
                    target_width=row.target_width,
                    target_height=row.target_height,
                    status="published",
                    published_at=now,
                )
            )
        session.commit()
    finally:
        session.close()


def _seed_default_model(session_factory, settings: Settings) -> None:
    session = session_factory()
    try:
        existing_rows = list(session.scalars(select(ModelConfigRecord)))
        # Importing the module in tests uses the safe mock default. Never let
        # that implicit default overwrite an already configured real provider.
        if settings.provider_mode == "mock" and existing_rows:
            return
        if settings.provider_mode == "qwen":
            model_id, name, provider = settings.qwen_model, "千问图片生成", "qwen"
        elif settings.provider_mode == "sensenova":
            model_id, name, provider = settings.sensenova_model, "商汤图片生成", "sensenova"
        else:
            model_id, name, provider = "mock", "开发测试模型", "mock"
        row = session.scalar(select(ModelConfigRecord).where(ModelConfigRecord.model_id == model_id))
        if row is None:
            row = ModelConfigRecord(
                name=name,
                provider=provider,
                model_id=model_id,
                model_type="image_generation",
                enabled=True,
                priority=1,
                module_bindings_json=json.dumps(["sticker", "mobile_wallpaper", "desktop_wallpaper"]),
                supported_ratios_json=json.dumps(list(ASPECT_RATIO_SIZES)),
                points_per_success=1,
                cost_cents_per_call=0,
            )
            session.add(row)
        for existing in existing_rows:
            existing.is_default = existing.model_id == model_id
            if existing.model_id != model_id and existing.provider in {"mock", "qwen", "sensenova"}:
                existing.enabled = False
        row.enabled = True
        row.is_default = True
        session.commit()
    finally:
        session.close()


def create_app(
    database_url: str | None = None,
    storage_root: str | Path | None = None,
    template_library_path: str | Path | None = None,
) -> FastAPI:
    settings = build_settings(database_url, storage_root, template_library_path)
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    session_factory = create_session_factory(settings.database_url)
    _seed_legacy_templates(session_factory, settings.template_library_path)
    _seed_default_model(session_factory, settings)
    if settings.provider_mode == "qwen":
        provider = QwenImageProvider(
            api_key=settings.qwen_api_key,
            endpoint=settings.qwen_endpoint,
            model=settings.qwen_model,
            timeout=max(settings.sensenova_timeout_seconds, 180.0),
            max_retries=settings.sensenova_max_retries,
            retry_backoff_seconds=settings.sensenova_retry_backoff_seconds,
        )
    elif settings.provider_mode == "sensenova":
        provider = SenseNovaProvider(
            api_key=settings.sensenova_api_key,
            base_url=settings.sensenova_base_url,
            model=settings.sensenova_model,
            timeout=settings.sensenova_timeout_seconds,
            max_retries=settings.sensenova_max_retries,
            retry_backoff_seconds=settings.sensenova_retry_backoff_seconds,
        )
    else:
        provider = MockProvider()

    app = FastAPI(title="图个乐 API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:3001",
            "http://localhost:3001",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.provider = provider

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)

    def owner_id(x_owner_id: Annotated[str | None, Header()] = None) -> str:
        value = (x_owner_id or "demo-owner").strip()
        if not value or len(value) > 120:
            raise AppError("INVALID_OWNER", "用户标识无效")
        return value

    def db() -> Session:
        return session_factory()

    def current_user(
        session: Session = Depends(db),
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> UserRecord:
        if not session_token:
            raise AppError("AUTH_REQUIRED", "请先登录", 401)
        record = session.scalar(
            select(SessionRecord).where(
                SessionRecord.token_hash == _sha256(session_token),
                SessionRecord.revoked_at.is_(None),
            )
        )
        if record is None or _as_utc(record.expires_at) <= _utcnow():
            raise AppError("AUTH_REQUIRED", "登录已失效，请重新登录", 401)
        user = session.get(UserRecord, record.user_id)
        if user is None or user.status != "active":
            raise AppError("AUTH_REQUIRED", "账号不可用", 401)
        record.last_seen_at = _utcnow()
        session.commit()
        return user

    def require_operator(user: UserRecord = Depends(current_user)) -> UserRecord:
        if user.role not in {"operator", "admin"}:
            raise AppError("ROLE_FORBIDDEN", "需要运营或管理员权限", 403)
        return user

    def require_admin(user: UserRecord = Depends(current_user)) -> UserRecord:
        if user.role != "admin":
            raise AppError("ROLE_FORBIDDEN", "需要管理员权限", 403)
        return user

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/test", include_in_schema=False)
    def test_console():
        page = Path(__file__).resolve().parent / "web" / "test_console.html"
        return FileResponse(page, media_type="text/html")

    @app.post("/api/v1/auth/request-code")
    def request_login_code(payload: EmailCodeRequest, session: Session = Depends(db)):
        email = _normalize_email(payload.email)
        if settings.auth_mode != "dev_fixed":
            raise AppError("AUTH_PROVIDER_NOT_CONFIGURED", "邮箱服务尚未配置", 503)
        now = _utcnow()
        challenge = LoginChallengeRecord(
            email_normalized=email,
            code_hash=_sha256(settings.auth_dev_code),
            expires_at=now + timedelta(seconds=settings.login_code_ttl_seconds),
        )
        session.add(challenge)
        session.commit()
        return {
            "challenge_id": challenge.id,
            "expires_at": challenge.expires_at.isoformat(),
            "delivery": "dev_fixed_code",
        }

    @app.post("/api/v1/auth/verify-code", response_model=UserEnvelope)
    def verify_login_code(payload: EmailCodeVerify, response: Response, session: Session = Depends(db)):
        email = _normalize_email(payload.email)
        challenge = session.get(LoginChallengeRecord, payload.challenge_id)
        now = _utcnow()
        if challenge is None or challenge.email_normalized != email:
            raise AppError("INVALID_CODE", "验证码无效", 401)
        if challenge.consumed_at is not None:
            raise AppError("CODE_ALREADY_USED", "验证码已使用", 401)
        if _as_utc(challenge.expires_at) <= now:
            raise AppError("CODE_EXPIRED", "验证码已过期", 401)
        if challenge.attempts >= settings.login_code_max_attempts:
            raise AppError("CODE_ATTEMPTS_EXCEEDED", "验证码尝试次数过多", 401)
        challenge.attempts += 1
        if _sha256(payload.code) != challenge.code_hash:
            session.commit()
            raise AppError("INVALID_CODE", "验证码无效", 401)
        challenge.consumed_at = now
        role = "admin" if email in settings.admin_emails else "operator" if email in settings.operator_emails else "user"
        user = session.scalar(select(UserRecord).where(UserRecord.email_normalized == email))
        if user is None:
            user = UserRecord(email_normalized=email, role=role, status="active")
            session.add(user)
            session.flush()
        elif user.status != "active":
            session.commit()
            raise AppError("ACCOUNT_DISABLED", "账号已停用", 403)
        else:
            user.role = role
        user.last_login_at = now
        raw_token = secrets.token_urlsafe(32)
        session.add(
            SessionRecord(
                token_hash=_sha256(raw_token),
                user_id=user.id,
                expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
            )
        )
        session.add(AuditEvent(owner_id=user.id, actor_user_id=user.id, actor_role=user.role, action="login", result="succeeded", metadata_json="{}"))
        session.commit()
        response.set_cookie(
            SESSION_COOKIE,
            raw_token,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            max_age=settings.session_ttl_seconds,
        )
        return {"user": _user_payload(user)}

    @app.get("/api/v1/auth/me", response_model=UserEnvelope)
    def auth_me(user: UserRecord = Depends(current_user)):
        return {"user": _user_payload(user)}

    @app.post("/api/v1/auth/logout")
    def auth_logout(response: Response, session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE), session: Session = Depends(db)):
        if session_token:
            record = session.scalar(select(SessionRecord).where(SessionRecord.token_hash == _sha256(session_token)))
            if record is not None:
                record.revoked_at = _utcnow()
                session.commit()
        response.delete_cookie(SESSION_COOKIE)
        return {"ok": True}

    @app.get("/api/v1/templates", response_model=TemplateListOut)
    def templates(
        kind: str | None = Query(default=None),
        module: str | None = Query(default=None),
        session: Session = Depends(db),
    ):
        if kind is not None and kind not in {"sticker", "wallpaper"}:
            raise AppError("INVALID_KIND", "品类必须是 sticker 或 wallpaper")
        if module is not None and module not in {"sticker", "mobile_wallpaper", "desktop_wallpaper"}:
            raise AppError("INVALID_MODULE", "模块必须是 sticker、mobile_wallpaper 或 desktop_wallpaper")
        module_filter = module or ("mobile_wallpaper" if kind == "wallpaper" else kind)
        query = select(TemplateRecord).where(TemplateRecord.status == "published")
        if module_filter:
            query = query.where(TemplateRecord.module_kind == module_filter)
        rows = list(session.scalars(query.order_by(TemplateRecord.created_at)))
        return {"items": [TemplateOut.model_validate(_template_payload(row, legacy_kind=kind == "wallpaper")) for row in rows]}

    @app.get("/api/v1/models", response_model=ModelListOut)
    def models(module: str | None = Query(default=None), session: Session = Depends(db)):
        rows = list(session.scalars(select(ModelConfigRecord).where(ModelConfigRecord.enabled.is_(True)).order_by(ModelConfigRecord.priority, ModelConfigRecord.created_at)))
        if module:
            rows = [row for row in rows if not json.loads(row.module_bindings_json or "[]") or module in json.loads(row.module_bindings_json or "[]")]
        return {"items": [ModelOut.model_validate(_model_payload(row)) for row in rows]}

    @app.get("/api/v1/admin/models", response_model=ModelListOut)
    def admin_models(user: UserRecord = Depends(require_operator), session: Session = Depends(db)):
        rows = list(session.scalars(select(ModelConfigRecord).order_by(ModelConfigRecord.priority, ModelConfigRecord.created_at)))
        return {"items": [ModelOut.model_validate(_model_payload(row)) for row in rows]}

    @app.post("/api/v1/generations", response_model=GenerationOut, status_code=201)
    def create_generation(payload: GenerationCreateIn, user: UserRecord = Depends(current_user), session: Session = Depends(db)):
        if payload.idempotency_key:
            existing = session.scalar(select(GenerationRecord).where(GenerationRecord.user_id == user.id, GenerationRecord.idempotency_key == payload.idempotency_key))
            if existing is not None:
                return _generation_payload(existing)
        template = session.scalar(select(TemplateRecord).where(TemplateRecord.id == payload.template_id, TemplateRecord.status == "published"))
        if template is None:
            raise AppError("TEMPLATE_NOT_FOUND", "模板不存在或尚未发布", 404)
        model_query = select(ModelConfigRecord).where(ModelConfigRecord.enabled.is_(True))
        if payload.model_id:
            model_query = model_query.where(ModelConfigRecord.model_id == payload.model_id)
        else:
            model_query = model_query.where(ModelConfigRecord.is_default.is_(True))
        model = session.scalar(model_query.order_by(ModelConfigRecord.priority))
        if model is None:
            raise AppError("MODEL_UNAVAILABLE", "当前没有可用的生图模型", 503)
        bindings = json.loads(model.module_bindings_json or "[]")
        if bindings and template.module_kind not in bindings:
            raise AppError("MODEL_MODULE_UNSUPPORTED", "该模型未绑定当前模块", 400)
        width, height, aspect_ratio = _resolve_generation_dimensions(template, payload)
        today = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        free_count = session.scalar(select(func.count(GenerationRecord.id)).where(GenerationRecord.user_id == user.id, GenerationRecord.status == "succeeded", GenerationRecord.free_quota_used.is_(True), GenerationRecord.created_at >= today)) or 0
        free_quota_used = free_count < 3
        points = model.points_per_success
        if not free_quota_used and user.points_balance < points:
            raise AppError("QUOTA_EXCEEDED", "今日免费额度已用完，当前积分不足", 402)
        if not free_quota_used:
            user.points_balance -= points
        prompt = _compose_prompt(template, payload.prompt)
        row = GenerationRecord(
            user_id=user.id,
            template_id=template.id,
            template_version_no=template.version_no,
            module_kind=template.module_kind,
            prompt_snapshot=prompt,
            aspect_ratio=aspect_ratio,
            output_width=width,
            output_height=height,
            model_id=model.model_id,
            provider=provider.name,
            status="running",
            points_charged=0 if free_quota_used else points,
            free_quota_used=free_quota_used,
            charge_status="reserved",
            idempotency_key=payload.idempotency_key,
        )
        session.add(row)
        session.flush()
        session.commit()
        started = time.monotonic()
        try:
            asset_path = settings.storage_root / "generations" / f"{row.id}.png"
            provider.generate(asset_path, width, height, template.title, prompt=prompt)
            row.status = "succeeded"
            row.asset_path = str(asset_path)
            row.elapsed_ms = round((time.monotonic() - started) * 1000)
            row.charge_status = "charged"
            row.cost_cents = model.cost_cents_per_call
            row.updated_at = _utcnow()
            session.add(AuditEvent(owner_id=user.id, actor_user_id=user.id, actor_role=user.role, entity_type="generation", entity_id=row.id, action="generation", result="succeeded", metadata_json=json.dumps({"template_id": row.template_id, "model_id": row.model_id, "aspect_ratio": row.aspect_ratio, "output_width": width, "output_height": height, "elapsed_ms": row.elapsed_ms, "cost_cents": row.cost_cents}, ensure_ascii=False)))
            session.commit()
        except Exception as exc:
            if not free_quota_used:
                user.points_balance += points
            row.status = "failed"
            row.error_code = "GENERATION_FAILED"
            row.charge_status = "refunded"
            row.elapsed_ms = round((time.monotonic() - started) * 1000)
            row.updated_at = _utcnow()
            session.add(AuditEvent(owner_id=user.id, actor_user_id=user.id, actor_role=user.role, entity_type="generation", entity_id=row.id, action="generation", result="failed", metadata_json=json.dumps({"error": type(exc).__name__}, ensure_ascii=False)))
            session.commit()
            raise AppError("GENERATION_FAILED", "生成失败，额度已返还，请稍后重试", 502) from exc
        return _generation_payload(row)

    @app.get("/api/v1/generations", response_model=GenerationListOut)
    def list_generations(user: UserRecord = Depends(current_user), session: Session = Depends(db)):
        rows = list(session.scalars(select(GenerationRecord).where(GenerationRecord.user_id == user.id).order_by(GenerationRecord.created_at.desc()).limit(50)))
        return {"items": [_generation_payload(row) for row in rows]}

    @app.get("/api/v1/generations/{generation_id}", response_model=GenerationOut)
    def get_generation(generation_id: str, user: UserRecord = Depends(current_user), session: Session = Depends(db)):
        row = session.scalar(select(GenerationRecord).where(GenerationRecord.id == generation_id, GenerationRecord.user_id == user.id))
        if row is None:
            raise AppError("NOT_FOUND", "生成任务不存在", 404)
        return _generation_payload(row)

    @app.get("/api/v1/generations/{generation_id}/asset")
    def get_generation_asset(generation_id: str, user: UserRecord = Depends(current_user), session: Session = Depends(db)):
        row = session.scalar(select(GenerationRecord).where(GenerationRecord.id == generation_id, GenerationRecord.user_id == user.id))
        if row is None or row.status != "succeeded" or not row.asset_path or not Path(row.asset_path).is_file():
            raise AppError("NOT_FOUND", "生成结果不存在", 404)
        return FileResponse(row.asset_path, media_type="image/png", filename=f"{generation_id}.png")

    @app.get("/api/v1/admin/templates")
    def admin_templates(user: UserRecord = Depends(require_operator), session: Session = Depends(db)):
        rows = list(session.scalars(select(TemplateRecord).order_by(TemplateRecord.created_at.desc())))
        return {"items": [_template_payload(row) for row in rows]}

    @app.post("/api/v1/admin/templates/import", status_code=201)
    def import_template(payload: TemplateImportIn, user: UserRecord = Depends(require_operator), session: Session = Depends(db)):
        if session.get(TemplateRecord, payload.template_id) is not None:
            raise AppError("TEMPLATE_EXISTS", "模板 ID 已存在", 409)
        now = _utcnow()
        row = TemplateRecord(
            id=payload.template_id,
            slug=payload.template_id,
            module_kind=payload.module_kind,
            title=payload.title,
            default_prompt=payload.default_prompt,
            prompt_key=payload.prompt_key,
            target_width=payload.target_width,
            target_height=payload.target_height,
            default_aspect_ratio=_ratio_for_dimensions(payload.target_width, payload.target_height),
            reference_image_url=payload.reference_image_url,
            source_platform=payload.source_platform,
            source_url=payload.source_url,
            source_type="manual",
            rights_status=payload.rights_status,
            status="candidate",
            version_no=1,
            created_by=user.id,
            updated_by=user.id,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.add(TemplateVersionRecord(template_id=row.id, version_no=1, prompt_snapshot=row.default_prompt, target_width=row.target_width, target_height=row.target_height, status="draft", created_by=user.id))
        session.add(AuditEvent(owner_id=user.id, actor_user_id=user.id, actor_role=user.role, entity_type="template", entity_id=row.id, action="template_import", result="candidate", metadata_json="{}"))
        session.commit()
        return _template_payload(row)

    @app.post("/api/v1/admin/templates/{template_id}/review")
    def review_template(template_id: str, payload: TemplateReviewIn, user: UserRecord = Depends(require_operator), session: Session = Depends(db)):
        row = session.get(TemplateRecord, template_id)
        if row is None:
            raise AppError("TEMPLATE_NOT_FOUND", "模板不存在", 404)
        if row.status not in {"candidate", "pending_review"}:
            raise AppError("INVALID_TEMPLATE_STATE", "当前模板状态不可审核")
        row.status = "approved" if payload.decision == "approve" else "rejected"
        row.reviewed_by = user.id
        row.reviewed_at = _utcnow()
        row.review_reason = payload.reason
        row.updated_by = user.id
        session.add(AuditEvent(owner_id=user.id, actor_user_id=user.id, actor_role=user.role, entity_type="template", entity_id=row.id, action="template_review", result=row.status, metadata_json=json.dumps({"reason": payload.reason}, ensure_ascii=False)))
        session.commit()
        return _template_payload(row)

    @app.post("/api/v1/admin/templates/{template_id}/publish")
    def publish_template(template_id: str, user: UserRecord = Depends(require_operator), session: Session = Depends(db)):
        row = session.get(TemplateRecord, template_id)
        if row is None:
            raise AppError("TEMPLATE_NOT_FOUND", "模板不存在", 404)
        if row.status != "approved":
            raise AppError("INVALID_TEMPLATE_STATE", "只有审核通过的模板才能发布")
        now = _utcnow()
        row.status = "published"
        row.published_at = now
        row.updated_by = user.id
        version = session.scalar(select(TemplateVersionRecord).where(TemplateVersionRecord.template_id == row.id, TemplateVersionRecord.version_no == row.version_no))
        if version is not None:
            version.status = "published"
            version.published_at = now
        session.add(AuditEvent(owner_id=user.id, actor_user_id=user.id, actor_role=user.role, entity_type="template", entity_id=row.id, action="template_publish", result="published", metadata_json="{}"))
        session.commit()
        return _template_payload(row)

    @app.post("/api/v1/uploads", response_model=UploadOut, status_code=201)
    async def upload_image(
        file: UploadFile = File(...),
        owner: str = Depends(owner_id),
        session: Session = Depends(db),
    ):
        content_type = file.content_type or ""
        data = await file.read()
        digest = validate_image(data, content_type, file.filename or "", settings.max_upload_bytes)
        upload_id = __import__("uuid").uuid4().hex
        path = store_upload(settings.storage_root, upload_id, file.filename or "upload.bin", data)
        record = UploadRecord(
            id=upload_id,
            owner_id=owner,
            original_name=Path(file.filename or "upload.bin").name,
            storage_path=str(path),
            content_type=content_type,
            bytes=len(data),
            sha256=digest,
            status="available",
        )
        session.add(record)
        session.add(AuditEvent(owner_id=owner, action="upload", result="accepted", metadata_json=json.dumps({"upload_id": upload_id})))
        session.commit()
        return UploadOut(
            upload_id=record.id,
            owner_id=record.owner_id,
            original_name=record.original_name,
            content_type=record.content_type,
            bytes=record.bytes,
            sha256=record.sha256,
            status=record.status,
        )

    @app.post("/api/v1/tasks", response_model=TaskOut, status_code=201)
    def create_task(
        payload: CreateTaskIn,
        owner: str = Depends(owner_id),
        session: Session = Depends(db),
    ):
        upload = session.scalar(select(UploadRecord).where(UploadRecord.id == payload.upload_id, UploadRecord.owner_id == owner))
        if upload is None or upload.status != "available":
            raise AppError("UPLOAD_NOT_FOUND", "上传文件不存在或已不可用", 404)
        template = find_template(load_templates(settings.template_library_path), payload.template_id)
        aspect_ratio = payload.aspect_ratio or template.get("default_aspect_ratio") or _ratio_for_dimensions(int(template["target_width"]), int(template["target_height"]))
        output_width, output_height = _resolve_output_size(template, aspect_ratio)
        task = TaskRecord(
            owner_id=owner,
            template_id=payload.template_id,
            upload_id=upload.id,
            status="running",
            provider=provider.name,
            aspect_ratio=aspect_ratio,
            output_width=output_width,
            output_height=output_height,
        )
        session.add(task)
        session.flush()
        _generate_version(session, task, template, provider, settings.storage_root, upload=upload, action="generate", width=output_width, height=output_height)
        versions = list(session.scalars(select(VersionRecord).where(VersionRecord.task_id == task.id).order_by(VersionRecord.version_no)))
        return _task_payload(task, versions)

    @app.post("/api/v1/tasks/{task_id}/regenerate", response_model=TaskOut, status_code=201)
    def regenerate_task(
        task_id: str,
        payload: RegenerateTaskIn,
        owner: str = Depends(owner_id),
        session: Session = Depends(db),
    ):
        task = session.scalar(select(TaskRecord).where(TaskRecord.id == task_id, TaskRecord.owner_id == owner))
        if task is None:
            raise AppError("NOT_FOUND", "任务不存在", 404)
        template_id = payload.template_id or task.template_id
        template = find_template(load_templates(settings.template_library_path), template_id)
        versions = list(session.scalars(select(VersionRecord).where(VersionRecord.task_id == task.id).order_by(VersionRecord.version_no)))
        task.template_id = template_id
        task.status = "running"
        task.attempts += 1
        aspect_ratio = payload.aspect_ratio or task.aspect_ratio or template.get("default_aspect_ratio") or _ratio_for_dimensions(int(template["target_width"]), int(template["target_height"]))
        output_width, output_height = _resolve_output_size(template, aspect_ratio)
        task.aspect_ratio = aspect_ratio
        task.output_width = output_width
        task.output_height = output_height
        _generate_version(session, task, template, provider, settings.storage_root, upload=None, action="regenerate", version_no=len(versions) + 1, width=output_width, height=output_height)
        versions = list(session.scalars(select(VersionRecord).where(VersionRecord.task_id == task.id).order_by(VersionRecord.version_no)))
        return _task_payload(task, versions)

    @app.get("/api/v1/audit", response_model=AuditListOut)
    def audit_events(owner: str = Depends(owner_id), session: Session = Depends(db)):
        rows = list(session.scalars(select(AuditEvent).where(AuditEvent.owner_id == owner).order_by(AuditEvent.created_at.desc()).limit(100)))
        return {
            "items": [
                AuditOut(
                    id=row.id,
                    task_id=row.task_id,
                    action=row.action,
                    result=row.result,
                    metadata=json.loads(row.metadata_json or "{}"),
                    created_at=row.created_at.isoformat(),
                )
                for row in rows
            ]
        }

    @app.get("/api/v1/tasks/{task_id}", response_model=TaskOut)
    def get_task(task_id: str, owner: str = Depends(owner_id), session: Session = Depends(db)):
        task = session.scalar(select(TaskRecord).where(TaskRecord.id == task_id, TaskRecord.owner_id == owner))
        if task is None:
            raise AppError("NOT_FOUND", "任务不存在", 404)
        versions = list(session.scalars(select(VersionRecord).where(VersionRecord.task_id == task.id).order_by(VersionRecord.version_no)))
        return _task_payload(task, versions)

    @app.get("/api/v1/assets/{version_id}")
    def get_asset(version_id: str, owner: str = Depends(owner_id), session: Session = Depends(db)):
        version = session.scalar(select(VersionRecord).where(VersionRecord.id == version_id))
        if version is None:
            raise AppError("NOT_FOUND", "产物不存在", 404)
        task = session.scalar(select(TaskRecord).where(TaskRecord.id == version.task_id, TaskRecord.owner_id == owner))
        if task is None or version.status != "succeeded" or not version.asset_path:
            raise AppError("NOT_FOUND", "产物不存在", 404)
        path = Path(version.asset_path)
        if not path.is_file():
            raise AppError("ASSET_UNAVAILABLE", "产物文件不可用", 404)
        return FileResponse(path, media_type="image/png", filename=f"{version_id}.png")

    return app


def _task_payload(task: TaskRecord, versions: list[VersionRecord]) -> dict:
    return {
        "task_id": task.id,
        "owner_id": task.owner_id,
        "template_id": task.template_id,
        "status": task.status,
        "provider": task.provider,
        "version_id": versions[-1].id if versions else None,
        "elapsed_ms": task.elapsed_ms,
        "cost_cents": task.cost_cents,
        "aspect_ratio": task.aspect_ratio,
        "output_width": task.output_width,
        "output_height": task.output_height,
        "versions": [
            VersionOut(
                id=version.id,
                version_no=version.version_no,
                status=version.status,
                provider=version.provider,
                asset_url=f"/api/v1/assets/{version.id}" if version.status == "succeeded" else None,
            )
            for version in versions
        ],
    }


def _generate_version(session: Session, task: TaskRecord, template: dict, provider, storage_root: Path, *, upload=None, action: str, version_no: int | None = None, width: int | None = None, height: int | None = None) -> VersionRecord:
    version = VersionRecord(task_id=task.id, version_no=version_no or 1, status="running", provider=provider.name)
    session.add(version)
    session.flush()
    started = time.monotonic()
    try:
        asset_path = storage_root / "assets" / f"{version.id}.png"
        output_width = width or int(template["target_width"])
        output_height = height or int(template["target_height"])
        provider.generate(asset_path, output_width, output_height, str(template["name"]))
        elapsed_ms = round((time.monotonic() - started) * 1000)
        version.status = "succeeded"
        version.asset_path = str(asset_path)
        task.status = "succeeded"
        task.elapsed_ms = elapsed_ms
        task.cost_cents = None
        task.updated_at = datetime.now(timezone.utc)
        if upload is not None:
            upload.status = "deleted"
            remove_file(upload.storage_path)
        session.add(AuditEvent(owner_id=task.owner_id, task_id=task.id, action=action, result="succeeded", metadata_json=json.dumps({"elapsed_ms": elapsed_ms, "cost_cents": None, "version_no": version.version_no, "aspect_ratio": task.aspect_ratio, "output_width": output_width, "output_height": output_height})))
        session.commit()
        return version
    except Exception as exc:
        session.rollback()
        raise AppError("GENERATION_FAILED", "生成失败，请稍后重试", 502) from exc


def _ratio_for_dimensions(width: int, height: int) -> str:
    ratio = width / height
    return min(ASPECT_RATIO_SIZES, key=lambda value: abs(ASPECT_RATIO_SIZES[value][0] / ASPECT_RATIO_SIZES[value][1] - ratio))


def _compose_prompt(template: TemplateRecord, user_prompt: str) -> str:
    base = (template.default_prompt or template.title).strip()
    extra = user_prompt.strip()
    return f"{base}\n用户要求：{extra}" if extra else base


def _resolve_generation_dimensions(template: TemplateRecord, payload: GenerationCreateIn) -> tuple[int, int, str]:
    if (payload.width is None) != (payload.height is None):
        raise AppError("INVALID_SIZE", "自定义尺寸必须同时填写宽和高", 400)
    if payload.width is not None and payload.height is not None:
        ratio_value = payload.width / payload.height
        if not 0.25 <= ratio_value <= 4.0:
            raise AppError("INVALID_SIZE", "尺寸比例必须在 0.25 到 4.0 之间", 400)
        return payload.width, payload.height, f"{payload.width}:{payload.height}"
    ratio = payload.aspect_ratio or template.default_aspect_ratio or _ratio_for_dimensions(template.target_width, template.target_height)
    if ratio not in ASPECT_RATIO_SIZES:
        raise AppError("INVALID_ASPECT_RATIO", "输出比例不在支持范围内", 400)
    if ratio == template.default_aspect_ratio:
        return template.target_width, template.target_height, ratio
    if template.module_kind == "sticker" and ratio == "1:1":
        return 512, 512, ratio
    width, height = ASPECT_RATIO_SIZES[ratio]
    return width, height, ratio


def _resolve_output_size(template: dict, aspect_ratio: str) -> tuple[int, int]:
    if aspect_ratio not in ASPECT_RATIO_SIZES:
        raise AppError("INVALID_ASPECT_RATIO", "输出比例不在支持范围内", 400)
    if aspect_ratio == template.get("default_aspect_ratio"):
        return int(template["target_width"]), int(template["target_height"])
    if template.get("kind") == "sticker" and aspect_ratio == "1:1":
        return 512, 512
    return ASPECT_RATIO_SIZES[aspect_ratio]


app = create_app()
