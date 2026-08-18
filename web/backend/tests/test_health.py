from fastapi.testclient import TestClient
from pytest import MonkeyPatch


def test_health_endpoint(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("APP_ENV", "test")

    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "pipeerp-api"}
