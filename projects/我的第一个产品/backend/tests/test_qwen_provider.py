from io import BytesIO

from PIL import Image

from app.services.qwen_image_provider import QwenImageProvider, _supported_size


class _Response:
    def __init__(self, payload=None, content=b""):
        self._payload = payload
        self.content = content
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_qwen_provider_uses_dashscope_nested_payload_and_normalizes(monkeypatch, tmp_path):
    image = BytesIO()
    Image.new("RGB", (64, 64), (120, 80, 20)).save(image, format="PNG")
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(json)
        return _Response({"output": {"choices": [{"message": {"content": [{"image": "https://example.test/image.png"}]}}]}})

    monkeypatch.setattr("app.services.qwen_image_provider.httpx.post", fake_post)
    monkeypatch.setattr("app.services.qwen_image_provider.httpx.get", lambda url, timeout: _Response(content=image.getvalue()))
    output = tmp_path / "result.png"
    QwenImageProvider("test", "https://example.test/generation", "qwen-image-2.1-turbo").generate(output, 1179, 2556, "日出手机壁纸")

    assert output.exists()
    with Image.open(output) as result:
        assert result.size == (1179, 2556)
    assert calls[0]["model"] == "qwen-image-2.1-turbo"
    assert calls[0]["input"]["messages"][0]["content"][0]["text"]
    assert "*" in calls[0]["parameters"]["size"]


def test_qwen_supported_size_stays_within_qwen_resolution_limits():
    assert _supported_size(1179, 2556) == "1024*2048"
