import os
from collections.abc import Generator
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-key-" * 5)
os.environ.setdefault("APP_ENV", "test")

from app.infrastructure.database.base import Base  # noqa: E402
from app.infrastructure.database.session import get_database_session  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.identity.models import AuditLog  # noqa: E402
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
            "track_lots": False,
            "standard_weight_kg": "12.500",
            "weight_tolerance_percent": "5",
        }
        created = client.post(
            "/api/v1/master-data/products",
            json=payload,
            headers=_csrf(client),
        )
        assert created.status_code == 201, created.text
        assert created.json()["version"] == 1
        assert created.json()["standard_weight_kg"] == "0"
        assert created.json()["weight_tolerance_percent"] == "0"
        assert created.json()["track_lots"] is True

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

        finished = client.patch(
            f"/api/v1/master-data/products/{product_id}",
            json={
                "version": 2,
                "product_type": "finished_good",
                "standard_weight_kg": "2.750",
                "weight_tolerance_percent": "9",
            },
            headers=_csrf(client),
        )
        assert finished.status_code == 200, finished.text
        assert finished.json()["standard_weight_kg"] == "2.750"
        assert finished.json()["weight_tolerance_percent"] == "0"

        raw_again = client.patch(
            f"/api/v1/master-data/products/{product_id}",
            json={"version": 3, "product_type": "raw_material"},
            headers=_csrf(client),
        )
        assert raw_again.status_code == 200, raw_again.text
        assert raw_again.json()["standard_weight_kg"] == "0"

        stale = client.patch(
            f"/api/v1/master-data/products/{product_id}",
            json={"version": 1, "name_ar": "تعديل قديم"},
            headers=_csrf(client),
        )
        assert stale.status_code == 409

        deleted = client.delete(
            f"/api/v1/master-data/products/{product_id}",
            headers=_csrf(client),
        )
        assert deleted.status_code == 204, deleted.text
        listed = client.get("/api/v1/master-data/products")
        assert listed.status_code == 200
        assert all(item["id"] != product_id for item in listed.json())

    with factory() as db:
        assert "master_data.product.delete" in set(db.scalars(select(AuditLog.event_type)))
    app.dependency_overrides.clear()


def test_partner_must_have_one_desktop_type_and_writes_require_manage_permission() -> None:
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
        assert created.status_code == 422

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
            denied_unit = read_only.post(
                "/api/v1/master-data/units",
                json={
                    "code": "BOX",
                    "name_ar": "صندوق",
                    "symbol": "صندوق",
                    "decimal_places": 0,
                },
                headers=_csrf(read_only),
            )
            assert denied_unit.status_code == 403
            denied_warehouse = read_only.post(
                "/api/v1/master-data/warehouses",
                json={"code": "DENIED", "name_ar": "غير مسموح", "is_default": False},
                headers=_csrf(read_only),
            )
            assert denied_warehouse.status_code == 403
            current_settings = read_only.get("/api/v1/master-data/settings")
            assert current_settings.status_code == 200
            denied_settings = read_only.put(
                "/api/v1/master-data/settings",
                json=current_settings.json(),
                headers=_csrf(read_only),
            )
            assert denied_settings.status_code == 403
    app.dependency_overrides.clear()


def test_reference_data_crud_rejects_duplicates_stale_updates_and_category_cycles() -> None:
    factory = _database()
    _seed(factory)
    with _client(factory) as client:
        _login(client)
        unit = client.post(
            "/api/v1/master-data/units",
            json={
                "code": "M",
                "name_ar": "متر",
                "symbol": "م",
                "decimal_places": 2,
            },
            headers=_csrf(client),
        )
        assert unit.status_code == 201, unit.text
        duplicate = client.post(
            "/api/v1/master-data/units",
            json={
                "code": "m",
                "name_ar": "متر مكرر",
                "symbol": "م",
                "decimal_places": 2,
            },
            headers=_csrf(client),
        )
        assert duplicate.status_code == 409

        unit_id = unit.json()["id"]
        updated_unit = client.put(
            f"/api/v1/master-data/units/{unit_id}",
            json={
                "version": 1,
                "code": "M",
                "name_ar": "متر طولي",
                "symbol": "م",
                "decimal_places": 3,
                "is_active": True,
            },
            headers=_csrf(client),
        )
        assert updated_unit.status_code == 200, updated_unit.text
        stale_unit = client.put(
            f"/api/v1/master-data/units/{unit_id}",
            json={
                "version": 1,
                "code": "M",
                "name_ar": "تعديل قديم",
                "symbol": "م",
                "decimal_places": 3,
                "is_active": True,
            },
            headers=_csrf(client),
        )
        assert stale_unit.status_code == 409

        parent = client.post(
            "/api/v1/master-data/categories",
            json={"code": "RAW", "name_ar": "خامات"},
            headers=_csrf(client),
        )
        assert parent.status_code == 201, parent.text
        child = client.post(
            "/api/v1/master-data/categories",
            json={
                "code": "POLYMER",
                "name_ar": "بوليمرات",
                "parent_id": parent.json()["id"],
            },
            headers=_csrf(client),
        )
        assert child.status_code == 201, child.text
        cycle = client.put(
            f"/api/v1/master-data/categories/{parent.json()['id']}",
            json={
                "version": 1,
                "code": "RAW",
                "name_ar": "خامات",
                "parent_id": child.json()["id"],
                "is_active": True,
            },
            headers=_csrf(client),
        )
        assert cycle.status_code == 409

    with factory() as db:
        events = set(db.scalars(select(AuditLog.event_type)))
        assert "master_data.unit.create" in events
        assert "master_data.unit.update" in events
        assert "master_data.category.create" in events
    app.dependency_overrides.clear()


def test_single_factory_warehouse_and_company_settings_are_concurrency_safe() -> None:
    factory = _database()
    _seed(factory)
    with _client(factory) as client:
        _login(client)
        created = client.post(
            "/api/v1/master-data/warehouses",
            json={"code": "SECOND", "name_ar": "المخزن الثاني", "is_default": True},
            headers=_csrf(client),
        )
        assert created.status_code == 409

        warehouses = client.get("/api/v1/master-data/warehouses?include_inactive=true")
        assert warehouses.status_code == 200
        assert len(warehouses.json()) == 1
        factory_warehouse = warehouses.json()[0]
        assert factory_warehouse["code"] == "MAIN"
        assert factory_warehouse["name_ar"] == "المصنع"
        assert factory_warehouse["is_default"] is True

        settings = client.get("/api/v1/master-data/settings")
        assert settings.status_code == 200
        assert settings.json()["default_warehouse_id"] == factory_warehouse["id"]
        current_version = settings.json()["version"]

        payload = {
            **settings.json(),
            "company_name_ar": "شركة بايب للاختبار",
        }
        payload.pop("id", None)
        updated = client.put(
            "/api/v1/master-data/settings",
            json=payload,
            headers=_csrf(client),
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["version"] == current_version + 1

        stale = client.put(
            "/api/v1/master-data/settings",
            json={**payload, "company_name_ar": "تعديل قديم"},
            headers=_csrf(client),
        )
        assert stale.status_code == 409

        deactivate_default = client.put(
            f"/api/v1/master-data/warehouses/{factory_warehouse['id']}",
            json={
                "version": factory_warehouse["version"],
                "code": "MAIN",
                "name_ar": "المصنع",
                "is_default": False,
                "is_active": False,
            },
            headers=_csrf(client),
        )
        assert deactivate_default.status_code == 409
    app.dependency_overrides.clear()
