import os
from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-key-" * 5)
os.environ.setdefault("APP_ENV", "test")

from app.infrastructure.database.base import Base  # noqa: E402
from app.infrastructure.database.session import get_database_session  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.identity import models as identity_models  # noqa: E402, F401
from app.modules.identity.service import ClientContext, create_initial_admin  # noqa: E402


def _database() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _client(factory: sessionmaker[Session]) -> TestClient:
    def override_database() -> Generator[Session, None, None]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_database_session] = override_database
    return TestClient(app)


def _bootstrap(factory: sessionmaker[Session]) -> None:
    with factory.begin() as db:
        create_initial_admin(
            db,
            username="admin",
            display_name="مدير النظام",
            password="Admin-password-2026",
            client=ClientContext("127.0.0.1", "test", "bootstrap"),
        )


def _login(client: TestClient, username: str, password: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("pipeerp_csrf")
    assert token is not None
    return {"X-CSRF-Token": token}


def test_authentication_rotation_logout_and_security_headers() -> None:
    factory = _database()
    _bootstrap(factory)
    with _client(factory) as client:
        _login(client, "ADMIN", "Admin-password-2026")
        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["roles"] == ["system_admin"]
        assert me.headers["x-frame-options"] == "DENY"
        old_refresh = client.cookies.get("pipeerp_refresh")
        refresh = client.post("/api/v1/auth/refresh", headers=_csrf(client))
        assert refresh.status_code == 200
        assert client.cookies.get("pipeerp_refresh") != old_refresh
        logout = client.post("/api/v1/auth/logout", headers=_csrf(client))
        assert logout.status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401
    app.dependency_overrides.clear()


def test_csrf_and_direct_permission_bypass_are_denied_and_audited() -> None:
    factory = _database()
    _bootstrap(factory)
    with _client(factory) as admin:
        _login(admin, "admin", "Admin-password-2026")
        payload = {
            "username": "operator",
            "display_name": "مسؤول التشغيل",
            "password": "Operator-password-2026",
            "role_codes": ["operations_manager"],
            "must_change_password": False,
        }
        assert admin.post("/api/v1/identity/users", json=payload).status_code == 403
        created = admin.post(
            "/api/v1/identity/users",
            json=payload,
            headers=_csrf(admin),
        )
        assert created.status_code == 201, created.text

        with _client(factory) as operator:
            _login(operator, "operator", "Operator-password-2026")
            bypass = operator.post(
                "/api/v1/identity/users",
                json={**payload, "username": "forbidden"},
                headers=_csrf(operator),
            )
            assert bypass.status_code == 403

        audit = admin.get("/api/v1/identity/audit")
        assert audit.status_code == 200
        assert any(
            item["event_type"] == "security.permission.denied"
            for item in audit.json()
        )
    app.dependency_overrides.clear()


def test_disabling_user_invalidates_existing_session_immediately() -> None:
    factory = _database()
    _bootstrap(factory)
    with _client(factory) as admin:
        _login(admin, "admin", "Admin-password-2026")
        created = admin.post(
            "/api/v1/identity/users",
            json={
                "username": "auditor",
                "display_name": "مراجع النظام",
                "password": "Auditor-password-2026",
                "role_codes": ["operations_manager"],
                "must_change_password": False,
            },
            headers=_csrf(admin),
        )
        user_id = created.json()["id"]

        with _client(factory) as auditor:
            _login(auditor, "auditor", "Auditor-password-2026")
            assert auditor.get("/api/v1/auth/me").status_code == 200
            disabled = admin.patch(
                f"/api/v1/identity/users/{user_id}",
                json={"is_active": False},
                headers=_csrf(admin),
            )
            assert disabled.status_code == 200
            assert auditor.get("/api/v1/auth/me").status_code == 401
    app.dependency_overrides.clear()


def test_repeated_failures_lock_the_account_without_revealing_user_state() -> None:
    factory = _database()
    _bootstrap(factory)
    with _client(factory) as client:
        for _ in range(5):
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "wrong-password"},
            )
            assert response.status_code == 401
            assert response.json()["detail"] == "بيانات الدخول غير صحيحة"
        locked = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "Admin-password-2026"},
        )
        assert locked.status_code == 401
        assert locked.json()["detail"] == "بيانات الدخول غير صحيحة"
    app.dependency_overrides.clear()


def test_temporary_password_cannot_bypass_forced_change_through_api() -> None:
    factory = _database()
    _bootstrap(factory)
    with _client(factory) as admin:
        _login(admin, "admin", "Admin-password-2026")
        created = admin.post(
            "/api/v1/identity/users",
            json={
                "username": "temporary-admin",
                "display_name": "مدير مؤقت",
                "password": "Temporary-password-2026",
                "role_codes": ["system_admin"],
                "must_change_password": True,
            },
            headers=_csrf(admin),
        )
        assert created.status_code == 201
        with _client(factory) as temporary:
            _login(temporary, "temporary-admin", "Temporary-password-2026")
            bypass = temporary.get("/api/v1/identity/users")
            assert bypass.status_code == 403
            assert bypass.json()["detail"] == "يجب تغيير كلمة المرور المؤقتة أولًا"
    app.dependency_overrides.clear()
