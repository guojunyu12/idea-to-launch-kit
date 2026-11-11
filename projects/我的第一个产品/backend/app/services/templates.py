from __future__ import annotations

import json
from pathlib import Path

from app.core.errors import AppError


def load_templates(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AppError("TEMPLATE_LIBRARY_ERROR", "模板库暂时不可用", 500) from exc
    if not isinstance(data, list):
        raise AppError("TEMPLATE_LIBRARY_ERROR", "模板库格式无效", 500)
    return data


def find_template(templates: list[dict], template_id: str) -> dict:
    for item in templates:
        if item.get("template_id") == template_id:
            return item
    raise AppError("TEMPLATE_NOT_FOUND", "模板不存在", 404)
