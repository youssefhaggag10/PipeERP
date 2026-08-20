import os
from collections.abc import Generator
from decimal import Decimal
from secrets import token_urlsafe
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-key-" * 5)
os.environ.setdefault("APP_ENV", "test")

from app.infrastructure.database.base import Base  # noqa: E402
from app.infrastructure.database.session import get_database_session  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.identity.service import ClientContext, create_initial_admin  # noqa: E402
from app.modules.inventory.models import InventoryBalance, InventoryLayer  # noqa: E402
from app.modules.master_data.models import (  # noqa: E402
    DocumentSequence,
    Partner,
    Product,
    UnitOfMeasure,
    Warehouse,
)
from app.modules.sales.models import (  # noqa: E402
    CustomerInvoice,
    SalesDelivery,
    SalesOrder,
    SalesQuotation,
)

ADMIN_PASSWORD = f"Admin-test-7!{token_urlsafe(18)}"
PIECE_CLERK_PASSWORD = f"Piece-test-7!{token_urlsafe(18)}"
WEIGHT_CLERK_PASSWORD = f"Weight-test-7!{token_urlsafe(18)}"


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


def _seed(
    factory: sessionmaker[Session],
    *,
    cost_basis: str = "weight",
    unit_cost: Decimal = Decimal("10"),
) -> tuple[str, str, str]:
    with factory.begin() as db:
        create_initial_admin(
            db,
            username="admin",
            display_name="مدير النظام",
            password=ADMIN_PASSWORD,
            client=ClientContext("127.0.0.1", "test", "bootstrap"),
        )
        unit = UnitOfMeasure(
            code="PIPE",
            normalized_code="PIPE",
            name_ar="ماسورة",
            symbol="ماسورة",
            decimal_places=0,
            is_active=True,
            version=1,
        )
        warehouse = Warehouse(
            code="MAIN",
            normalized_code="MAIN",
            name_ar="مخزن المصنع",
            is_default=True,
            is_active=True,
            version=1,
        )
        customer = Partner(
            code="CUS-001",
            normalized_code="CUS-001",
            name_ar="عميل المبيعات",
            phone="",
            address="",
            tax_number="",
            is_customer=True,
            is_supplier=False,
            is_active=True,
            version=1,
        )
        db.add_all([unit, warehouse, customer])
        db.flush()
        product = Product(
            code="FG-090",
            normalized_code="FG-090",
            name_ar="ماسورة 90 مم",
            product_type="finished_good",
            unit_id=unit.id,
            category_id=None,
            min_stock=0,
            track_lots=True,
            standard_weight_kg=Decimal("10"),
            weight_tolerance_percent=5,
            is_active=True,
            version=1,
        )
        db.add(product)
        db.flush()
        layer = InventoryLayer(
            product_id=product.id,
            warehouse_id=warehouse.id,
            lot_id=None,
            source_type="manufacturing_output",
            source_id="seed",
            source_line_id="seed-line",
            cost_basis=cost_basis,
            quantity_received=Decimal("100"),
            quantity_remaining=Decimal("100"),
            weight_received_kg=Decimal("1000"),
            weight_remaining_kg=Decimal("1000"),
            unit_cost=unit_cost,
            version=1,
        )
        balance = InventoryBalance(
            product_id=product.id,
            warehouse_id=warehouse.id,
            quantity_on_hand=Decimal("100"),
            weight_on_hand_kg=Decimal("1000"),
            version=1,
        )
        db.add_all([layer, balance])
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
                    ("sales_order", "SO-"),
                    ("sales_delivery", "SD-"),
                    ("sales_invoice", "SI-"),
                    ("weight_card", "WC-"),
                    ("sales_quotation", "QT-"),
                )
            ]
        )
        db.flush()
        return str(product.id), str(warehouse.id), str(customer.id)


def _login(
    client: TestClient,
    username: str = "admin",
    password: str = ADMIN_PASSWORD,
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text


def _headers(client: TestClient, key: str | None = None) -> dict[str, str]:
    csrf = client.cookies.get("pipeerp_csrf")
    assert csrf is not None
    headers = {"X-CSRF-Token": csrf}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def test_piece_sale_delivers_fifo_and_posts_invoice_once() -> None:
    factory = _database()
    product_id, warehouse_id, customer_id = _seed(factory)
    with _client(factory) as client:
        _login(client)
        created = client.post(
            "/api/v1/sales/orders",
            headers=_headers(client),
            json={
                "customer_id": customer_id,
                "warehouse_id": warehouse_id,
                "notes": "بيع بالقطعة",
                "lines": [
                    {
                        "product_id": product_id,
                        "quantity": "2",
                        "unit": "ماسورة",
                        "unit_price": "150",
                    }
                ],
            },
        )
        assert created.status_code == 201, created.text
        order = created.json()
        delivered = client.post(
            f"/api/v1/sales/orders/{order['id']}/delivery",
            headers=_headers(client, "piece-delivery-0001"),
            json={"version": order["version"]},
        )
        assert delivered.status_code == 200, delivered.text
        result = delivered.json()
        assert result["status"] == "delivered"
        assert result["invoice"]["invoice_number"] == "SI-000001"
        assert result["invoice"]["total"] == "300.00"
        assert result["lines"][0]["unit"] == "ماسورة"
        assert result["delivery"]["lines"][0]["quantity"] == "2.000000"
        assert result["delivery"]["lines"][0]["weight_kg"] == "20.000000"
        assert result["delivery"]["lines"][0]["cost_amount"] == "200.000000"

        replay = client.post(
            f"/api/v1/sales/orders/{order['id']}/delivery",
            headers=_headers(client, "piece-delivery-0001"),
            json={"version": order["version"]},
        )
        assert replay.status_code == 200
        assert replay.json()["delivery"]["id"] == result["delivery"]["id"]

    with factory() as db:
        assert db.scalar(select(func.count(SalesDelivery.id))) == 1
        assert db.scalar(select(func.count(CustomerInvoice.id))) == 1
        balance = db.get(InventoryBalance, (UUID(product_id), UUID(warehouse_id)))
        assert balance is not None
        assert balance.quantity_on_hand == Decimal("98.000000")
        assert balance.weight_on_hand_kg == Decimal("980.000000")


def test_weight_sale_preserves_exact_card_weight_and_adjustments() -> None:
    factory = _database()
    product_id, warehouse_id, customer_id = _seed(factory)
    with _client(factory) as client:
        _login(client)
        created = client.post(
            "/api/v1/sales/weight-orders",
            headers=_headers(client),
            json={
                "customer_id": customer_id,
                "warehouse_id": warehouse_id,
                "weight_mode": "total_card",
                "pricing_mode": "uniform",
                "total_actual_weight_kg": "95",
                "uniform_price_per_kg": "20",
                "discount_amount": "100",
                "transport_amount": "250",
                "tax_amount": "0",
                "vehicle_number": "س ص ع 123",
                "lines": [{"product_id": product_id, "quantity": "10"}],
            },
        )
        assert created.status_code == 201, created.text
        order = created.json()
        assert order["weight_cards"][0]["net_weight_kg"] == "95.000000"
        assert order["subtotal"] == "1900.00"
        assert order["total"] == "2050.00"
        delivered = client.post(
            f"/api/v1/sales/orders/{order['id']}/delivery",
            headers=_headers(client, "weight-delivery-0001"),
            json={"version": order["version"]},
        )
        assert delivered.status_code == 200, delivered.text
        result = delivered.json()
        assert result["invoice"]["invoice_type"] == "weight"
        assert result["invoice"]["total"] == "2050.00"
        assert result["delivery"]["lines"][0]["quantity"] == "10.000000"
        assert result["delivery"]["lines"][0]["weight_kg"] == "95.000000"

    with factory() as db:
        balance = db.get(InventoryBalance, (UUID(product_id), UUID(warehouse_id)))
        assert balance is not None
        assert balance.quantity_on_hand == Decimal("90.000000")
        assert balance.weight_on_hand_kg == Decimal("905.000000")


def test_weight_sale_keeps_piece_based_fifo_cost_when_actual_weight_varies() -> None:
    factory = _database()
    product_id, warehouse_id, customer_id = _seed(
        factory,
        cost_basis="quantity",
        unit_cost=Decimal("40"),
    )
    with _client(factory) as client:
        _login(client)
        order = client.post(
            "/api/v1/sales/weight-orders",
            headers=_headers(client),
            json={
                "customer_id": customer_id,
                "warehouse_id": warehouse_id,
                "weight_mode": "total_card",
                "pricing_mode": "uniform",
                "total_actual_weight_kg": "95",
                "uniform_price_per_kg": "20",
                "lines": [{"product_id": product_id, "quantity": "10"}],
            },
        ).json()
        delivered = client.post(
            f"/api/v1/sales/orders/{order['id']}/delivery",
            headers=_headers(client, "quantity-cost-weight-delivery"),
            json={"version": order["version"]},
        )
        assert delivered.status_code == 200, delivered.text
        line = delivered.json()["delivery"]["lines"][0]
        assert line["quantity"] == "10.000000"
        assert line["weight_kg"] == "95.000000"
        assert line["cost_amount"] == "400.000000"


def test_quotation_has_no_stock_invoice_or_order_effect() -> None:
    factory = _database()
    product_id, _warehouse_id, customer_id = _seed(factory)
    with _client(factory) as client:
        _login(client)
        response = client.post(
            "/api/v1/sales/quotations",
            headers=_headers(client),
            json={
                "customer_id": customer_id,
                "notes": "عرض فقط",
                "lines": [
                    {
                        "product_id": product_id,
                        "item_name": "ماسورة 90 مم",
                        "quantity": "10",
                        "unit": "ماسورة",
                        "unit_price": "25.5",
                    },
                    {
                        "product_id": None,
                        "item_name": "خدمة نقل اختيارية",
                        "quantity": "1",
                        "unit": "خدمة",
                        "unit_price": "100",
                    },
                ],
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["quotation_number"] == "QT-000001"
        assert response.json()["total"] == "355.00"

    with factory() as db:
        assert db.scalar(select(func.count(SalesQuotation.id))) == 1
        assert db.scalar(select(func.count(SalesOrder.id))) == 0
        assert db.scalar(select(func.count(CustomerInvoice.id))) == 0


def test_weight_draft_can_be_cancelled_without_stock_or_invoice_effect() -> None:
    factory = _database()
    product_id, warehouse_id, customer_id = _seed(factory)
    with _client(factory) as client:
        _login(client)
        created = client.post(
            "/api/v1/sales/weight-orders",
            headers=_headers(client),
            json={
                "customer_id": customer_id,
                "warehouse_id": warehouse_id,
                "weight_mode": "total_card",
                "pricing_mode": "uniform",
                "total_actual_weight_kg": "48",
                "uniform_price_per_kg": "20",
                "lines": [{"product_id": product_id, "quantity": "5"}],
            },
        ).json()
        cancelled = client.post(
            f"/api/v1/sales/orders/{created['id']}/cancellation",
            headers=_headers(client),
            json={"version": created["version"], "reason": "العميل ألغى الطلب"},
        )
        assert cancelled.status_code == 200, cancelled.text
        result = cancelled.json()
        assert result["status"] == "cancelled"
        assert result["weight_cards"][0]["status"] == "cancelled"
        refused = client.post(
            f"/api/v1/sales/orders/{created['id']}/delivery",
            headers=_headers(client, "cancelled-weight-delivery"),
            json={"version": result["version"]},
        )
        assert refused.status_code == 409

    with factory() as db:
        balance = db.get(InventoryBalance, (UUID(product_id), UUID(warehouse_id)))
        assert balance is not None
        assert balance.quantity_on_hand == Decimal("100.000000")
        assert balance.weight_on_hand_kg == Decimal("1000.000000")
        assert db.scalar(select(func.count(CustomerInvoice.id))) == 0


def test_delivery_reversal_restores_exact_stock_and_reverses_invoice() -> None:
    factory = _database()
    product_id, warehouse_id, customer_id = _seed(factory)
    with _client(factory) as client:
        _login(client)
        order = client.post(
            "/api/v1/sales/orders",
            headers=_headers(client),
            json={
                "customer_id": customer_id,
                "warehouse_id": warehouse_id,
                "lines": [{"product_id": product_id, "quantity": "3", "unit_price": "100"}],
            },
        ).json()
        delivered = client.post(
            f"/api/v1/sales/orders/{order['id']}/delivery",
            headers=_headers(client, "piece-delivery-reverse-0001"),
            json={"version": order["version"]},
        ).json()
        reversed_response = client.post(
            f"/api/v1/sales/deliveries/{delivered['delivery']['id']}/reversal",
            headers=_headers(client, "piece-reversal-0001"),
            json={"reason": "إلغاء تسليم اختباري"},
        )
        assert reversed_response.status_code == 200, reversed_response.text
        reversed_order = reversed_response.json()
        assert reversed_order["status"] == "reversed"
        assert reversed_order["invoice"]["status"] == "reversed"
        assert reversed_order["delivery"]["status"] == "reversed"

    with factory() as db:
        balance = db.get(InventoryBalance, (UUID(product_id), UUID(warehouse_id)))
        assert balance is not None
        assert balance.quantity_on_hand == Decimal("100.000000")
        assert balance.weight_on_hand_kg == Decimal("1000.000000")


def test_piece_and_weight_permissions_are_isolated_for_read_write_and_reversal() -> None:
    factory = _database()
    product_id, warehouse_id, customer_id = _seed(factory)
    with _client(factory) as admin:
        _login(admin)
        piece = admin.post(
            "/api/v1/sales/orders",
            headers=_headers(admin),
            json={
                "customer_id": customer_id,
                "warehouse_id": warehouse_id,
                "lines": [{"product_id": product_id, "quantity": "2", "unit_price": "100"}],
            },
        ).json()
        weight = admin.post(
            "/api/v1/sales/weight-orders",
            headers=_headers(admin),
            json={
                "customer_id": customer_id,
                "warehouse_id": warehouse_id,
                "weight_mode": "total_card",
                "pricing_mode": "uniform",
                "total_actual_weight_kg": "19",
                "uniform_price_per_kg": "20",
                "lines": [{"product_id": product_id, "quantity": "2"}],
            },
        ).json()
        piece_delivery = admin.post(
            f"/api/v1/sales/orders/{piece['id']}/delivery",
            headers=_headers(admin, "permission-piece-delivery"),
            json={"version": piece["version"]},
        ).json()["delivery"]
        weight_delivery = admin.post(
            f"/api/v1/sales/orders/{weight['id']}/delivery",
            headers=_headers(admin, "permission-weight-delivery"),
            json={"version": weight["version"]},
        ).json()["delivery"]

        for role_code, permissions, username, password in (
            (
                "piece_clerk",
                ["sales.read", "sales.manage"],
                "piece-clerk",
                PIECE_CLERK_PASSWORD,
            ),
            (
                "weight_clerk",
                ["weight_sales.read", "weight_sales.manage"],
                "weight-clerk",
                WEIGHT_CLERK_PASSWORD,
            ),
        ):
            role = admin.post(
                "/api/v1/identity/roles",
                headers=_headers(admin),
                json={
                    "code": role_code,
                    "name_ar": f"دور {role_code}",
                    "permissions": permissions,
                },
            )
            assert role.status_code == 201, role.text
            user = admin.post(
                "/api/v1/identity/users",
                headers=_headers(admin),
                json={
                    "username": username,
                    "display_name": f"مستخدم {role_code}",
                    "password": password,
                    "role_codes": [role_code],
                    "must_change_password": False,
                },
            )
            assert user.status_code == 201, user.text

    with _client(factory) as piece_client:
        _login(piece_client, "piece-clerk", PIECE_CLERK_PASSWORD)
        rows = piece_client.get("/api/v1/sales/orders")
        assert rows.status_code == 200
        assert {item["billing_method"] for item in rows.json()} == {"piece"}
        assert piece_client.get(f"/api/v1/sales/orders/{weight['id']}").status_code == 403
        assert (
            piece_client.post(
                "/api/v1/sales/weight-orders",
                headers=_headers(piece_client),
                json={
                    "customer_id": customer_id,
                    "warehouse_id": warehouse_id,
                    "weight_mode": "total_card",
                    "pricing_mode": "uniform",
                    "total_actual_weight_kg": "10",
                    "uniform_price_per_kg": "20",
                    "lines": [{"product_id": product_id, "quantity": "1"}],
                },
            ).status_code
            == 403
        )
        assert (
            piece_client.post(
                f"/api/v1/sales/deliveries/{weight_delivery['id']}/reversal",
                headers=_headers(piece_client, "denied-weight-reversal"),
                json={"reason": "محاولة غير مصرح بها"},
            ).status_code
            == 403
        )

    with _client(factory) as weight_client:
        _login(weight_client, "weight-clerk", WEIGHT_CLERK_PASSWORD)
        rows = weight_client.get("/api/v1/sales/orders")
        assert rows.status_code == 200
        assert {item["billing_method"] for item in rows.json()} == {"weight"}
        assert weight_client.get(f"/api/v1/sales/orders/{piece['id']}").status_code == 403
        assert (
            weight_client.post(
                "/api/v1/sales/orders",
                headers=_headers(weight_client),
                json={
                    "customer_id": customer_id,
                    "warehouse_id": warehouse_id,
                    "lines": [{"product_id": product_id, "quantity": "1", "unit_price": "100"}],
                },
            ).status_code
            == 403
        )
        assert (
            weight_client.post(
                f"/api/v1/sales/deliveries/{piece_delivery['id']}/reversal",
                headers=_headers(weight_client, "denied-piece-reversal"),
                json={"reason": "محاولة غير مصرح بها"},
            ).status_code
            == 403
        )

    app.dependency_overrides.clear()
