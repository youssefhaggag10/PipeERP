import os
from collections.abc import Generator
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-key-" * 5)
os.environ.setdefault("APP_ENV", "test")

from app.infrastructure.database.base import Base  # noqa: E402
from app.infrastructure.database.session import get_database_session  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.identity.models import AuditLog  # noqa: E402
from app.modules.identity.service import ClientContext, create_initial_admin  # noqa: E402
from app.modules.inventory.models import InventoryBalance, InventoryLayer  # noqa: E402
from app.modules.master_data.models import (  # noqa: E402
    CompanySettings,
    DocumentSequence,
    Partner,
    Product,
    UnitOfMeasure,
    Warehouse,
)
from app.modules.purchasing.models import (  # noqa: E402
    PurchaseOrder,
    PurchaseReceipt,
    PurchaseReceiptLine,
    SupplierInvoice,
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


def _seed(factory: sessionmaker[Session]) -> tuple[str, str, str]:
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
            version=1,
        )
        warehouse = Warehouse(
            code="MAIN",
            normalized_code="MAIN",
            name_ar="المصنع",
            is_default=True,
            is_active=True,
            version=1,
        )
        supplier = Partner(
            code="SUP-001",
            normalized_code="SUP-001",
            name_ar="مورد الخامات",
            phone="",
            address="",
            tax_number="",
            is_customer=False,
            is_supplier=True,
            is_active=True,
            version=1,
        )
        db.add_all([unit, warehouse, supplier])
        db.flush()
        product = Product(
            code="RM-001",
            normalized_code="RM-001",
            name_ar="خامة اختبار",
            product_type="raw_material",
            unit_id=unit.id,
            category_id=None,
            min_stock=0,
            track_lots=True,
            standard_weight_kg=Decimal("0.5"),
            weight_tolerance_percent=5,
            is_active=True,
            version=1,
        )
        db.add(product)
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
                version=1,
            )
        )
        db.add_all(
            [
                DocumentSequence(
                    document_type=document_type,
                    prefix=prefix,
                    next_value=1,
                    padding=6,
                    version=1,
                )
                for document_type, prefix in (
                    ("purchase_order", "PO-"),
                    ("purchase_receipt", "PR-"),
                    ("purchase_invoice", "PI-"),
                )
            ]
        )
        db.flush()
        return str(product.id), str(warehouse.id), str(supplier.id)


def _login(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin-password-2026"},
    )
    assert response.status_code == 200, response.text


def _headers(test_client: TestClient, key: str | None = None) -> dict[str, str]:
    csrf = test_client.cookies.get("pipeerp_csrf")
    assert csrf is not None
    result = {"X-CSRF-Token": csrf}
    if key is not None:
        result["Idempotency-Key"] = key
    return result


def test_purchase_order_partial_receipts_loss_costing_and_supplier_invoice() -> None:
    factory = _database()
    product_id, warehouse_id, supplier_id = _seed(factory)
    with _client(factory) as test_client:
        _login(test_client)
        created = test_client.post(
            "/api/v1/purchases/orders",
            headers=_headers(test_client),
            json={
                "supplier_id": supplier_id,
                "warehouse_id": warehouse_id,
                "notes": "توريد خامة على دفعتين",
                "lines": [
                    {
                        "product_id": product_id,
                        "cost_basis": "quantity",
                        "ordered_quantity": "1000",
                        "ordered_weight_kg": "500",
                        "unit_price": "30",
                        "additional_unit_cost": "4",
                    }
                ],
            },
        )
        assert created.status_code == 201, created.text
        order = created.json()
        assert order["order_number"] == "PO-000001"
        assert order["status"] == "draft"
        assert order["total"] == "34000.00"

        approved = test_client.post(
            f"/api/v1/purchases/orders/{order['id']}/approval",
            headers=_headers(test_client),
            json={"version": order["version"]},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        line_id = approved.json()["lines"][0]["id"]

        first_payload = {
            "notes": "الدفعة الأولى",
            "lines": [
                {
                    "purchase_order_line_id": line_id,
                    "gross_quantity": "400",
                    "gross_weight_kg": "200",
                    "loss_quantity": "2",
                    "loss_weight_kg": "1",
                    "lot_number": "LOT-001",
                }
            ],
        }
        first = test_client.post(
            f"/api/v1/purchases/orders/{order['id']}/receipts",
            headers=_headers(test_client, "purchase-receipt-0001"),
            json=first_payload,
        )
        assert first.status_code == 201, first.text
        assert first.json()["receipt_number"] == "PR-000001"
        first_line = first.json()["lines"][0]
        assert first_line["net_quantity"] == "398.000000"
        assert first_line["capitalized_cost"] == "13600.00"
        assert first_line["inventory_unit_cost"] == "34.170854"

        repeated = test_client.post(
            f"/api/v1/purchases/orders/{order['id']}/receipts",
            headers=_headers(test_client, "purchase-receipt-0001"),
            json=first_payload,
        )
        assert repeated.status_code == 201
        assert repeated.json()["id"] == first.json()["id"]

        changed_replay = test_client.post(
            f"/api/v1/purchases/orders/{order['id']}/receipts",
            headers=_headers(test_client, "purchase-receipt-0001"),
            json={**first_payload, "notes": "طلب مختلف"},
        )
        assert changed_replay.status_code == 409

        over_receipt = test_client.post(
            f"/api/v1/purchases/orders/{order['id']}/receipts",
            headers=_headers(test_client, "purchase-receipt-0002"),
            json={
                "lines": [
                    {
                        "purchase_order_line_id": line_id,
                        "gross_quantity": "601",
                        "gross_weight_kg": "300",
                    }
                ]
            },
        )
        assert over_receipt.status_code in {409, 422}

        second = test_client.post(
            f"/api/v1/purchases/orders/{order['id']}/receipts",
            headers=_headers(test_client, "purchase-receipt-0003"),
            json={
                "notes": "الدفعة الثانية",
                "lines": [
                    {
                        "purchase_order_line_id": line_id,
                        "gross_quantity": "600",
                        "gross_weight_kg": "300",
                        "loss_quantity": "3",
                        "loss_weight_kg": "1.5",
                        "lot_number": "LOT-002",
                    }
                ],
            },
        )
        assert second.status_code == 201, second.text

        refreshed = test_client.get(f"/api/v1/purchases/orders/{order['id']}")
        assert refreshed.status_code == 200
        assert refreshed.json()["status"] == "received"
        assert refreshed.json()["lines"][0]["received_quantity"] == "1000.000000"

        invoice = test_client.post(
            f"/api/v1/purchases/orders/{order['id']}/supplier-invoice",
            headers=_headers(test_client),
            json={"supplier_invoice_number": "SUP-INV-2026-88"},
        )
        assert invoice.status_code == 201, invoice.text
        assert invoice.json()["invoice_number"] == "PI-000001"
        assert invoice.json()["total"] == "34000.00"

    with factory() as db:
        order_row = db.scalar(select(PurchaseOrder))
        assert order_row is not None and order_row.status == "received"
        assert db.scalar(select(func.count(PurchaseReceipt.id))) == 2
        assert db.scalar(select(func.count(PurchaseReceiptLine.id))) == 2
        assert db.scalar(select(func.count(SupplierInvoice.id))) == 1
        balance = db.scalar(select(InventoryBalance))
        assert balance is not None
        assert balance.quantity_on_hand == Decimal("995.000000")
        assert balance.weight_on_hand_kg == Decimal("497.500000")
        assert db.scalar(select(func.count(InventoryLayer.id))) == 2
        events = set(db.scalars(select(AuditLog.event_type)))
        assert {
            "purchasing.order.create",
            "purchasing.order.approve",
            "purchasing.receipt.post",
            "purchasing.invoice.post",
        } <= events


def test_purchase_read_permission_cannot_create_or_receive_orders() -> None:
    factory = _database()
    product_id, warehouse_id, supplier_id = _seed(factory)
    with _client(factory) as test_client:
        _login(test_client)
        role = test_client.post(
            "/api/v1/identity/roles",
            headers=_headers(test_client),
            json={
                "code": "purchase_viewer",
                "name_ar": "مشاهد المشتريات",
                "permissions": ["purchases.read"],
            },
        )
        assert role.status_code == 201, role.text
        viewer = test_client.post(
            "/api/v1/identity/users",
            headers=_headers(test_client),
            json={
                "username": "purchase.viewer",
                "display_name": "مشاهد المشتريات",
                "password": "Viewer-password-2026",
                "role_codes": ["purchase_viewer"],
                "must_change_password": False,
            },
        )
        assert viewer.status_code == 201, viewer.text
        login = test_client.post(
            "/api/v1/auth/login",
            json={"username": "purchase.viewer", "password": "Viewer-password-2026"},
        )
        assert login.status_code == 200, login.text

        assert test_client.get("/api/v1/purchases/orders").status_code == 200
        denied = test_client.post(
            "/api/v1/purchases/orders",
            headers=_headers(test_client),
            json={
                "supplier_id": supplier_id,
                "warehouse_id": warehouse_id,
                "lines": [
                    {
                        "product_id": product_id,
                        "cost_basis": "quantity",
                        "ordered_quantity": "10",
                        "unit_price": "5",
                    }
                ],
            },
        )
        assert denied.status_code == 403

    with factory() as db:
        assert db.scalar(select(func.count(PurchaseOrder.id))) == 0
        assert (
            db.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.event_type == "security.permission.denied",
                    AuditLog.entity_id == "purchases.manage",
                )
            )
            == 1
        )
