import os
from collections.abc import Generator

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
from app.modules.inventory.models import (  # noqa: E402
    InventoryAllocation,
    InventoryLayer,
    InventoryTransaction,
)
from app.modules.master_data.models import (  # noqa: E402
    CompanySettings,
    Product,
    UnitOfMeasure,
    Warehouse,
)


def database() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def client(factory: sessionmaker[Session]) -> TestClient:
    def override_database() -> Generator[Session, None, None]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_database_session] = override_database
    return TestClient(app)


def seed(factory: sessionmaker[Session]) -> tuple[str, str, str, str]:
    with factory.begin() as db:
        create_initial_admin(
            db,
            username="admin",
            display_name="مدير النظام",
            password="Admin-password-2026",
            client=ClientContext("127.0.0.1", "test", "bootstrap"),
        )
        unit = UnitOfMeasure(
            code="PCS",
            normalized_code="PCS",
            name_ar="قطعة",
            symbol="قطعة",
            decimal_places=0,
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
        secondary = Warehouse(
            code="SECONDARY",
            normalized_code="SECONDARY",
            name_ar="مخزن الفرع",
            is_default=False,
            is_active=True,
            version=1,
        )
        inactive = Warehouse(
            code="INACTIVE",
            normalized_code="INACTIVE",
            name_ar="مخزن متوقف",
            is_default=False,
            is_active=False,
            version=1,
        )
        db.add_all([unit, warehouse, secondary, inactive])
        db.flush()
        product = Product(
            code="FG-INV",
            normalized_code="FG-INV",
            name_ar="منتج مخزون",
            product_type="finished_good",
            unit_id=unit.id,
            category_id=None,
            min_stock=0,
            track_lots=True,
            standard_weight_kg=10,
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
        db.flush()
        return str(product.id), str(warehouse.id), str(secondary.id), str(inactive.id)


def login(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin-password-2026"},
    )
    assert response.status_code == 200, response.text


def headers(test_client: TestClient, key: str) -> dict[str, str]:
    csrf = test_client.cookies.get("pipeerp_csrf")
    assert csrf is not None
    return {"X-CSRF-Token": csrf, "Idempotency-Key": key}


def test_receipt_issue_fifo_idempotency_and_negative_stock_protection() -> None:
    factory = database()
    product_id, warehouse_id, secondary_id, inactive_id = seed(factory)
    with client(factory) as test_client:
        login(test_client)
        receipt_payload = {
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "quantity": "10",
            "weight_kg": "100",
            "cost_basis": "quantity",
            "unit_cost": "5",
            "lot_number": "LOT-001",
            "reference_type": "opening_balance",
            "reference_id": "OB-1",
        }
        receipt = test_client.post(
            "/api/v1/inventory/receipts",
            json=receipt_payload,
            headers=headers(test_client, "receipt-test-0001"),
        )
        assert receipt.status_code == 201, receipt.text
        assert receipt.json()["product_name_ar"] == "منتج مخزون"
        assert receipt.json()["warehouse_name_ar"] == "المصنع"
        repeated = test_client.post(
            "/api/v1/inventory/receipts",
            json=receipt_payload,
            headers=headers(test_client, "receipt-test-0001"),
        )
        assert repeated.status_code == 201
        assert repeated.json()["id"] == receipt.json()["id"]

        conflicting_replay = test_client.post(
            "/api/v1/inventory/issues",
            json={
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "amount": "1",
                "cost_basis": "quantity",
                "reference_type": "adjustment",
            },
            headers=headers(test_client, "receipt-test-0001"),
        )
        assert conflicting_replay.status_code == 409

        rejected = test_client.post(
            "/api/v1/inventory/issues",
            json={
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "amount": "12",
                "cost_basis": "quantity",
                "reference_type": "adjustment",
            },
            headers=headers(test_client, "issue-test-00001"),
        )
        assert rejected.status_code == 409

        issued = test_client.post(
            "/api/v1/inventory/issues",
            json={
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "amount": "4",
                "cost_basis": "quantity",
                "reference_type": "adjustment",
                "reference_id": "ADJ-1",
            },
            headers=headers(test_client, "issue-test-00002"),
        )
        assert issued.status_code == 201, issued.text
        assert issued.json()["quantity_delta"] == "-4.000000"
        assert issued.json()["weight_delta_kg"] == "-40.000000"
        assert issued.json()["total_cost"] == "20.000000"

        balances = test_client.get("/api/v1/inventory/balances")
        assert balances.status_code == 200
        assert balances.json()[0]["quantity_on_hand"] == "6.000000"
        assert balances.json()[0]["weight_on_hand_kg"] == "60.000000"
        assert balances.json()[0]["product_code"] == "FG-INV"

        options = test_client.get("/api/v1/inventory/options")
        assert options.status_code == 200
        assert options.json()["products"][0]["name_ar"] == "منتج مخزون"
        assert options.json()["warehouses"][0]["name_ar"] == "المصنع"

        transactions = test_client.get("/api/v1/inventory/transactions")
        assert transactions.status_code == 200
        assert {item["transaction_type"] for item in transactions.json()} == {"receipt", "issue"}
        assert all(item["product_name_ar"] == "منتج مخزون" for item in transactions.json())

        transfer = test_client.post(
            "/api/v1/inventory/transfers",
            json={
                "product_id": product_id,
                "source_warehouse_id": warehouse_id,
                "destination_warehouse_id": secondary_id,
                "amount": "2",
                "cost_basis": "quantity",
                "notes": "تحويل تجريبي",
            },
            headers=headers(test_client, "transfer-test-0001"),
        )
        assert transfer.status_code == 201, transfer.text
        assert transfer.json()["outbound"]["quantity_delta"] == "-2.000000"
        assert transfer.json()["inbound"]["quantity_delta"] == "2.000000"
        assert transfer.json()["outbound"]["total_cost"] == "10.000000"
        assert transfer.json()["inbound"]["total_cost"] == "10.000000"
        transfer_card = test_client.get(
            f"/api/v1/inventory/stock-card?product_id={product_id}&limit=500"
        )
        transfer_in_rows = [
            row
            for row in transfer_card.json()
            if row["transaction_id"] == transfer.json()["inbound"]["id"]
        ]
        assert [
            (row["lot_number"], row["quantity_in"], row["unit_cost"]) for row in transfer_in_rows
        ] == [("LOT-001", "2.000000", "5.000000")]

        failed_transfer = test_client.post(
            "/api/v1/inventory/transfers",
            json={
                "product_id": product_id,
                "source_warehouse_id": warehouse_id,
                "destination_warehouse_id": secondary_id,
                "amount": "99",
                "cost_basis": "quantity",
            },
            headers=headers(test_client, "transfer-test-0002"),
        )
        assert failed_transfer.status_code == 409
        atomic_failure = test_client.post(
            "/api/v1/inventory/transfers",
            json={
                "product_id": product_id,
                "source_warehouse_id": warehouse_id,
                "destination_warehouse_id": inactive_id,
                "amount": "1",
                "cost_basis": "quantity",
            },
            headers=headers(test_client, "transfer-test-0003"),
        )
        assert atomic_failure.status_code == 404
        balances_after_transfer = test_client.get("/api/v1/inventory/balances").json()
        indexed = {item["warehouse_id"]: item for item in balances_after_transfer}
        assert indexed[warehouse_id]["quantity_on_hand"] == "4.000000"
        assert indexed[secondary_id]["quantity_on_hand"] == "2.000000"

        adjustment = test_client.post(
            "/api/v1/inventory/adjustments",
            json={
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "direction": "increase",
                "quantity": "1",
                "weight_kg": "10",
                "cost_basis": "quantity",
                "unit_cost": "7",
                "reason": "نتيجة الجرد الفعلي",
            },
            headers=headers(test_client, "adjustment-test-0001"),
        )
        assert adjustment.status_code == 201, adjustment.text
        assert adjustment.json()["transaction_type"] == "adjustment_in"
        assert adjustment.json()["quantity_delta"] == "1.000000"

        reversal = test_client.post(
            f"/api/v1/inventory/transactions/{issued.json()['id']}/reversal",
            json={"reason": "إلغاء الصرف التجريبي بعد المراجعة"},
            headers=headers(test_client, "reversal-test-0001"),
        )
        assert reversal.status_code == 201, reversal.text
        assert reversal.json()["transaction_type"] == "reversal_in"
        assert reversal.json()["reversal_of_id"] == issued.json()["id"]
        assert reversal.json()["quantity_delta"] == "4.000000"

        repeated_reversal = test_client.post(
            f"/api/v1/inventory/transactions/{issued.json()['id']}/reversal",
            json={"reason": "محاولة عكس ثانية"},
            headers=headers(test_client, "reversal-test-0002"),
        )
        assert repeated_reversal.status_code == 409

    with factory() as db:
        assert db.scalar(select(func.count(InventoryTransaction.id))) == 6
        assert db.scalar(select(func.count(InventoryAllocation.id))) == 2
        stock_layers = list(db.scalars(select(InventoryLayer)))
        assert sum((item.quantity_remaining for item in stock_layers), 0) == 11
        assert sum((item.weight_remaining_kg for item in stock_layers), 0) == 110
        events = set(db.scalars(select(AuditLog.event_type)))
        assert {
            "inventory.receipt.post",
            "inventory.issue.post",
            "inventory.transfer_out.post",
            "inventory.transfer_in.post",
            "inventory.adjustment_in.post",
            "inventory.reversal_in.post",
        } <= events
    app.dependency_overrides.clear()


def test_stock_card_expands_fifo_issue_into_the_source_lots() -> None:
    factory = database()
    product_id, warehouse_id, _, _ = seed(factory)
    with client(factory) as test_client:
        login(test_client)
        for index, (lot_number, quantity, unit_cost) in enumerate(
            (("LOT-OLD", "5", "3"), ("LOT-NEW", "10", "7")), start=1
        ):
            response = test_client.post(
                "/api/v1/inventory/receipts",
                json={
                    "product_id": product_id,
                    "warehouse_id": warehouse_id,
                    "quantity": quantity,
                    "weight_kg": "0",
                    "cost_basis": "quantity",
                    "unit_cost": unit_cost,
                    "lot_number": lot_number,
                    "reference_type": "opening_balance",
                    "reference_id": f"OB-{index}",
                },
                headers=headers(test_client, f"stock-card-receipt-{index}"),
            )
            assert response.status_code == 201, response.text

        issue = test_client.post(
            "/api/v1/inventory/issues",
            json={
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "amount": "8",
                "cost_basis": "quantity",
                "reference_type": "manual_issue",
                "reference_id": "ISSUE-1",
            },
            headers=headers(test_client, "stock-card-issue-0001"),
        )
        assert issue.status_code == 201, issue.text

        response = test_client.get(
            f"/api/v1/inventory/stock-card?product_id={product_id}&limit=500"
        )
        assert response.status_code == 200, response.text
        rows = response.json()
        outbound = [row for row in rows if row["transaction_id"] == issue.json()["id"]]
        assert [(row["lot_number"], row["quantity_out"], row["unit_cost"]) for row in outbound] == [
            ("LOT-OLD", "5.000000", "3.000000"),
            ("LOT-NEW", "3.000000", "7.000000"),
        ]
        assert all(row["product_code"] == "FG-INV" for row in outbound)
        assert all(row["product_name_ar"] == "منتج مخزون" for row in outbound)
        assert all(row["warehouse_name_ar"] == "المصنع" for row in outbound)
        assert all(row["reference_number"] == "ISSUE-1" for row in outbound)
        assert all(row["partner_name_ar"] == "" for row in outbound)
    app.dependency_overrides.clear()
