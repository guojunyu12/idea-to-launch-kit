from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app


def image_bytes(fmt: str = "PNG") -> bytes:
    buf = BytesIO()
    Image.new("RGB", (32, 32), (80, 120, 200)).save(buf, format=fmt)
    return buf.getvalue()


def login(client, email: str = "v7-user@example.com"):
    challenge = client.post("/api/v1/auth/request-code", json={"email": email}).json()
    response = client.post(
        "/api/v1/auth/verify-code",
        json={"challenge_id": challenge["challenge_id"], "email": email, "code": "000000"},
    )
    assert response.status_code == 200
    return response.json()["user"]


@pytest.fixture()
def client(tmp_path):
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        storage_root=tmp_path / "storage",
    )
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint_reports_ready(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_test_console_page_is_available(client):
    response = client.get("/test")
    assert response.status_code == 200
    assert "图个乐 · 生成测试台" in response.text
    assert "api/v1/uploads" in response.text


def test_templates_can_be_filtered_by_kind(client):
    response = client.get("/api/v1/templates", params={"kind": "wallpaper"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert all(item["kind"] == "wallpaper" for item in payload["items"])


def test_v7_generation_requires_login_and_lists_models(client):
    assert client.get("/api/v1/models").status_code == 200
    response = client.post("/api/v1/generations", json={"template_id": "sticker-laugh", "prompt": "开心"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_v7_generation_uses_prompt_size_and_returns_owner_scoped_asset(client):
    login(client)
    response = client.post(
        "/api/v1/generations",
        json={"template_id": "sticker-laugh", "prompt": "蓝色背景和夸张笑脸", "width": 640, "height": 640, "idempotency_key": "v7-1"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["output_width"] == 640
    assert payload["output_height"] == 640
    assert "蓝色背景" in payload["prompt"]
    assert payload["free_quota_used"] is True
    assert client.get(payload["asset_url"]).status_code == 200
    login(client, "another-v7-user@example.com")
    assert client.get(f"/api/v1/generations/{payload['generation_id']}").status_code == 404


def test_v7_generation_idempotency_does_not_call_twice(client):
    login(client, "idempotent@example.com")
    body = {"template_id": "sticker-laugh", "prompt": "同一个任务", "idempotency_key": "same-request"}
    first = client.post("/api/v1/generations", json=body)
    second = client.post("/api/v1/generations", json=body)
    assert first.status_code == second.status_code == 201
    assert first.json()["generation_id"] == second.json()["generation_id"]
    assert len(client.get("/api/v1/generations").json()["items"]) == 1


def test_upload_rejects_non_image_content_with_uniform_error(client):
    response = client.post(
        "/api/v1/uploads",
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_UPLOAD"
    assert set(response.json()) == {"error"}


def test_upload_persists_owner_scoped_metadata(client):
    response = client.post(
        "/api/v1/uploads",
        headers={"X-Owner-ID": "owner-a"},
        files={"file": ("portrait.png", image_bytes(), "image/png")},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["owner_id"] == "owner-a"
    assert payload["content_type"] == "image/png"
    assert payload["bytes"] > 0
    assert payload["upload_id"]


def test_create_mock_task_returns_persisted_result(client):
    upload = client.post(
        "/api/v1/uploads",
        headers={"X-Owner-ID": "owner-a"},
        files={"file": ("portrait.png", image_bytes(), "image/png")},
    ).json()
    response = client.post(
        "/api/v1/tasks",
        headers={"X-Owner-ID": "owner-a"},
        json={"template_id": "wallpaper-sunrise", "upload_id": upload["upload_id"]},
    )
    assert response.status_code == 201
    task = response.json()
    assert task["status"] == "succeeded"
    assert task["provider"] == "mock"
    assert task["version_id"]

    fetched = client.get(
        f"/api/v1/tasks/{task['task_id']}",
        headers={"X-Owner-ID": "owner-a"},
    )
    assert fetched.status_code == 200
    assert fetched.json()["task_id"] == task["task_id"]
    assert fetched.json()["versions"][0]["status"] == "succeeded"


def test_create_task_accepts_aspect_ratio_and_returns_output_size(client):
    upload = client.post(
        "/api/v1/uploads",
        headers={"X-Owner-ID": "owner-a"},
        files={"file": ("portrait.png", image_bytes(), "image/png")},
    ).json()
    response = client.post(
        "/api/v1/tasks",
        headers={"X-Owner-ID": "owner-a"},
        json={"template_id": "wallpaper-sunrise", "upload_id": upload["upload_id"], "aspect_ratio": "9:16"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["aspect_ratio"] == "9:16"
    assert (payload["output_width"], payload["output_height"]) == (1536, 2752)


def test_create_task_rejects_unknown_aspect_ratio(client):
    upload = client.post(
        "/api/v1/uploads",
        headers={"X-Owner-ID": "owner-a"},
        files={"file": ("portrait.png", image_bytes(), "image/png")},
    ).json()
    response = client.post(
        "/api/v1/tasks",
        headers={"X-Owner-ID": "owner-a"},
        json={"template_id": "sticker-laugh", "upload_id": upload["upload_id"], "aspect_ratio": "9:6"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ASPECT_RATIO"


def test_task_cannot_be_read_by_another_owner(client):
    upload = client.post(
        "/api/v1/uploads",
        headers={"X-Owner-ID": "owner-a"},
        files={"file": ("portrait.png", image_bytes(), "image/png")},
    ).json()
    task = client.post(
        "/api/v1/tasks",
        headers={"X-Owner-ID": "owner-a"},
        json={"template_id": "sticker-laugh", "upload_id": upload["upload_id"]},
    ).json()
    response = client.get(
        f"/api/v1/tasks/{task['task_id']}",
        headers={"X-Owner-ID": "owner-b"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_regenerate_creates_history_version_and_updates_template(client):
    upload = client.post(
        "/api/v1/uploads",
        headers={"X-Owner-ID": "owner-a"},
        files={"file": ("portrait.png", image_bytes(), "image/png")},
    ).json()
    task = client.post(
        "/api/v1/tasks",
        headers={"X-Owner-ID": "owner-a"},
        json={"template_id": "sticker-laugh", "upload_id": upload["upload_id"]},
    ).json()

    regenerated = client.post(
        f"/api/v1/tasks/{task['task_id']}/regenerate",
        headers={"X-Owner-ID": "owner-a"},
        json={"template_id": "wallpaper-sunrise"},
    )

    assert regenerated.status_code == 201
    payload = regenerated.json()
    assert payload["template_id"] == "wallpaper-sunrise"
    assert len(payload["versions"]) == 2
    assert payload["versions"][-1]["version_no"] == 2
    assert payload["elapsed_ms"] >= 0


def test_audit_events_are_owner_scoped(client):
    upload = client.post(
        "/api/v1/uploads",
        headers={"X-Owner-ID": "owner-a"},
        files={"file": ("portrait.png", image_bytes(), "image/png")},
    ).json()
    task = client.post(
        "/api/v1/tasks",
        headers={"X-Owner-ID": "owner-a"},
        json={"template_id": "sticker-laugh", "upload_id": upload["upload_id"]},
    ).json()

    own = client.get("/api/v1/audit", headers={"X-Owner-ID": "owner-a"})
    other = client.get("/api/v1/audit", headers={"X-Owner-ID": "owner-b"})

    assert own.status_code == 200
    assert any(item["task_id"] == task["task_id"] for item in own.json()["items"])
    assert other.status_code == 200
    assert other.json()["items"] == []
