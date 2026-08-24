import os
from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-key-" * 5)
os.environ.setdefault("APP_ENV", "test")

from app.infrastructure.database.base import Base  # noqa: E402
from app.infrastructure.database.session import get_database_session  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.identity.service import ClientContext, create_initial_admin  # noqa: E402
from app.modules.master_data.models import DocumentSequence, Partner  # noqa: E402


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


def _seed(factory: sessionmaker[Session]) -> None:
    with factory.begin() as db:
        create_initial_admin(
            db,
            username="admin",
            display_name="مدير النظام",
            password="Admin-password-2026",
            client=ClientContext("127.0.0.1", "test", "bootstrap"),
        )
        db.add(
            DocumentSequence(
                document_type="crm_lead", prefix="LD-", next_value=1, padding=6, version=1
            )
        )


def _login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin-password-2026"},
    )
    assert response.status_code == 200
    token = client.cookies.get("pipeerp_csrf")
    assert token
    return {"X-CSRF-Token": token}


def test_crm_lead_activity_pipeline_and_conversion_flow() -> None:
    factory = _database()
    _seed(factory)
    with _client(factory) as client:
        headers = _login(client)
        options = client.get("/api/v1/crm/options")
        assert options.status_code == 200
        owner_id = options.json()["owners"][0]["id"]
        created = client.post(
            "/api/v1/crm/leads",
            headers=headers,
            json={
                "name": "عميل محتمل",
                "phone": "01000000000",
                "source_code": "facebook",
                "temperature": "hot",
                "assigned_user_id": owner_id,
                "opportunity_value": "25000",
            },
        )
        assert created.status_code == 201, created.text
        lead = created.json()
        assert lead["lead_number"] == "LD-000001"

        duplicate = client.post(
            "/api/v1/crm/leads",
            headers=headers,
            json={"name": "عميل مكرر", "phone": "01000000000"},
        )
        assert duplicate.status_code == 409

        stage = client.post(
            f"/api/v1/crm/leads/{lead['id']}/stage",
            headers=headers,
            json={"stage_code": "negotiation"},
        )
        assert stage.status_code == 200
        assert stage.json()["stage_code"] == "negotiation"

        note = client.post(
            f"/api/v1/crm/leads/{lead['id']}/notes",
            headers=headers,
            json={"note": "تم إرسال تفاصيل الأسعار"},
        )
        assert note.status_code == 201

        activity = client.post(
            f"/api/v1/crm/leads/{lead['id']}/activities",
            headers=headers,
            json={
                "subject": "اتصال متابعة",
                "due_at": "2026-08-22T10:00:00Z",
                "priority": "high",
            },
        )
        assert activity.status_code == 201, activity.text
        scheduled_summary = client.get("/api/v1/crm/summary")
        assert scheduled_summary.status_code == 200, scheduled_summary.text
        assert scheduled_summary.json()["today_count"] == 0
        rescheduled = client.post(
            f"/api/v1/crm/activities/{activity.json()['id']}/reschedule",
            headers=headers,
            json={"due_at": "2026-08-23T11:30:00Z"},
        )
        assert rescheduled.status_code == 200, rescheduled.text
        assert rescheduled.json()["due_at"].startswith("2026-08-23T11:30:00")
        completed = client.post(
            f"/api/v1/crm/activities/{activity.json()['id']}/completion",
            headers=headers,
            json={"outcome": "وافق على العرض"},
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "done"

        source_report = client.get("/api/v1/crm/reports?mode=source")
        assert source_report.status_code == 200
        assert source_report.json() == [
            {"label": "فيسبوك", "total": 1, "won": 0, "value": "25000.00"}
        ]
        owner_report = client.get("/api/v1/crm/reports?mode=owner")
        assert owner_report.status_code == 200
        assert owner_report.json()[0]["total"] == 1
        assert client.get("/api/v1/crm/reports?mode=invalid").status_code == 422

        conversion = client.post(f"/api/v1/crm/leads/{lead['id']}/conversion", headers=headers)
        assert conversion.status_code == 200, conversion.text
        refreshed = client.get("/api/v1/crm/leads")
        assert refreshed.json()[0]["stage_code"] == "won"
        summary = client.get("/api/v1/crm/summary")
        assert summary.json()["won_count"] == 1
        pipeline = client.get("/api/v1/crm/pipeline")
        assert next(item for item in pipeline.json() if item["code"] == "won")["lead_count"] == 1

    with factory() as db:
        partner = db.scalar(select(Partner).where(Partner.phone == "01000000000"))
        assert partner is not None and partner.is_customer
    app.dependency_overrides.clear()


def test_crm_navigation_syncs_customers_once_and_only_admin_schedules() -> None:
    factory = _database()
    _seed(factory)
    with factory.begin() as db:
        db.add(
            Partner(
                code="CUS-SYNC",
                normalized_code="CUS-SYNC",
                name_ar="عميل موجود",
                phone="01011111111",
                address="القاهرة",
                tax_number="",
                is_customer=True,
                is_supplier=False,
                is_active=True,
                version=1,
            )
        )
    with _client(factory) as client:
        headers = _login(client)
        first = client.get("/api/v1/crm/options")
        second = client.get("/api/v1/crm/options")
        assert first.status_code == 200 and second.status_code == 200
        leads = client.get("/api/v1/crm/leads").json()
        assert len(leads) == 1
        assert leads[0]["name"] == "عميل موجود"
        assert leads[0]["customer_partner_id"] is not None
        assert leads[0]["stage_code"] == "won"

        role = client.post(
            "/api/v1/identity/roles",
            headers=headers,
            json={
                "code": "crm_manager_non_admin",
                "name_ar": "مدير CRM",
                "permissions": ["crm.read", "crm.manage"],
            },
        )
        assert role.status_code == 201, role.text
        user = client.post(
            "/api/v1/identity/users",
            headers=headers,
            json={
                "username": "crm.manager",
                "display_name": "مدير متابعة",
                "password": "CRM-manager-password-2026",
                "role_codes": ["crm_manager_non_admin"],
            },
        )
        assert user.status_code == 201, user.text
        manager_headers = _login_as(client, "crm.manager", "CRM-manager-password-2026")
        denied = client.post(
            f"/api/v1/crm/leads/{leads[0]['id']}/activities",
            headers=manager_headers,
            json={"subject": "متابعة", "due_at": "2026-08-25T10:00:00Z"},
        )
        assert denied.status_code == 403
    app.dependency_overrides.clear()


def _login_as(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = client.cookies.get("pipeerp_csrf")
    assert token
    return {"X-CSRF-Token": token}
