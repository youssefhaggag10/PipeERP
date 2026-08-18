import os
from collections.abc import Generator
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-key-" * 5)
os.environ.setdefault("APP_ENV", "test")

from app.infrastructure.database.base import Base  # noqa: E402
from app.infrastructure.database.session import get_database_session  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.identity.service import ClientContext, create_initial_admin  # noqa: E402
from app.modules.master_data.models import (  # noqa: E402
    CompanySettings,
    UnitOfMeasure,
    Warehouse,
)


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


def _seed(factory: sessionmaker[Session]) -> str:
    with factory.begin() as db:
        create_initial_admin(
            db,
            username="admin",
            display_name="مدير النظام",
            password="Admin-password-2026",
            client=ClientContext("127.0.0.1", "test", "bootstrap"),
        )
        unit = UnitOfMeasure(
            code="KG",
            normalized_code="KG",
            name_ar="كيلوجرام",
            symbol="كجم",
            decimal_places=3,
            is_active=True,
        )
        warehouse = Warehouse(
            code="MAIN",
            normalized_code="MAIN",
            name_ar="المصنع",
            is_default=True,
            is_active=True,
            version=1,
        )
        db.add_all([unit, warehouse])
        db.flush()
        db.add(
            CompanySettings(
                id=1,
                company_name_ar="PipeERP",
                phone="",
                address="",
                tax_number="",
                currency_code="EGP",
                currency_decimal_places=2,
                tax_enabled=False,
                default_tax_rate=0,
                default_warehouse_id=warehouse.id,
            )
        )
        return str(unit.id)


def _login(
    client: TestClient, username: str = "admin", password: str = "Admin-password-2026"
) -> None:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("pipeerp_csrf")
    assert token is not None
    return {"X-CSRF-Token": token}


def test_product_creation_duplicate_code_and_optimistic_concurrency() -> None:
    factory = _database()
    unit_id = _seed(factory)
    with _client(factory) as client:
        _login(client)
        payload = {
            "code": "RM-001",
            "name_ar": "خامة اختبار",
            "product_type": "raw_material",
            "unit_id": unit_id,
            "min_stock": "10.000",
            "track_lots": True,
        }
        created = client.post(
            "/api/v1/master-data/products",
            json=payload,
            headers=_csrf(client),
        )
        assert created.status_code == 201, created.text
        assert created.json()["version"] == 1

        duplicate = client.post(
            "/api/v1/master-data/products",
            json={**payload, "code": "rm-001"},
            headers=_csrf(client),
        )
        assert duplicate.status_code == 409

        product_id = created.json()["id"]
        updated = client.patch(
            f"/api/v1/master-data/products/{product_id}",
            json={"version": 1, "name_ar": "خامة محدثة"},
            headers=_csrf(client),
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["version"] == 2

        stale = client.patch(
            f"/api/v1/master-data/products/{product_id}",
            json={"version": 1, "name_ar": "تعديل قديم"},
            headers=_csrf(client),
        )
        assert stale.status_code == 409
    app.dependency_overrides.clear()


def test_partner_can_be_customer_and_supplier_and_writes_require_manage_permission() -> None:
    factory = _database()
    _seed(factory)
    with _client(factory) as admin:
        _login(admin)
        created = admin.post(
            "/api/v1/master-data/partners",
            json={
                "code": "P-001",
                "name_ar": "شريك مزدوج",
                "is_customer": True,
                "is_supplier": True,
            },
            headers=_csrf(admin),
        )
        assert created.status_code == 201, created.text
        assert created.json()["is_customer"] is True
        assert created.json()["is_supplier"] is True

        operator_name = f"operator-{uuid4().hex[:6]}"
        operator = admin.post(
            "/api/v1/identity/users",
            json={
                "username": operator_name,
                "display_name": "مشغل للقراءة",
                "password": "Operator-password-2026",
                "role_codes": ["operations_manager"],
                "must_change_password": False,
            },
            headers=_csrf(admin),
        )
        assert operator.status_code == 201, operator.text

        with _client(factory) as read_only:
            _login(read_only, operator_name, "Operator-password-2026")
            assert read_only.get("/api/v1/master-data/partners").status_code == 200
            denied = read_only.post(
                "/api/v1/master-data/partners",
                json={
                    "code": "P-002",
                    "name_ar": "غير مسموح",
                    "is_customer": True,
                },
                headers=_csrf(read_only),
            )
            assert denied.status_code == 403
    app.dependency_overrides.clear()
