from __future__ import annotations

import time
from pathlib import Path
from io import BytesIO

import httpx
from PIL import Image, ImageOps


class QwenImageProvider:
    """DashScope native synchronous adapter for qwen-image-2.1-turbo."""

    name = "qwen-image-2.1-turbo"

    def __init__(self, api_key: str, endpoint: str, model: str, timeout: float = 600.0, max_retries: int = 1, retry_backoff_seconds: float = 1.0):
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self.name = model
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)

    def generate(self, output_path: Path, width: int, height: int, label: str) -> None:
        request = {
            "model": self.model,
            "input": {
                "messages": [{"role": "user", "content": [{"text": _prompt_for(label)}]}]
            },
            "parameters": {"size": _supported_size(width, height), "prompt_extend": False},
        }
        response = self._post_with_retries(request)
        payload = response.json()
        try:
            content = payload["output"]["choices"][0]["message"]["content"]
            image_url = next(item["image"] for item in content if item.get("image"))
        except (KeyError, IndexError, TypeError, StopIteration) as exc:
            raise RuntimeError("千问接口没有返回图片地址") from exc
        image_response = httpx.get(image_url, timeout=self.timeout)
        image_response.raise_for_status()
        try:
            with Image.open(BytesIO(image_response.content)) as image:
                normalized = ImageOps.fit(image.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                normalized.save(output_path, format="PNG")
        except Exception as exc:
            raise RuntimeError("千问返回的图片无法解码") from exc

    def _post_with_retries(self, payload: dict) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        retryable = {429, 500, 502, 503, 504}
        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.post(self.endpoint, headers=headers, json=payload, timeout=self.timeout)
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise RuntimeError("千问接口网络请求失败") from exc
                time.sleep(self.retry_backoff_seconds * (2**attempt))
                continue
            if response.status_code not in retryable:
                response.raise_for_status()
                return response
            if attempt >= self.max_retries:
                response.raise_for_status()
            time.sleep(self.retry_backoff_seconds * (2**attempt))
        raise RuntimeError("千问接口请求失败")


def _supported_size(width: int, height: int) -> str:
    options = {
        "512*512": 1,
        "1024*1024": 1,
        "1536*864": 1536 / 864,
        "864*1536": 864 / 1536,
        "1536*1024": 1536 / 1024,
        "1024*1536": 1024 / 1536,
        "1792*1024": 1792 / 1024,
        "1024*1792": 1024 / 1792,
        "2048*1024": 2,
        "1024*2048": 0.5,
        "1728*1152": 1.5,
        "1152*1728": 1152 / 1728,
    }
    ratio = width / height
    return min(options, key=lambda size: abs(options[size] - ratio))


def _prompt_for(label: str) -> str:
    return f"生成一张{label}，构图完整，主体清晰，色彩协调，不出现水印、乱码或多余边框，画面干净。"
