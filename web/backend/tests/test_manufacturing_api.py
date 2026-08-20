import os
from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

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
from app.modules.inventory.models import (  # noqa: E402
    InventoryBalance,
    InventoryLayer,
)
from app.modules.manufacturing.models import (  # noqa: E402
    ManufacturingCompletion,
    ManufacturingMaterialIssue,
    ManufacturingOrder,
)
from app.modules.master_data.models import (  # noqa: E402
    CompanySettings,
    DocumentSequence,
    Product,
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


def _seed(factory: sessionmaker[Session]) -> dict[str, str]:
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
        db.add_all([unit, warehouse])
        db.flush()
        raw_a = Product(
            code="RAW-A",
            normalized_code="RAW-A",
            name_ar="خامة أ",
            product_type="raw_material",
            unit_id=unit.id,
            category_id=None,
            min_stock=0,
            track_lots=True,
            standard_weight_kg=0,
            weight_tolerance_percent=5,
            is_active=True,
            version=1,
        )
        raw_b = Product(
            code="RAW-B",
            normalized_code="RAW-B",
            name_ar="خامة ب",
            product_type="raw_material",
            unit_id=unit.id,
            category_id=None,
            min_stock=0,
            track_lots=True,
            standard_weight_kg=0,
            weight_tolerance_percent=5,
            is_active=True,
            version=1,
        )
        output = Product(
            code="PIPE-110",
            normalized_code="PIPE-110",
            name_ar="ماسورة 110",
            product_type="finished_good",
            unit_id=unit.id,
            category_id=None,
            min_stock=0,
            track_lots=True,
            standard_weight_kg=Decimal("1.5"),
            weight_tolerance_percent=5,
            is_active=True,
            version=1,
        )
        db.add_all([raw_a, raw_b, output])
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
                version=1,
            )
        )
        db.add(
            DocumentSequence(
                document_type="manufacturing_order",
                prefix="MO-",
                next_value=1,
                padding=6,
                version=1,
            )
        )
        for product, stock, cost in (
            (raw_a, Decimal("500"), Decimal("2")),
            (raw_b, Decimal("100"), Decimal("3")),
        ):
            db.add(
                InventoryBalance(
                    product_id=product.id,
                    warehouse_id=warehouse.id,
                    quantity_on_hand=stock,
                    weight_on_hand_kg=0,
                    version=1,
                )
            )
            db.add(
                InventoryLayer(
                    product_id=product.id,
                    warehouse_id=warehouse.id,
                    lot_id=None,
                    source_type="opening",
                    source_id=None,
                    source_line_id=None,
                    cost_basis="quantity",
                    quantity_received=stock,
                    quantity_remaining=stock,
                    weight_received_kg=0,
                    weight_remaining_kg=0,
                    unit_cost=cost,
                    received_at=datetime.now(UTC),
                    version=1,
                )
            )
        return {
            "warehouse": str(warehouse.id),
            "raw_a": str(raw_a.id),
            "raw_b": str(raw_b.id),
            "output": str(output.id),
        }


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


def _create_recipe_and_order(test_client: TestClient, ids: dict[str, str]) -> dict:
    recipe = test_client.post(
        "/api/v1/manufacturing/recipes",
        headers=_headers(test_client),
        json={
            "code": "PVC-110",
            "name_ar": "خلطة مواسير 110",
            "output_product_ids": [ids["output"]],
            "components": [
                {"product_id": ids["raw_a"], "quantity_per_batch": "90"},
                {"product_id": ids["raw_b"], "quantity_per_batch": "10"},
            ],
            "suggested_scrap_per_batch": "10",
        },
    )
    assert recipe.status_code == 201, recipe.text
    order = test_client.post(
        "/api/v1/manufacturing/orders",
        headers=_headers(test_client, "manufacturing-create-001"),
        json={
            "recipe_id": recipe.json()["id"],
            "warehouse_id": ids["warehouse"],
            "outputs": [{"product_id": ids["output"], "quantity": "100"}],
            "scrap_inputs": [],
            "notes": "اختبار دورة التصنيع",
        },
    )
    assert order.status_code == 201, order.text
    assert order.json()["planned_batches"] == 2
    return order.json()


def test_manufacturing_full_cycle_posts_fifo_outputs_scrap_and_completion() -> None:
    factory = _database()
    ids = _seed(factory)
    with _client(factory) as test_client:
        _login(test_client)
        order = _create_recipe_and_order(test_client, ids)
        started = test_client.post(
            f"/api/v1/manufacturing/orders/{order['id']}/start",
            headers=_headers(test_client, "manufacturing-start-001"),
            json={"version": order["version"]},
        )
        assert started.status_code == 200, started.text
        assert started.json()["status"] == "in_progress"
        completed = test_client.post(
            f"/api/v1/manufacturing/orders/{order['id']}/complete",
            headers=_headers(test_client, "manufacturing-complete-001"),
            json={
                "version": started.json()["version"],
                "actual_batches": 2,
                "scrap_weight_kg": "20",
                "outputs": [
                    {
                        "product_id": ids["output"],
                        "good_quantity": "100",
                        "defective_quantity": "2",
                        "actual_weight_kg": "150",
                    }
                ],
                "adjustments": [],
                "notes": "إكمال فعلي",
            },
        )
        assert completed.status_code == 200, completed.text
        result = completed.json()
        assert result["status"] == "completed"
        assert result["material_cost"] == "420.00"
        assert result["finished_cost"] == "378.00"
        assert result["weight_variance_kg"] == "30.000000"

    with factory() as db:
        output_balance = db.get(
            InventoryBalance, (UUID(ids["output"]), UUID(ids["warehouse"]))
        )
        assert output_balance is not None
        assert output_balance.quantity_on_hand == Decimal("100.000000")
        assert output_balance.weight_on_hand_kg == Decimal("150.000000")
        completion = db.scalar(select(ManufacturingCompletion))
        assert completion is not None
        assert completion.scrap_inventory_transaction_id is not None
        assert len(list(db.scalars(select(ManufacturingMaterialIssue)))) == 2


def test_cancelling_in_progress_order_returns_every_issued_material() -> None:
    factory = _database()
    ids = _seed(factory)
    with _client(factory) as test_client:
        _login(test_client)
        order = _create_recipe_and_order(test_client, ids)
        started = test_client.post(
            f"/api/v1/manufacturing/orders/{order['id']}/start",
            headers=_headers(test_client, "manufacturing-start-cancel"),
            json={"version": order["version"]},
        )
        assert started.status_code == 200, started.text
        cancelled = test_client.post(
            f"/api/v1/manufacturing/orders/{order['id']}/cancel",
            headers=_headers(test_client, "manufacturing-cancel-001"),
            json={"version": started.json()["version"], "reason": "إلغاء اختبار"},
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"

    with factory() as db:
        order_row = db.scalar(select(ManufacturingOrder))
        assert order_row is not None and order_row.status == "cancelled"
        for product_id, expected in ((ids["raw_a"], "500"), (ids["raw_b"], "100")):
            balance = db.get(
                InventoryBalance, (UUID(product_id), UUID(ids["warehouse"]))
            )
            assert balance is not None
            assert balance.quantity_on_hand == Decimal(expected)
        issues = list(db.scalars(select(ManufacturingMaterialIssue)))
        assert issues and all(item.reversal_transaction_id is not None for item in issues)


def test_start_is_idempotent_and_rejects_a_different_version_for_same_key() -> None:
    factory = _database()
    ids = _seed(factory)
    with _client(factory) as test_client:
        _login(test_client)
        order = _create_recipe_and_order(test_client, ids)
        first = test_client.post(
            f"/api/v1/manufacturing/orders/{order['id']}/start",
            headers=_headers(test_client, "manufacturing-start-repeat"),
            json={"version": order["version"]},
        )
        assert first.status_code == 200, first.text
        repeated = test_client.post(
            f"/api/v1/manufacturing/orders/{order['id']}/start",
            headers=_headers(test_client, "manufacturing-start-repeat"),
            json={"version": order["version"]},
        )
        assert repeated.status_code == 200, repeated.text
        conflict = test_client.post(
            f"/api/v1/manufacturing/orders/{order['id']}/start",
            headers=_headers(test_client, "manufacturing-start-repeat"),
            json={"version": first.json()["version"]},
        )
        assert conflict.status_code == 409


def test_draft_replan_adds_a_batch_when_selected_scrap_has_no_stock() -> None:
    factory = _database()
    ids = _seed(factory)
    with _client(factory) as test_client:
        _login(test_client)
        recipe = test_client.post(
            "/api/v1/manufacturing/recipes",
            headers=_headers(test_client),
            json={
                "code": "PVC-REPLAN",
                "name_ar": "خلطة إعادة التخطيط",
                "output_product_ids": [ids["output"]],
                "components": [
                    {"product_id": ids["raw_a"], "quantity_per_batch": "90"},
                    {"product_id": ids["raw_b"], "quantity_per_batch": "10"},
                ],
                "suggested_scrap_per_batch": "10",
            },
        )
        assert recipe.status_code == 201, recipe.text
        recipe_data = recipe.json()
        order = test_client.post(
            "/api/v1/manufacturing/orders",
            headers=_headers(test_client, "manufacturing-replan-create"),
            json={
                "recipe_id": recipe_data["id"],
                "warehouse_id": ids["warehouse"],
                "outputs": [{"product_id": ids["output"], "quantity": "134"}],
                "scrap_inputs": [
                    {
                        "product_id": recipe_data["scrap_product_id"],
                        "quantity_per_batch": "10",
                    }
                ],
            },
        )
        assert order.status_code == 201, order.text
        assert order.json()["planned_batches"] == 2
        preview = test_client.get(
            f"/api/v1/manufacturing/orders/{order.json()['id']}/replan-preview"
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["new_batches"] == 3
        assert preview.json()["usable_scrap_kg"] == "0.000000"
        applied = test_client.post(
            f"/api/v1/manufacturing/orders/{order.json()['id']}/replan",
            headers=_headers(test_client),
            json={"version": order.json()["version"]},
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["planned_batches"] == 3
        assert applied.json()["planned_input_weight_kg"] == "300.000000"


def test_additional_batch_shortage_rolls_back_every_extra_issue() -> None:
    factory = _database()
    ids = _seed(factory)
    with _client(factory) as test_client:
        _login(test_client)
        order = _create_recipe_and_order(test_client, ids)
        started = test_client.post(
            f"/api/v1/manufacturing/orders/{order['id']}/start",
            headers=_headers(test_client, "manufacturing-start-extra"),
            json={"version": order["version"]},
        )
        assert started.status_code == 200, started.text
        failed = test_client.post(
            f"/api/v1/manufacturing/orders/{order['id']}/complete",
            headers=_headers(test_client, "manufacturing-complete-extra-short"),
            json={
                "version": started.json()["version"],
                "actual_batches": 6,
                "scrap_weight_kg": "0",
                "outputs": [
                    {
                        "product_id": ids["output"],
                        "good_quantity": "100",
                        "defective_quantity": "0",
                        "actual_weight_kg": "150",
                    }
                ],
                "adjustments": [],
            },
        )
        assert failed.status_code == 409, failed.text

    with factory() as db:
        order_row = db.scalar(select(ManufacturingOrder))
        assert order_row is not None
        assert order_row.status == "in_progress"
        assert order_row.issued_batches == 2
        assert len(list(db.scalars(select(ManufacturingMaterialIssue)))) == 2
        expected_balances = {ids["raw_a"]: Decimal("320"), ids["raw_b"]: Decimal("80")}
        for product_id, expected in expected_balances.items():
            balance = db.get(
                InventoryBalance, (UUID(product_id), UUID(ids["warehouse"]))
            )
            assert balance is not None
            assert balance.quantity_on_hand == expected


def test_modified_mix_persists_report_and_returns_excluded_material() -> None:
    factory = _database()
    ids = _seed(factory)
    with _client(factory) as test_client:
        _login(test_client)
        order = _create_recipe_and_order(test_client, ids)
        started = test_client.post(
            f"/api/v1/manufacturing/orders/{order['id']}/start",
            headers=_headers(test_client, "manufacturing-start-modified"),
            json={"version": order["version"]},
        )
        assert started.status_code == 200, started.text
        completed = test_client.post(
            f"/api/v1/manufacturing/orders/{order['id']}/complete",
            headers=_headers(test_client, "manufacturing-complete-modified"),
            json={
                "version": started.json()["version"],
                "actual_batches": 2,
                "scrap_weight_kg": "20",
                "outputs": [
                    {
                        "product_id": ids["output"],
                        "good_quantity": "100",
                        "defective_quantity": "1",
                        "actual_weight_kg": "150",
                    }
                ],
                "adjustments": [
                    {
                        "excluded_product_id": ids["raw_b"],
                        "batch_count": 1,
                        "reason": "تشغيل خلطة بدون خامة ب",
                        "actual_material_quantities": [
                            {"product_id": ids["raw_a"], "actual_quantity": "90"}
                        ],
                    }
                ],
            },
        )
        assert completed.status_code == 200, completed.text
        report = completed.json()["completion"]
        assert report["full_batches"] == 1
        assert report["modified_batches"] == 1
        assert report["adjustments"][0]["excluded_product_name_ar"] == "خامة ب"
        quantities = {
            item["product_id"]: item["actual_quantity"]
            for item in report["adjustments"][0]["actual_material_quantities"]
        }
        assert quantities[ids["raw_a"]] == "90.000000"
        assert quantities[ids["raw_b"]] == "0.000000"

    with factory() as db:
        balance = db.get(
            InventoryBalance, (UUID(ids["raw_b"]), UUID(ids["warehouse"]))
        )
        assert balance is not None
        assert balance.quantity_on_hand == Decimal("90.000000")
