import os

from fastapi.testclient import TestClient

from app.main import create_app


def _client(tmp_path, monkeypatch, *, admins="admin@example.com", operators="ops@example.com"):
    monkeypatch.setenv("AUTH_MODE", "dev_fixed")
    monkeypatch.setenv("AUTH_DEV_CODE", "000000")
    monkeypatch.setenv("ADMIN_EMAILS", admins)
    monkeypatch.setenv("OPERATOR_EMAILS", operators)
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'v7.db'}",
        storage_root=tmp_path / "storage",
    )
    return TestClient(app)


def login(client, email: str):
    requested = client.post("/api/v1/auth/request-code", json={"email": email})
    assert requested.status_code == 200
    challenge_id = requested.json()["challenge_id"]
    verified = client.post(
        "/api/v1/auth/verify-code",
        json={"challenge_id": challenge_id, "email": email, "code": "000000"},
    )
    assert verified.status_code == 200
    return verified.json()["user"]


def test_email_code_login_sets_http_only_cookie_and_maps_whitelist_role(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        user = login(client, " Admin@Example.com ")
        assert user["email"] == "admin@example.com"
        assert user["role"] == "admin"
        assert "aigc_session" in client.cookies
        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["id"] == user["id"]


def test_regular_user_cannot_review_or_publish_templates(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        login(client, "user@example.com")
        response = client.get("/api/v1/admin/templates")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ROLE_FORBIDDEN"


def test_template_candidate_is_hidden_until_review_and_publish(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        login(client, "ops@example.com")
        created = client.post(
            "/api/v1/admin/templates/import",
            json={
                "template_id": "v7-candidate",
                "title": "V7 候选",
                "module_kind": "desktop_wallpaper",
                "target_width": 3072,
                "target_height": 1376,
                "source_platform": "manual",
                "source_url": "https://example.com/template",
                "rights_status": "cleared",
            },
        )
        assert created.status_code == 201
        assert created.json()["status"] == "candidate"
        assert not any(item["template_id"] == "v7-candidate" for item in client.get("/api/v1/templates").json()["items"])

        reviewed = client.post(
            "/api/v1/admin/templates/v7-candidate/review",
            json={"decision": "approve", "reason": "来源和版权已核对"},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "approved"
        published = client.post("/api/v1/admin/templates/v7-candidate/publish")
        assert published.status_code == 200
        assert published.json()["status"] == "published"
        public = client.get("/api/v1/templates", params={"module": "desktop_wallpaper"})
        assert any(item["template_id"] == "v7-candidate" for item in public.json()["items"])


def test_invalid_code_is_uniform_and_challenge_is_single_use(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        requested = client.post("/api/v1/auth/request-code", json={"email": "user@example.com"})
        payload = requested.json()
        wrong = client.post(
            "/api/v1/auth/verify-code",
            json={"challenge_id": payload["challenge_id"], "email": "user@example.com", "code": "111111"},
        )
        assert wrong.status_code == 401
        assert set(wrong.json()) == {"error"}
        right = client.post(
            "/api/v1/auth/verify-code",
            json={"challenge_id": payload["challenge_id"], "email": "user@example.com", "code": "000000"},
        )
        assert right.status_code == 200
        reused = client.post(
            "/api/v1/auth/verify-code",
            json={"challenge_id": payload["challenge_id"], "email": "user@example.com", "code": "000000"},
        )
        assert reused.status_code == 401
        assert reused.json()["error"]["code"] == "CODE_ALREADY_USED"

