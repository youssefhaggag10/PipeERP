import os
from secrets import token_urlsafe

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", token_urlsafe(48))
os.environ.setdefault("APP_ENV", "test")

from app.infrastructure.database.session import get_database_session


def test_health_endpoint(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("APP_ENV", "test")

    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "pipeerp-api"}
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"


def test_request_id_accepts_safe_values_and_replaces_unsafe_values(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("APP_ENV", "test")
    from app.main import app

    with TestClient(app) as client:
        accepted = client.get("/api/v1/health", headers={"X-Request-ID": "mobile-123"})
        replaced = client.get("/api/v1/health", headers={"X-Request-ID": "unsafe id"})

    assert accepted.headers["x-request-id"] == "mobile-123"
    assert replaced.headers["x-request-id"] != "unsafe id"


def test_readiness_checks_the_database(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("APP_ENV", "test")
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine)

    def database_session():
        with factory() as db:
            yield db

    from app.main import app

    app.dependency_overrides[get_database_session] = database_session
    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "pipeerp-api"}


def test_readiness_fails_closed_when_the_database_is_unavailable(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("APP_ENV", "test")

    class FailingDatabase:
        def execute(self, _statement: object) -> None:
            raise SQLAlchemyError("database unavailable")

    def database_session():
        yield FailingDatabase()

    from app.main import app

    app.dependency_overrides[get_database_session] = database_session
    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")
    app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "قاعدة البيانات غير جاهزة"
