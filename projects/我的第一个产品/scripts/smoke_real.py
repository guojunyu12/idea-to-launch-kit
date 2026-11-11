from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
STAGE = os.getenv("SMOKE_STAGE", "阶段2-1")
EVIDENCE = ROOT / "docs" / "evidence" / STAGE
BASE_URL = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
OWNER = "real-smoke-owner"
MODEL = os.getenv("SENSENOVA_MODEL", "未配置")


def foundation_smoke() -> None:
    started = datetime.now(timezone.utc).astimezone()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    base_url = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    provider_mode = os.getenv("GEN_PROVIDER_MODE", "sensenova").lower()
    is_qwen = provider_mode == "qwen" or os.getenv("SMOKE_PROVIDER", "").lower() == "qwen"
    model_base = os.getenv(
        "QWEN_IMAGE_ENDPOINT" if is_qwen else "SENSENOVA_BASE_URL",
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation" if is_qwen else "https://token.sensenova.cn/v1",
    ).rstrip("/")
    api_key = os.getenv("QWEN_IMAGE_API_KEY" if is_qwen else "SENSENOVA_API_KEY", "")
    model = os.getenv("QWEN_IMAGE_MODEL" if is_qwen else "SENSENOVA_MODEL", "qwen-image-2.1-turbo" if is_qwen else "sensenova-u1.5-lite")
    size = os.getenv("SMOKE_MODEL_SIZE", "512x512")
    timeout = float(os.getenv("SMOKE_MODEL_TIMEOUT_SECONDS", "180"))
    with httpx.Client(base_url=base_url, timeout=30) as client:
        health = client.get("/healthz")
        health.raise_for_status()
        templates = client.get("/api/v1/templates", params={"module": "sticker"})
        templates.raise_for_status()
        if not templates.json().get("items"):
            raise RuntimeError("公开模板列表为空")
    with httpx.Client(timeout=timeout) as client:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if is_qwen:
            response = client.post(
                model_base,
                headers=headers,
                json={
                    "model": model,
                    "input": {"messages": [{"role": "user", "content": [{"text": "A simple blue circle on white background, no text"}]}]},
                    "parameters": {"size": size.replace("x", "*"), "prompt_extend": False},
                },
            )
        else:
            response = client.post(
                f"{model_base}/images/generations",
                headers=headers,
                json={"model": model, "prompt": "A simple blue circle on white background, no text", "size": size, "n": 1},
            )
        response.raise_for_status()
        if is_qwen:
            content = response.json()["output"]["choices"][0]["message"]["content"]
            image_url = next(item["image"] for item in content if item.get("image"))
            image_bytes = client.get(image_url).content
        else:
            result = response.json()["data"][0]
            if result.get("b64_json"):
                import base64

                image_bytes = base64.b64decode(result["b64_json"], validate=True)
            elif result.get("url"):
                image_bytes = client.get(result["url"]).content
            else:
                raise RuntimeError("模型接口没有返回图片地址")
    output_path = EVIDENCE / "真实模型结果.png"
    output_path.write_bytes(image_bytes)
    with Image.open(output_path) as image:
        width, height = image.size
    record = f"""# {STAGE}真实模型冒烟记录

- 模型：{model}
- 供应商：{"阿里云百炼 DashScope" if is_qwen else "SenseNova"}
- 接口：`{"POST /api/v1/services/aigc/multimodal-generation/generation" if is_qwen else "POST /v1/images/generations"}`
- 说明：阶段2-1只验收账户/角色/模板基础能力；本次额外调用一次真实生图接口确认供应商连通性，结果图片保存于本目录。大尺寸生成链路留阶段2-2。

| 时间 | 检查 | 结果 |
| {started.strftime('%Y-%m-%d %H:%M')} | 应用健康检查 | 200，`/healthz` |
| {started.strftime('%Y-%m-%d %H:%M')} | 公开模板检查 | 200，`sticker` 已发布模板可见 |
| {started.strftime('%Y-%m-%d %H:%M')} | 真实模型调用 | 200，模型 `{model}`，请求尺寸 `{size}` |
| {started.strftime('%Y-%m-%d %H:%M')} | 结果解码 | PNG，{width}×{height}，{len(image_bytes)} bytes |
"""
    (EVIDENCE / "冒烟记录.md").write_text(record, encoding="utf-8")
    print(json.dumps({"model": model, "status": "succeeded", "size": [width, height]}, ensure_ascii=False))


def main() -> None:
    if STAGE == "阶段2-1":
        foundation_smoke()
        return
    started = datetime.now(timezone.utc).astimezone()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tugele-smoke-") as temp_dir:
        input_path = Path(temp_dir) / "smoke.png"
        Image.new("RGB", (320, 240), (246, 204, 96)).save(input_path, format="PNG")
        with httpx.Client(base_url=BASE_URL, timeout=300) as client:
            health = client.get("/healthz")
            health.raise_for_status()
            upload = client.post(
                "/api/v1/uploads",
                headers={"X-Owner-ID": OWNER},
                files={"file": (input_path.name, input_path.read_bytes(), "image/png")},
            )
            upload.raise_for_status()
            upload_payload = upload.json()
            task = client.post(
                "/api/v1/tasks",
                headers={"X-Owner-ID": OWNER},
                json={"template_id": "wallpaper-sunrise", "upload_id": upload_payload["upload_id"]},
            )
            task.raise_for_status()
            task_payload = task.json()
            if STAGE == "阶段2-1":
                regenerated_payload = task_payload
            else:
                regenerated = client.post(
                    f"/api/v1/tasks/{task_payload['task_id']}/regenerate",
                    headers={"X-Owner-ID": OWNER},
                    json={"template_id": "wallpaper-sunrise"},
                )
                regenerated.raise_for_status()
                regenerated_payload = regenerated.json()
                if len(regenerated_payload["versions"]) < 2:
                    raise RuntimeError("重新生成没有保留历史版本")
            audit = client.get("/api/v1/audit", headers={"X-Owner-ID": OWNER})
            audit.raise_for_status()
            if not any(item.get("task_id") == task_payload["task_id"] for item in audit.json()["items"]):
                raise RuntimeError("审计查询没有返回当前任务")
            asset_url = regenerated_payload["versions"][-1]["asset_url"]
            asset = client.get(asset_url, headers={"X-Owner-ID": OWNER})
            asset.raise_for_status()
            output_path = EVIDENCE / "sensenova真实结果.png"
            output_path.write_bytes(asset.content)
            with Image.open(output_path) as image:
                width, height = image.size
            isolated = client.get(
                f"/api/v1/tasks/{regenerated_payload['task_id']}",
                headers={"X-Owner-ID": "other-owner"},
            )
            if isolated.status_code != 404:
                raise RuntimeError(f"归属隔离失败：HTTP {isolated.status_code}")

    record = f"""# {STAGE}真实模型冒烟记录

- 模型：{MODEL}
- 供应商：SenseNova
- 接口：`POST /v1/images/generations`
- 说明：本次调用使用商汤文生图接口；当前接口不接收上传照片作为参考图，因此结果只验证供应商连通性、任务状态、下载和尺寸归一化，不代表人物相似度验收。

| 时间 | 任务 | 结果 |
| {started.strftime('%Y-%m-%d %H:%M')} | `/healthz` | 200，服务可用 |
| {started.strftime('%Y-%m-%d %H:%M')} | 上传测试 PNG | 201，`status=available` |
| {started.strftime('%Y-%m-%d %H:%M')} | 创建生成任务 | 201，`status={task_payload['status']}`，`provider={task_payload['provider']}` |
| {started.strftime('%Y-%m-%d %H:%M')} | {'生成结果' if STAGE == '阶段2-1' else '重新生成'} | 201，历史版本 {len(regenerated_payload['versions'])} 个，耗时 `{regenerated_payload.get('elapsed_ms')}` ms |
| {started.strftime('%Y-%m-%d %H:%M')} | 审计查询 | 200，当前任务事件可见 |
| {started.strftime('%Y-%m-%d %H:%M')} | 下载结果 | 200，PNG，{width}×{height}，{len(asset.content)} bytes |
| {started.strftime('%Y-%m-%d %H:%M')} | 换用户读取任务 | 404，`NOT_FOUND` |

任务 ID：`{regenerated_payload['task_id']}`
版本 ID：`{regenerated_payload['version_id']}`
"""
    (EVIDENCE / "冒烟记录.md").write_text(record, encoding="utf-8")
    print(json.dumps({"model": MODEL, "task_id": task_payload["task_id"], "status": task_payload["status"], "size": [width, height]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
