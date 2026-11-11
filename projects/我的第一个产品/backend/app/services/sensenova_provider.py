from __future__ import annotations

import base64
import time
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageOps


class SenseNovaProvider:
    name = "sensenova"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 120.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = model
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)

    def generate(self, output_path: Path, width: int, height: int, label: str) -> None:
        request_size = _supported_size(width, height)
        request = {
            "model": self.model,
            "prompt": _prompt_for(label),
            "size": request_size,
            "n": 1,
        }
        response = self._post_with_retries(request)
        payload = response.json()
        try:
            result = payload["data"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("商汤接口没有返回图片地址") from exc
        if result.get("b64_json"):
            try:
                image_bytes = base64.b64decode(result["b64_json"], validate=True)
            except (ValueError, TypeError) as exc:
                raise RuntimeError("商汤返回的 base64 图片无效") from exc
        elif result.get("url"):
            image_response = self._get_with_retries(result["url"])
            image_response.raise_for_status()
            image_bytes = image_response.content
        else:
            raise RuntimeError("商汤接口没有返回图片地址")
        try:
            with Image.open(BytesIO(image_bytes)) as image:
                normalized = ImageOps.fit(image.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                normalized.save(output_path, format="PNG")
        except Exception as exc:
            raise RuntimeError("商汤返回的图片无法解码") from exc

    def _post_with_retries(self, payload: dict) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        return self._request_with_retries(
            lambda: httpx.post(
                f"{self.base_url}/images/generations",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        )

    def _get_with_retries(self, url: str) -> httpx.Response:
        return self._request_with_retries(lambda: httpx.get(url, timeout=self.timeout))

    def _request_with_retries(self, request) -> httpx.Response:
        retryable_statuses = {429, 500, 502, 503, 504}
        for attempt in range(self.max_retries + 1):
            try:
                response = request()
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise RuntimeError("商汤接口网络请求失败") from exc
            else:
                if response.status_code not in retryable_statuses:
                    response.raise_for_status()
                    return response
                if attempt >= self.max_retries:
                    response.raise_for_status()
            time.sleep(self.retry_backoff_seconds * (2**attempt))
        raise RuntimeError("商汤接口请求失败")


def _supported_size(width: int, height: int) -> str:
    ratio = width / height
    options = {
        "1664x2496": 1664 / 2496,
        "2496x1664": 2496 / 1664,
        "1760x2368": 1760 / 2368,
        "2368x1760": 2368 / 1760,
        "1824x2272": 1824 / 2272,
        "2272x1824": 2272 / 1824,
        "2048x2048": 1,
        "2752x1536": 2752 / 1536,
        "1536x2752": 1536 / 2752,
        "3072x1376": 3072 / 1376,
        "1344x3136": 1344 / 3136,
    }
    return min(options, key=lambda size: abs(options[size] - ratio))


def _prompt_for(label: str) -> str:
    return (
        f"生成一张{label}，适合移动端分享和保存。构图完整，主体清晰，色彩协调，"
        "不出现水印、乱码或多余边框，画面保持干净，使用中文视觉设计语境。"
    )
