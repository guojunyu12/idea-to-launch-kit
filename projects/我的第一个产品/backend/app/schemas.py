from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EmailCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class EmailCodeVerify(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=36)
    email: str = Field(min_length=3, max_length=320)
    code: str = Field(min_length=4, max_length=12)


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    status: str


class UserEnvelope(BaseModel):
    user: UserOut


class TemplateImportIn(BaseModel):
    template_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=255)
    module_kind: str = Field(pattern="^(sticker|mobile_wallpaper|desktop_wallpaper)$")
    target_width: int = Field(gt=0, le=10000)
    target_height: int = Field(gt=0, le=10000)
    default_prompt: str = Field(default="", max_length=4096)
    prompt_key: str = Field(default="", max_length=160)
    reference_image_url: str | None = Field(default=None, max_length=1000)
    source_platform: str = Field(min_length=1, max_length=120)
    source_url: str | None = Field(default=None, max_length=2000)
    rights_status: str = Field(default="pending", max_length=40)


class TemplateReviewIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    reason: str = Field(default="", max_length=1000)


class TemplateOut(BaseModel):
    template_id: str
    name: str
    kind: str
    target_width: int
    target_height: int
    prompt_key: str
    reference_image_url: str | None = None
    default_aspect_ratio: str | None = None
    module_kind: str | None = None
    status: str | None = None
    version_no: int | None = None


class TemplateListOut(BaseModel):
    items: list[TemplateOut]


class UploadOut(BaseModel):
    upload_id: str
    owner_id: str
    original_name: str
    content_type: str
    bytes: int
    sha256: str
    status: str


class CreateTaskIn(BaseModel):
    template_id: str = Field(min_length=1, max_length=120)
    upload_id: str = Field(min_length=1, max_length=36)
    aspect_ratio: str | None = Field(default=None, max_length=20)


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_id: str = Field(alias="id")
    version_no: int
    status: str
    provider: str
    asset_url: str | None = None


class TaskOut(BaseModel):
    task_id: str
    owner_id: str
    template_id: str
    status: str
    provider: str
    version_id: str | None = None
    versions: list[VersionOut] = []
    elapsed_ms: int | None = None
    cost_cents: int | None = None
    aspect_ratio: str | None = None
    output_width: int | None = None
    output_height: int | None = None


class RegenerateTaskIn(BaseModel):
    template_id: str | None = Field(default=None, min_length=1, max_length=120)
    aspect_ratio: str | None = Field(default=None, max_length=20)


class AuditOut(BaseModel):
    id: str
    task_id: str | None = None
    action: str
    result: str
    metadata: dict = {}
    created_at: str


class AuditListOut(BaseModel):
    items: list[AuditOut]
