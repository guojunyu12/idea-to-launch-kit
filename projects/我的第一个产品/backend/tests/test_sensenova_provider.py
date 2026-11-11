import base64
from io import BytesIO

import httpx
import pytest
from PIL import Image

from app.services.sensenova_provider import SenseNovaProvider


class FakeResponse:
    def __init__(self, payload=None, content=b"", status_code=200):
        self._payload = payload
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def image_content(size=(1536, 2752)):
    buf = BytesIO()
    Image.new("RGB", size, (240, 180, 80)).save(buf, format="PNG")
    return buf.getvalue()


def test_sensenova_posts_supported_size_and_normalizes_result(monkeypatch, tmp_path):
    calls = {}

    def fake_post(url, *, headers, json, timeout):
        calls.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse({"data": [{"url": "https://cdn.example/result.png"}]})

    def fake_get(url, *, timeout):
        calls["download_url"] = url
        return FakeResponse(content=image_content())

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    output = tmp_path / "result.png"
    provider = SenseNovaProvider(api_key="sk-test", base_url="https://token.sensenova.cn/v1", model="sensenova-u1-fast", timeout=30)

    provider.generate(output, 1179, 2556, "日出手机壁纸")

    assert calls["url"] == "https://token.sensenova.cn/v1/images/generations"
    assert calls["headers"]["Authorization"] == "Bearer sk-test"
    assert calls["json"]["model"] == "sensenova-u1-fast"
    assert calls["json"]["size"] == "1344x3136"
    assert calls["download_url"] == "https://cdn.example/result.png"
    with Image.open(output) as image:
        assert image.size == (1179, 2556)


def test_sensenova_requires_result_url(monkeypatch, tmp_path):
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: FakeResponse({"data": []}))
    provider = SenseNovaProvider(api_key="sk-test", base_url="https://token.sensenova.cn/v1", model="sensenova-u1-fast", timeout=30)

    with pytest.raises(RuntimeError, match="没有返回图片地址"):
        provider.generate(tmp_path / "result.png", 512, 512, "大笑表情包")


def test_sensenova_accepts_base64_result(monkeypatch, tmp_path):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse({"data": [{"b64_json": base64.b64encode(image_content((2048, 2048))).decode()}]}),
    )
    output = tmp_path / "result.png"
    provider = SenseNovaProvider(api_key="sk-test", base_url="https://token.sensenova.cn/v1", model="sensenova-u1.5-lite", timeout=30)

    provider.generate(output, 512, 512, "大笑表情包")

    with Image.open(output) as image:
        assert image.size == (512, 512)


def test_sensenova_retries_transient_generation_error(monkeypatch, tmp_path):
    responses = [
        FakeResponse({"error": {"code": "quota_exceeded_error"}}, status_code=429),
        FakeResponse({"data": [{"b64_json": base64.b64encode(image_content((2048, 2048))).decode()}]}),
    ]
    calls = {"post": 0, "sleep": []}

    def fake_post(*args, **kwargs):
        calls["post"] += 1
        return responses.pop(0)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("app.services.sensenova_provider.time.sleep", lambda value: calls["sleep"].append(value))
    output = tmp_path / "result.png"
    provider = SenseNovaProvider(
        api_key="sk-test",
        base_url="https://token.sensenova.cn/v1",
        model="sensenova-u1.5-lite",
        timeout=30,
        retry_backoff_seconds=0,
    )

    provider.generate(output, 512, 512, "大笑表情包")

    assert calls["post"] == 2
    assert calls["sleep"] == [0]
