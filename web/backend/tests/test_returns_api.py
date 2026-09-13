import os
from collections.abc import Generator
from decimal import Decimal
from secrets import token_urlsafe
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

TEST_PASSWORD = token_urlsafe(32)
os.environ.setdefault("SECRET_KEY", token_urlsafe(48))
os.environ.setdefault("APP_ENV", "test")

from app.infrastructure.database.base import Base  # noqa: E402
from app.infrastructure.database.session import get_database_session  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.identity.models import User  # noqa: E402
from app.modules.identity.service import ClientContext, create_initial_admin  # noqa: E402
from app.modules.inventory.models import (  # noqa: E402
    InventoryAllocation,
    InventoryBalance,
    InventoryLayer,
    InventoryTransaction,
)
from app.modules.inventory.service import post_exact_layer_issue  # noqa: E402
from app.modules.master_data.models import (  # noqa: E402
    DocumentSequence,
    Partner,
    Product,
    UnitOfMeasure,
    Warehouse,
)
from app.modules.purchasing.models import (  # noqa: E402
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    SupplierInvoice,
)
from app.modules.returns.models import (  # noqa: E402
    InvoiceReturn,
    InvoiceReturnLine,
    InvoiceReturnSource,
    ReturnRefund,
)
from app.modules.sales.models import (  # noqa: E402
    CustomerInvoice,
    SalesDelivery,
    SalesDeliveryLine,
    SalesOrder,
    SalesOrderLine,
)
from app.modules.treasury.models import (  # noqa: E402
    FinancialAccount,
    PaymentAllocation,
    PaymentTransaction,
)
from app.modules.treasury.service import list_partner_balances  # noqa: E402


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


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text


def _headers(client: TestClient, key: str) -> dict[str, str]:
    csrf = client.cookies.get("pipeerp_csrf")
    assert csrf is not None
    return {"X-CSRF-Token": csrf, "Idempotency-Key": key}


def _seed_sales(factory: sessionmaker[Session]) -> dict[str, str]:
    with factory.begin() as db:
        create_initial_admin(
            db,
            username="admin",
            display_name="مدير النظام",
            password=TEST_PASSWORD,
            client=ClientContext("127.0.0.1", "test", "bootstrap"),
        )
        actor_id = db.scalar(select(User.id).where(User.normalized_username == "admin"))
        assert actor_id is not None
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
        customer = Partner(
            code="CUS-RET",
            normalized_code="CUS-RET",
            name_ar="عميل المرتجع",
            phone="",
            address="",
            tax_number="",
            is_customer=True,
            is_supplier=False,
            is_active=True,
            version=1,
        )
        cash = FinancialAccount(
            code="CASH-RET",
            normalized_code="CASH-RET",
            name_ar="خزينة المرتجعات",
            account_type="cash",
            opening_balance=0,
            is_default=True,
            is_active=True,
            notes="",
            version=1,
        )
        db.add_all([unit, warehouse, customer, cash])
        db.flush()
        product = Product(
            code="FG-RET",
            normalized_code="FG-RET",
            name_ar="منتج مرتجع",
            product_type="finished_good",
            unit_id=unit.id,
            category_id=None,
            min_stock=0,
            track_lots=True,
            standard_weight_kg=0,
            weight_tolerance_percent=5,
            is_active=True,
            version=1,
        )
        db.add(product)
        db.flush()
        order = SalesOrder(
            order_number="SO-RET-1",
            customer_id=customer.id,
            warehouse_id=warehouse.id,
            billing_method="piece",
            status="delivered",
            notes="",
            subtotal=100,
            discount_amount=0,
            transport_amount=0,
            tax_amount=0,
            total=100,
            version=1,
            created_by_id=actor_id,
        )
        db.add(order)
        db.flush()
        order_line = SalesOrderLine(
            sales_order_id=order.id,
            product_id=product.id,
            quantity=2,
            unit="قطعة",
            unit_price=50,
            line_total=100,
            standard_weight_kg=0,
            billing_weight_kg=0,
            price_per_kg=0,
            notes="",
        )
        db.add(order_line)
        db.flush()
        issue = InventoryTransaction(
            idempotency_key="original-sales-issue",
            transaction_type="issue",
            product_id=product.id,
            warehouse_id=warehouse.id,
            lot_id=None,
            quantity_delta=-2,
            weight_delta_kg=0,
            unit_cost=10,
            total_cost=20,
            cost_basis="quantity",
            reference_type="sales_delivery",
            reference_id="seed-delivery",
            reference_line_id=str(order_line.id),
            reversal_of_id=None,
            notes="",
            posted_by_id=actor_id,
        )
        db.add(issue)
        db.flush()
        delivery = SalesDelivery(
            delivery_number="SD-RET-1",
            sales_order_id=order.id,
            idempotency_key="seed-sales-delivery",
            request_hash="0" * 64,
            status="posted",
            posted_by_id=actor_id,
            reversal_reason="",
        )
        db.add(delivery)
        db.flush()
        db.add(
            SalesDeliveryLine(
                sales_delivery_id=delivery.id,
                sales_order_line_id=order_line.id,
                inventory_transaction_id=issue.id,
                quantity=2,
                weight_kg=0,
                cost_amount=20,
            )
        )
        invoice = CustomerInvoice(
            invoice_number="SI-RET-1",
            sales_order_id=order.id,
            customer_id=customer.id,
            invoice_type="standard",
            status="posted",
            subtotal=100,
            discount_amount=0,
            transport_amount=0,
            tax_amount=0,
            total=100,
            notes="",
            version=1,
        )
        db.add(invoice)
        db.flush()
        payment = PaymentTransaction(
            transaction_number="CR-RET-1",
            transaction_type="customer_receipt",
            partner_id=customer.id,
            financial_account_id=cash.id,
            amount=100,
            payment_method="cash",
            reference_type="sale",
            reference_id=order.id,
            customer_invoice_id=invoice.id,
            supplier_invoice_id=None,
            idempotency_key="seed-customer-receipt",
            request_hash="1" * 64,
            status="posted",
            notes="",
            posted_by_id=actor_id,
            reversal_reason="",
        )
        db.add(payment)
        db.flush()
        db.add(
            PaymentAllocation(
                payment_transaction_id=payment.id,
                customer_invoice_id=invoice.id,
                supplier_invoice_id=None,
                amount=100,
            )
        )
        opening_layer = InventoryLayer(
            product_id=product.id,
            warehouse_id=warehouse.id,
            lot_id=None,
            source_type="opening",
            source_id="seed",
            source_line_id="seed",
            cost_basis="quantity",
            quantity_received=10,
            quantity_remaining=8,
            weight_received_kg=0,
            weight_remaining_kg=0,
            unit_cost=10,
            version=1,
        )
        db.add(opening_layer)
        db.flush()
        db.add_all(
            [
                InventoryAllocation(
                    outbound_transaction_id=issue.id,
                    source_layer_id=opening_layer.id,
                    quantity=2,
                    weight_kg=0,
                    unit_cost=10,
                    total_cost=20,
                ),
                InventoryBalance(
                    product_id=product.id,
                    warehouse_id=warehouse.id,
                    quantity_on_hand=8,
                    weight_on_hand_kg=0,
                    version=1,
                ),
            ]
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
                    ("sales_return", "SR-"),
                    ("customer_refund", "CRF-"),
                )
            ]
        )
        db.flush()
        return {
            "invoice": str(invoice.id),
            "line": str(order_line.id),
            "customer": str(customer.id),
            "cash": str(cash.id),
            "product": str(product.id),
            "warehouse": str(warehouse.id),
            "issue": str(issue.id),
            "source_layer": str(opening_layer.id),
        }


def test_sales_return_refund_and_safe_reversal_flow() -> None:
    factory = _database()
    ids = _seed_sales(factory)
    with _client(factory) as client:
        _login(client)
        lines = client.get(f"/api/v1/returns/invoices/sales/{ids['invoice']}/lines")
        assert lines.status_code == 200, lines.text
        assert lines.json()[0]["remaining_quantity"] == "2.000000"

        returned = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "sales-return-idempotent-0001"),
            json={
                "return_type": "sales",
                "invoice_id": ids["invoice"],
                "reason": "عيب في قطعة",
                "lines": [{"source_line_id": ids["line"], "quantity": "1"}],
            },
        )
        assert returned.status_code == 201, returned.text
        document = returned.json()
        assert document["total"] == "50.00"
        assert document["lines"][0]["inventory_cost"] == "10.000000"

        repeated = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "sales-return-idempotent-0001"),
            json={
                "return_type": "sales",
                "invoice_id": ids["invoice"],
                "reason": "عيب في قطعة",
                "lines": [{"source_line_id": ids["line"], "quantity": "1"}],
            },
        )
        assert repeated.status_code == 201
        assert repeated.json()["id"] == document["id"]

        invoices = client.get("/api/v1/returns/invoices?return_type=sales")
        assert invoices.status_code == 200
        invoice = invoices.json()[0]
        assert invoice["net_total"] == "50.00"
        assert invoice["refundable"] == "50.00"

        refund = client.post(
            "/api/v1/returns/refunds",
            headers=_headers(client, "customer-refund-idempotent-0001"),
            json={
                "refund_type": "customer_refund",
                "invoice_id": ids["invoice"],
                "financial_account_id": ids["cash"],
                "amount": "50",
                "payment_method": "cash",
                "notes": "رد قيمة القطعة",
            },
        )
        assert refund.status_code == 201, refund.text
        refund_document = refund.json()

        blocked = client.post(
            f"/api/v1/returns/documents/{document['id']}/reverse",
            headers=_headers(client, "sales-return-reverse-blocked"),
            json={"version": document["version"], "reason": "تصحيح المستند"},
        )
        assert blocked.status_code == 409

        reversed_refund = client.post(
            f"/api/v1/returns/refunds/{refund_document['id']}/reverse",
            headers=_headers(client, "customer-refund-reverse-0001"),
            json={"version": refund_document["version"], "reason": "تصحيح رد المبلغ"},
        )
        assert reversed_refund.status_code == 200, reversed_refund.text
        reversed_return = client.post(
            f"/api/v1/returns/documents/{document['id']}/reverse",
            headers=_headers(client, "sales-return-reverse-0001"),
            json={"version": document["version"], "reason": "تصحيح المستند"},
        )
        assert reversed_return.status_code == 200, reversed_return.text

    with factory() as db:
        balance = db.get(
            InventoryBalance,
            (UUID(ids["product"]), UUID(ids["warehouse"])),
        )
        assert balance is not None and balance.quantity_on_hand == Decimal("8.000000")
        stored_return = db.scalar(select(InvoiceReturn))
        stored_refund = db.scalar(select(ReturnRefund))
        line = db.scalar(select(InvoiceReturnLine))
        assert stored_return is not None and stored_return.status == "reversed"
        assert stored_refund is not None and stored_refund.status == "reversed"
        assert line is not None and line.reversal_inventory_transaction_id is not None
        return_layer = db.scalar(
            select(InventoryLayer).where(
                InventoryLayer.source_type == "sales_return",
                InventoryLayer.source_id == str(stored_return.id),
            )
        )
        assert return_layer is not None and return_layer.quantity_remaining == 0
        partner_balance = next(
            item
            for item in list_partner_balances(db, partner_type="customer")
            if str(item.partner_id) == ids["customer"]
        )
        assert partner_balance.balance == Decimal("0.00")


def test_sales_single_layer_full_return_has_no_lot_fallback_and_exact_sources() -> None:
    factory = _database()
    ids = _seed_sales(factory)
    with _client(factory) as client:
        _login(client)
        rows = client.get(
            f"/api/v1/returns/invoices/sales/{ids['invoice']}/lines"
        )
        assert rows.status_code == 200, rows.text
        source = rows.json()[0]["sources"][0]
        assert source["lot_number"] == ""
        assert source["source_reference"] == "SD-RET-1"
        assert source["warehouse_name_ar"] == "المصنع"
        assert source["stable_label"] == "مصدر التسليم 1"
        assert "unit_cost" not in source
        returned = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "sales-single-full-return-0001"),
            json={
                "return_type": "sales",
                "invoice_id": ids["invoice"],
                "reason": "مرتجع كامل من مصدر واحد",
                "lines": [
                    {"source_line_id": ids["line"], "mode": "full_remaining"}
                ],
            },
        )
        assert returned.status_code == 201, returned.text
        assert returned.json()["lines"][0]["quantity"] == "2.000000"
        assert returned.json()["lines"][0]["inventory_cost"] == "20.000000"

    with factory() as db:
        line = db.scalar(select(InvoiceReturnLine))
        assert line is not None
        source_totals = db.execute(
            select(
                func.sum(InvoiceReturnSource.quantity),
                func.sum(InvoiceReturnSource.weight_kg),
            ).where(InvoiceReturnSource.invoice_return_line_id == line.id)
        ).one()
        assert source_totals == (line.quantity, line.weight_kg)


def _seed_purchase(factory: sessionmaker[Session]) -> dict[str, str]:
    with factory.begin() as db:
        actor_id = db.scalar(select(User.id).where(User.normalized_username == "admin"))
        warehouse = db.scalar(select(Warehouse).where(Warehouse.code == "MAIN"))
        unit = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "PCS"))
        cash = db.scalar(select(FinancialAccount).where(FinancialAccount.code == "CASH-RET"))
        assert actor_id is not None and warehouse is not None and unit is not None and cash
        supplier = Partner(
            code="SUP-RET",
            normalized_code="SUP-RET",
            name_ar="مورد المرتجع",
            phone="",
            address="",
            tax_number="",
            is_customer=False,
            is_supplier=True,
            is_active=True,
            version=1,
        )
        product = Product(
            code="RAW-RET",
            normalized_code="RAW-RET",
            name_ar="خامة مرتجعة للمورد",
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
        db.add_all([supplier, product])
        db.flush()
        order = PurchaseOrder(
            order_number="PO-RET-1",
            supplier_id=supplier.id,
            warehouse_id=warehouse.id,
            status="received",
            notes="",
            total=100,
            version=1,
            created_by_id=actor_id,
        )
        db.add(order)
        db.flush()
        order_line = PurchaseOrderLine(
            purchase_order_id=order.id,
            product_id=product.id,
            cost_basis="quantity",
            ordered_quantity=5,
            ordered_weight_kg=0,
            unit_price=20,
            additional_unit_cost=0,
            line_total=100,
            received_quantity=5,
            received_weight_kg=0,
            version=1,
        )
        db.add(order_line)
        db.flush()
        receipt_transaction = InventoryTransaction(
            idempotency_key="seed-purchase-receipt-move",
            transaction_type="receipt",
            product_id=product.id,
            warehouse_id=warehouse.id,
            lot_id=None,
            quantity_delta=5,
            weight_delta_kg=0,
            unit_cost=15,
            total_cost=75,
            cost_basis="quantity",
            reference_type="purchase_receipt",
            reference_id="seed-purchase-receipt",
            reference_line_id=str(order_line.id),
            reversal_of_id=None,
            notes="",
            posted_by_id=actor_id,
        )
        db.add(receipt_transaction)
        db.flush()
        receipt = PurchaseReceipt(
            receipt_number="GRN-RET-1",
            idempotency_key="seed-purchase-receipt",
            request_hash="2" * 64,
            purchase_order_id=order.id,
            status="posted",
            notes="",
            posted_by_id=actor_id,
            reversal_reason="",
        )
        db.add(receipt)
        db.flush()
        db.add(
            PurchaseReceiptLine(
                purchase_receipt_id=receipt.id,
                purchase_order_line_id=order_line.id,
                inventory_transaction_id=receipt_transaction.id,
                lot_number="",
                gross_quantity=5,
                gross_weight_kg=0,
                loss_quantity=0,
                loss_weight_kg=0,
                net_quantity=5,
                net_weight_kg=0,
                capitalized_cost=75,
                inventory_unit_cost=15,
            )
        )
        invoice = SupplierInvoice(
            invoice_number="PI-RET-1",
            supplier_invoice_number="SUP-INV-RET-1",
            purchase_order_id=order.id,
            supplier_id=supplier.id,
            status="posted",
            total=100,
            version=1,
        )
        db.add(invoice)
        db.flush()
        payment = PaymentTransaction(
            transaction_number="SP-RET-1",
            transaction_type="supplier_payment",
            partner_id=supplier.id,
            financial_account_id=cash.id,
            amount=100,
            payment_method="cash",
            reference_type="purchase",
            reference_id=order.id,
            customer_invoice_id=None,
            supplier_invoice_id=invoice.id,
            idempotency_key="seed-supplier-payment",
            request_hash="3" * 64,
            status="posted",
            notes="",
            posted_by_id=actor_id,
            reversal_reason="",
        )
        db.add(payment)
        db.flush()
        db.add(
            PaymentAllocation(
                payment_transaction_id=payment.id,
                customer_invoice_id=None,
                supplier_invoice_id=invoice.id,
                amount=100,
            )
        )
        db.add_all(
            [
                InventoryLayer(
                    product_id=product.id,
                    warehouse_id=warehouse.id,
                    lot_id=None,
                    source_type="purchase_receipt",
                    source_id=str(receipt.id),
                    source_line_id=str(order_line.id),
                    cost_basis="quantity",
                    quantity_received=5,
                    quantity_remaining=5,
                    weight_received_kg=0,
                    weight_remaining_kg=0,
                    unit_cost=15,
                    version=1,
                ),
                InventoryBalance(
                    product_id=product.id,
                    warehouse_id=warehouse.id,
                    quantity_on_hand=5,
                    weight_on_hand_kg=0,
                    version=1,
                ),
                DocumentSequence(
                    document_type="purchase_return",
                    prefix="PR-",
                    next_value=1,
                    padding=6,
                    version=1,
                ),
                DocumentSequence(
                    document_type="supplier_refund",
                    prefix="SRF-",
                    next_value=1,
                    padding=6,
                    version=1,
                ),
            ]
        )
        db.flush()
        return {
            "invoice": str(invoice.id),
            "line": str(order_line.id),
            "supplier": str(supplier.id),
            "cash": str(cash.id),
            "product": str(product.id),
            "warehouse": str(warehouse.id),
            "receipt": str(receipt.id),
            "receipt_transaction": str(receipt_transaction.id),
        }


def test_purchase_return_uses_receipt_source_and_supplier_refund_is_capped() -> None:
    factory = _database()
    _seed_sales(factory)
    ids = _seed_purchase(factory)
    with _client(factory) as client:
        _login(client)
        returned = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "purchase-return-idempotent-0001"),
            json={
                "return_type": "purchase",
                "invoice_id": ids["invoice"],
                "reason": "خامة غير مطابقة",
                "lines": [{"source_line_id": ids["line"], "quantity": "2"}],
            },
        )
        assert returned.status_code == 201, returned.text
        document = returned.json()
        assert document["total"] == "40.00"
        assert document["lines"][0]["inventory_cost"] == "30.000000"

        over_return = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "purchase-return-over-limit"),
            json={
                "return_type": "purchase",
                "invoice_id": ids["invoice"],
                "reason": "تجاوز المتاح",
                "lines": [{"source_line_id": ids["line"], "quantity": "4"}],
            },
        )
        assert over_return.status_code == 409

        over_refund = client.post(
            "/api/v1/returns/refunds",
            headers=_headers(client, "supplier-refund-over-limit"),
            json={
                "refund_type": "supplier_refund",
                "invoice_id": ids["invoice"],
                "financial_account_id": ids["cash"],
                "amount": "41",
                "payment_method": "cash",
            },
        )
        assert over_refund.status_code == 409
        refund = client.post(
            "/api/v1/returns/refunds",
            headers=_headers(client, "supplier-refund-idempotent-0001"),
            json={
                "refund_type": "supplier_refund",
                "invoice_id": ids["invoice"],
                "financial_account_id": ids["cash"],
                "amount": "40",
                "payment_method": "cash",
            },
        )
        assert refund.status_code == 201, refund.text
        refund_document = refund.json()

        reversed_refund = client.post(
            f"/api/v1/returns/refunds/{refund_document['id']}/reverse",
            headers=_headers(client, "supplier-refund-reverse-0001"),
            json={"version": refund_document["version"], "reason": "تصحيح الاسترداد"},
        )
        assert reversed_refund.status_code == 200
        reversed_return = client.post(
            f"/api/v1/returns/documents/{document['id']}/reverse",
            headers=_headers(client, "purchase-return-reverse-0001"),
            json={"version": document["version"], "reason": "تصحيح المرتجع"},
        )
        assert reversed_return.status_code == 200, reversed_return.text

    with factory() as db:
        balance = db.get(
            InventoryBalance,
            (UUID(ids["product"]), UUID(ids["warehouse"])),
        )
        assert balance is not None and balance.quantity_on_hand == Decimal("5.000000")
        partner_balance = next(
            item
            for item in list_partner_balances(db, partner_type="supplier")
            if str(item.partner_id) == ids["supplier"]
        )
        assert partner_balance.balance == Decimal("0.00")


def test_purchase_repeated_partial_returns_track_commercial_and_source_totals() -> None:
    factory = _database()
    _seed_sales(factory)
    ids = _seed_purchase(factory)
    with _client(factory) as client:
        _login(client)
        for index, amount in enumerate(("2", "1"), start=1):
            returned = client.post(
                "/api/v1/returns/documents",
                headers=_headers(client, f"purchase-repeated-partial-{index:04d}"),
                json={
                    "return_type": "purchase",
                    "invoice_id": ids["invoice"],
                    "reason": f"مرتجع شراء جزئي رقم {index}",
                    "lines": [{"source_line_id": ids["line"], "quantity": amount}],
                },
            )
            assert returned.status_code == 201, returned.text

        lines = client.get(
            f"/api/v1/returns/invoices/purchase/{ids['invoice']}/lines"
        )
        assert lines.status_code == 200, lines.text
        assert lines.json()[0]["returned_quantity"] == "3.000000"
        assert lines.json()[0]["remaining_quantity"] == "2.000000"
        exceeded = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "purchase-repeated-partial-exceeded-0001"),
            json={
                "return_type": "purchase",
                "invoice_id": ids["invoice"],
                "reason": "تجاوز المتاح من استلام الشراء",
                "lines": [{"source_line_id": ids["line"], "quantity": "3"}],
            },
        )
        assert exceeded.status_code == 409
        assert (
            exceeded.json()["detail"]["code"]
            == "PURCHASE_RETURN_ATTRIBUTABLE_STOCK_INSUFFICIENT"
        )

    with factory() as db:
        lines = list(db.scalars(select(InvoiceReturnLine)))
        for line in lines:
            source_quantity = db.scalar(
                select(func.sum(InvoiceReturnSource.quantity)).where(
                    InvoiceReturnSource.invoice_return_line_id == line.id
                )
            )
            assert source_quantity == line.quantity


def _make_sales_delivery_use_two_cost_layers(
    factory: sessionmaker[Session], ids: dict[str, str]
) -> tuple[UUID, UUID]:
    with factory.begin() as db:
        issue = db.get(InventoryTransaction, UUID(ids["issue"]))
        first_layer = db.get(InventoryLayer, UUID(ids["source_layer"]))
        first_allocation = db.scalar(
            select(InventoryAllocation).where(
                InventoryAllocation.outbound_transaction_id == issue.id
            )
        )
        balance = db.get(
            InventoryBalance,
            (UUID(ids["product"]), UUID(ids["warehouse"])),
        )
        assert issue is not None and first_layer is not None
        assert first_allocation is not None and balance is not None
        first_layer.quantity_received = Decimal("10")
        first_layer.quantity_remaining = Decimal("9")
        first_layer.unit_cost = Decimal("100")
        first_allocation.quantity = Decimal("1")
        first_allocation.unit_cost = Decimal("100")
        first_allocation.total_cost = Decimal("100")
        second_layer = InventoryLayer(
            product_id=first_layer.product_id,
            warehouse_id=first_layer.warehouse_id,
            lot_id=None,
            source_type="opening",
            source_id="seed-second-cost-layer",
            source_line_id="seed-second-cost-layer",
            cost_basis="quantity",
            quantity_received=10,
            quantity_remaining=9,
            weight_received_kg=0,
            weight_remaining_kg=0,
            unit_cost=200,
            version=1,
        )
        db.add(second_layer)
        db.flush()
        second_allocation = InventoryAllocation(
            outbound_transaction_id=issue.id,
            source_layer_id=second_layer.id,
            quantity=1,
            weight_kg=0,
            unit_cost=200,
            total_cost=200,
        )
        db.add(second_allocation)
        issue.unit_cost = Decimal("150")
        issue.total_cost = Decimal("300")
        balance.quantity_on_hand = Decimal("18")
        db.flush()
        return first_allocation.id, second_allocation.id


def _configure_purchase_stock(
    factory: sessionmaker[Session],
    ids: dict[str, str],
    *,
    gross: Decimal,
    loss: Decimal,
    remaining: Decimal,
    unit_cost: Decimal,
    unrelated_quantity: Decimal = Decimal("0"),
    unrelated_cost: Decimal = Decimal("100"),
) -> tuple[UUID, UUID | None]:
    with factory.begin() as db:
        order_line = db.get(PurchaseOrderLine, UUID(ids["line"]))
        receipt_line = db.scalar(
            select(PurchaseReceiptLine).where(
                PurchaseReceiptLine.purchase_order_line_id == order_line.id
            )
        )
        transaction = db.get(
            InventoryTransaction, UUID(ids["receipt_transaction"])
        )
        target_layer = db.scalar(
            select(InventoryLayer).where(
                InventoryLayer.source_type == "purchase_receipt",
                InventoryLayer.source_id == ids["receipt"],
            )
        )
        balance = db.get(
            InventoryBalance,
            (UUID(ids["product"]), UUID(ids["warehouse"])),
        )
        assert order_line is not None and receipt_line is not None
        assert transaction is not None and target_layer is not None and balance is not None
        net = gross - loss
        order_line.ordered_quantity = gross
        order_line.received_quantity = gross
        order_line.unit_price = Decimal("20")
        order_line.line_total = gross * Decimal("20")
        receipt_line.gross_quantity = gross
        receipt_line.loss_quantity = loss
        receipt_line.net_quantity = net
        receipt_line.capitalized_cost = net * unit_cost
        receipt_line.inventory_unit_cost = unit_cost
        transaction.quantity_delta = net
        transaction.unit_cost = unit_cost
        transaction.total_cost = net * unit_cost
        target_layer.quantity_received = net
        target_layer.quantity_remaining = remaining
        target_layer.unit_cost = unit_cost
        target_layer.source_transaction_id = transaction.id
        balance.quantity_on_hand = remaining + unrelated_quantity
        unrelated_layer_id: UUID | None = None
        if unrelated_quantity > 0:
            unrelated_layer = InventoryLayer(
                product_id=target_layer.product_id,
                warehouse_id=target_layer.warehouse_id,
                lot_id=None,
                source_type="opening",
                source_id="unrelated-old-stock",
                source_line_id="unrelated-old-stock",
                cost_basis="quantity",
                quantity_received=unrelated_quantity,
                quantity_remaining=unrelated_quantity,
                weight_received_kg=0,
                weight_remaining_kg=0,
                unit_cost=unrelated_cost,
                version=1,
            )
            db.add(unrelated_layer)
            db.flush()
            unrelated_layer_id = unrelated_layer.id
        db.flush()
        return target_layer.id, unrelated_layer_id


def test_sales_full_return_preserves_two_original_allocation_costs() -> None:
    factory = _database()
    ids = _seed_sales(factory)
    allocation_ids = _make_sales_delivery_use_two_cost_layers(factory, ids)
    with _client(factory) as client:
        _login(client)
        result = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "sales-multi-full-return-0001"),
            json={
                "return_type": "sales",
                "invoice_id": ids["invoice"],
                "reason": "مرتجع كامل متعدد الطبقات",
                "lines": [
                    {"source_line_id": ids["line"], "mode": "full_remaining"}
                ],
            },
        )
        assert result.status_code == 201, result.text
        assert result.json()["lines"][0]["quantity"] == "2.000000"
        assert result.json()["lines"][0]["inventory_cost"] == "300.000000"

    with factory() as db:
        sources = list(
            db.scalars(select(InvoiceReturnSource).order_by(InvoiceReturnSource.unit_cost))
        )
        assert [item.original_inventory_allocation_id for item in sources] == sorted(
            allocation_ids, key=lambda item: db.get(InventoryAllocation, item).unit_cost
        )
        assert [(item.quantity, item.unit_cost) for item in sources] == [
            (Decimal("1.000000"), Decimal("100.000000")),
            (Decimal("1.000000"), Decimal("200.000000")),
        ]
        return_layers = [
            db.get(InventoryLayer, item.return_inventory_layer_id) for item in sources
        ]
        assert [(item.quantity_received, item.unit_cost) for item in return_layers if item] == [
            (Decimal("1.000000"), Decimal("100.000000")),
            (Decimal("1.000000"), Decimal("200.000000")),
        ]


def test_sales_partial_multi_source_requires_and_respects_selection() -> None:
    factory = _database()
    ids = _seed_sales(factory)
    _make_sales_delivery_use_two_cost_layers(factory, ids)
    with _client(factory) as client:
        _login(client)
        rows = client.get(
            f"/api/v1/returns/invoices/sales/{ids['invoice']}/lines"
        ).json()
        assert len(rows[0]["sources"]) == 2
        missing = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "sales-multi-missing-source-0001"),
            json={
                "return_type": "sales",
                "invoice_id": ids["invoice"],
                "reason": "اختيار مصدر مطلوب",
                "lines": [{"source_line_id": ids["line"], "quantity": "0.5"}],
            },
        )
        assert missing.status_code == 409
        with factory() as db:
            expensive = db.scalar(
                select(InventoryAllocation).where(InventoryAllocation.unit_cost == 200)
            )
            assert expensive is not None
            expensive_id = str(expensive.id)
        selected = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "sales-multi-selected-source-0001"),
            json={
                "return_type": "sales",
                "invoice_id": ids["invoice"],
                "reason": "مرتجع من الطبقة الأعلى",
                "lines": [
                    {
                        "source_line_id": ids["line"],
                        "mode": "selected_sources",
                        "sources": [{"source_id": expensive_id, "quantity": "0.5"}],
                    }
                ],
            },
        )
        assert selected.status_code == 201, selected.text
        assert selected.json()["lines"][0]["inventory_cost"] == "100.000000"


def test_sales_repeated_partial_returns_cannot_exceed_original_allocation() -> None:
    factory = _database()
    ids = _seed_sales(factory)
    allocation_ids = _make_sales_delivery_use_two_cost_layers(factory, ids)
    selected_source_id = str(allocation_ids[0])
    with _client(factory) as client:
        _login(client)
        for index, amount in enumerate(("0.4", "0.6"), start=1):
            result = client.post(
                "/api/v1/returns/documents",
                headers=_headers(client, f"sales-repeated-partial-{index:04d}"),
                json={
                    "return_type": "sales",
                    "invoice_id": ids["invoice"],
                    "reason": f"مرتجع جزئي رقم {index}",
                    "lines": [
                        {
                            "source_line_id": ids["line"],
                            "mode": "selected_sources",
                            "sources": [
                                {"source_id": selected_source_id, "quantity": amount}
                            ],
                        }
                    ],
                },
            )
            assert result.status_code == 201, result.text

        rows = client.get(
            f"/api/v1/returns/invoices/sales/{ids['invoice']}/lines"
        )
        assert rows.status_code == 200, rows.text
        selected = next(
            source
            for source in rows.json()[0]["sources"]
            if source["source_id"] == selected_source_id
        )
        assert selected["already_returned_quantity"] == "1.000000"
        assert selected["remaining_returnable_quantity"] == "0.000000"

        exceeded = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "sales-repeated-partial-exceeded-0001"),
            json={
                "return_type": "sales",
                "invoice_id": ids["invoice"],
                "reason": "محاولة تجاوز المصدر الأصلي",
                "lines": [
                    {
                        "source_line_id": ids["line"],
                        "mode": "selected_sources",
                        "sources": [
                            {"source_id": selected_source_id, "quantity": "0.1"}
                        ],
                    }
                ],
            },
        )
        assert exceeded.status_code == 409

    with factory() as db:
        returned = db.scalar(
            select(func.sum(InvoiceReturnSource.quantity)).where(
                InvoiceReturnSource.original_inventory_allocation_id
                == UUID(selected_source_id)
            )
        )
        assert returned == Decimal("1.000000")


def test_weight_sales_return_uses_document_price_per_kg_and_source_cost() -> None:
    factory = _database()
    ids = _seed_sales(factory)
    with factory.begin() as db:
        order_line = db.get(SalesOrderLine, UUID(ids["line"]))
        order = db.get(SalesOrder, order_line.sales_order_id if order_line else None)
        invoice = db.get(CustomerInvoice, UUID(ids["invoice"]))
        issue = db.get(InventoryTransaction, UUID(ids["issue"]))
        allocation = db.scalar(
            select(InventoryAllocation).where(
                InventoryAllocation.outbound_transaction_id == UUID(ids["issue"])
            )
        )
        source_layer = db.get(InventoryLayer, UUID(ids["source_layer"]))
        delivery_line = db.scalar(
            select(SalesDeliveryLine).where(
                SalesDeliveryLine.inventory_transaction_id == UUID(ids["issue"])
            )
        )
        balance = db.get(
            InventoryBalance,
            (UUID(ids["product"]), UUID(ids["warehouse"])),
        )
        assert order_line is not None and order is not None and invoice is not None
        assert issue is not None and allocation is not None and source_layer is not None
        assert delivery_line is not None and balance is not None
        order.billing_method = "weight"
        invoice.invoice_type = "weight"
        order_line.unit_price = Decimal("250")
        order_line.price_per_kg = Decimal("50")
        order_line.billing_weight_kg = Decimal("10")
        issue.cost_basis = "weight"
        issue.weight_delta_kg = Decimal("-10")
        issue.unit_cost = Decimal("3")
        issue.total_cost = Decimal("30")
        allocation.weight_kg = Decimal("10")
        allocation.unit_cost = Decimal("3")
        allocation.total_cost = Decimal("30")
        source_layer.cost_basis = "weight"
        source_layer.weight_received_kg = Decimal("100")
        source_layer.weight_remaining_kg = Decimal("90")
        source_layer.unit_cost = Decimal("3")
        delivery_line.weight_kg = Decimal("10")
        delivery_line.cost_amount = Decimal("30")
        balance.weight_on_hand_kg = Decimal("90")

    with _client(factory) as client:
        _login(client)
        lines = client.get(
            f"/api/v1/returns/invoices/sales/{ids['invoice']}/lines"
        )
        assert lines.status_code == 200, lines.text
        assert lines.json()[0]["cost_basis"] == "weight"
        assert lines.json()[0]["unit_price"] == "50.000000"
        returned = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "sales-weight-return-0001"),
            json={
                "return_type": "sales",
                "invoice_id": ids["invoice"],
                "reason": "مرتجع مبيعات بالوزن",
                "lines": [{"source_line_id": ids["line"], "weight_kg": "4"}],
            },
        )
        assert returned.status_code == 201, returned.text
        line = returned.json()["lines"][0]
        assert line["quantity"] == "0.800000"
        assert line["weight_kg"] == "4.000000"
        assert line["unit_price"] == "50.000000"
        assert line["line_total"] == "200.00"
        assert line["inventory_cost"] == "12.000000"


def test_sales_return_reversal_is_blocked_after_return_layer_consumption() -> None:
    factory = _database()
    ids = _seed_sales(factory)
    with _client(factory) as client:
        _login(client)
        returned = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "sales-consumed-return-0001"),
            json={
                "return_type": "sales",
                "invoice_id": ids["invoice"],
                "reason": "مرتجع سيستهلك لاحقًا",
                "lines": [{"source_line_id": ids["line"], "quantity": "1"}],
            },
        )
        assert returned.status_code == 201, returned.text
        document = returned.json()
        with factory.begin() as db:
            source = db.scalar(select(InvoiceReturnSource))
            actor = db.scalar(select(User).where(User.normalized_username == "admin"))
            assert source is not None and source.return_inventory_layer_id is not None
            assert actor is not None
            post_exact_layer_issue(
                db,
                source_layer_id=source.return_inventory_layer_id,
                product_id=UUID(ids["product"]),
                warehouse_id=UUID(ids["warehouse"]),
                requested_quantity=Decimal("1"),
                requested_weight_kg=Decimal("0"),
                cost_basis="quantity",
                idempotency_key="consume-sales-return-layer-0001",
                reference_type="test_consumption",
                reference_id=document["id"],
                reference_line_id=ids["line"],
                notes="استهلاك لاحق",
                actor_user_id=actor.id,
                client=ClientContext("127.0.0.1", "test", "consume-return"),
            )
        reversal = client.post(
            f"/api/v1/returns/documents/{document['id']}/reverse",
            headers=_headers(client, "sales-consumed-reversal-0001"),
            json={"version": document["version"], "reason": "محاولة عكس غير آمنة"},
        )
        assert reversal.status_code == 409


def test_purchase_return_consumes_target_receipt_not_unrelated_fifo_stock() -> None:
    factory = _database()
    _seed_sales(factory)
    ids = _seed_purchase(factory)
    target_layer_id, unrelated_layer_id = _configure_purchase_stock(
        factory,
        ids,
        gross=Decimal("100"),
        loss=Decimal("0"),
        remaining=Decimal("100"),
        unit_cost=Decimal("200"),
        unrelated_quantity=Decimal("100"),
        unrelated_cost=Decimal("100"),
    )
    with _client(factory) as client:
        _login(client)
        result = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "purchase-target-source-0001"),
            json={
                "return_type": "purchase",
                "invoice_id": ids["invoice"],
                "reason": "إرجاع من استلام الشراء المحدد",
                "lines": [{"source_line_id": ids["line"], "quantity": "20"}],
            },
        )
        assert result.status_code == 201, result.text
        assert result.json()["lines"][0]["inventory_cost"] == "4000.000000"

    with factory() as db:
        target = db.get(InventoryLayer, target_layer_id)
        unrelated = db.get(InventoryLayer, unrelated_layer_id)
        source = db.scalar(select(InvoiceReturnSource))
        assert target is not None and target.quantity_remaining == Decimal("80.000000")
        assert unrelated is not None and unrelated.quantity_remaining == Decimal("100.000000")
        assert source is not None and source.consumed_inventory_layer_id == target_layer_id
        assert source.unit_cost == Decimal("200.000000")


def test_purchase_full_return_rejects_attributable_shortage_atomically() -> None:
    factory = _database()
    _seed_sales(factory)
    ids = _seed_purchase(factory)
    target_layer_id, unrelated_layer_id = _configure_purchase_stock(
        factory,
        ids,
        gross=Decimal("20"),
        loss=Decimal("0"),
        remaining=Decimal("15"),
        unit_cost=Decimal("200"),
        unrelated_quantity=Decimal("100"),
    )
    with factory() as db:
        before_transactions = db.scalar(select(func.count(InventoryTransaction.id)))
    with _client(factory) as client:
        _login(client)
        result = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "purchase-attributable-shortage-0001"),
            json={
                "return_type": "purchase",
                "invoice_id": ids["invoice"],
                "reason": "اختبار رفض ذري",
                "lines": [
                    {"source_line_id": ids["line"], "mode": "full_remaining"}
                ],
            },
        )
        assert result.status_code == 409, result.text
        detail = result.json()["detail"]
        assert detail["code"] == "PURCHASE_RETURN_ATTRIBUTABLE_STOCK_INSUFFICIENT"
        assert "20.000000" in detail["message"]
        assert "15.000000" in detail["message"]
        assert "GRN-RET-1" in detail["message"]

    with factory() as db:
        assert db.scalar(select(func.count(InvoiceReturn.id))) == 0
        assert db.scalar(select(func.count(InvoiceReturnSource.id))) == 0
        assert db.scalar(select(func.count(InventoryTransaction.id))) == before_transactions
        target = db.get(InventoryLayer, target_layer_id)
        unrelated = db.get(InventoryLayer, unrelated_layer_id)
        assert target is not None and target.quantity_remaining == Decimal("15.000000")
        assert unrelated is not None and unrelated.quantity_remaining == Decimal("100.000000")


def test_purchase_loss_uses_net_received_amount_as_returnable_stock() -> None:
    factory = _database()
    _seed_sales(factory)
    ids = _seed_purchase(factory)
    _configure_purchase_stock(
        factory,
        ids,
        gross=Decimal("10"),
        loss=Decimal("2"),
        remaining=Decimal("8"),
        unit_cost=Decimal("25"),
    )
    with _client(factory) as client:
        _login(client)
        lines = client.get(
            f"/api/v1/returns/invoices/purchase/{ids['invoice']}/lines"
        )
        assert lines.status_code == 200, lines.text
        assert lines.json()[0]["remaining_quantity"] == "8.000000"
        result = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "purchase-loss-full-return-0001"),
            json={
                "return_type": "purchase",
                "invoice_id": ids["invoice"],
                "reason": "إرجاع صافي الاستلام",
                "lines": [
                    {"source_line_id": ids["line"], "mode": "full_remaining"}
                ],
            },
        )
        assert result.status_code == 201, result.text
        assert result.json()["lines"][0]["quantity"] == "8.000000"
        assert result.json()["lines"][0]["inventory_cost"] == "200.000000"


def test_purchase_return_reversal_layer_keeps_root_for_later_return() -> None:
    factory = _database()
    _seed_sales(factory)
    ids = _seed_purchase(factory)
    root_id, _ = _configure_purchase_stock(
        factory,
        ids,
        gross=Decimal("5"),
        loss=Decimal("0"),
        remaining=Decimal("5"),
        unit_cost=Decimal("15"),
    )
    with _client(factory) as client:
        _login(client)
        first = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "purchase-return-before-reversal-0001"),
            json={
                "return_type": "purchase",
                "invoice_id": ids["invoice"],
                "reason": "مرتجع أول",
                "lines": [{"source_line_id": ids["line"], "quantity": "2"}],
            },
        )
        assert first.status_code == 201, first.text
        reversed_result = client.post(
            f"/api/v1/returns/documents/{first.json()['id']}/reverse",
            headers=_headers(client, "purchase-source-reversal-0001"),
            json={"version": first.json()["version"], "reason": "عكس للاختبار"},
        )
        assert reversed_result.status_code == 200, reversed_result.text
        with factory() as db:
            first_source = db.scalar(select(InvoiceReturnSource))
            assert first_source is not None
            derivative_id = first_source.reversal_inventory_layer_id
            assert derivative_id is not None
            derivative = db.get(InventoryLayer, derivative_id)
            assert derivative is not None
            assert derivative.provenance_root_layer_id == root_id
            assert derivative.unit_cost == Decimal("15.000000")
        second = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "purchase-return-from-derivative-0001"),
            json={
                "return_type": "purchase",
                "invoice_id": ids["invoice"],
                "reason": "مرتجع من طبقة العكس",
                "lines": [
                    {
                        "source_line_id": ids["line"],
                        "mode": "selected_sources",
                        "sources": [{"source_id": str(derivative_id), "quantity": "1"}],
                    }
                ],
            },
        )
        assert second.status_code == 201, second.text
    with factory() as db:
        latest_source = db.scalar(
            select(InvoiceReturnSource)
            .where(InvoiceReturnSource.consumed_inventory_layer_id == derivative_id)
        )
        assert latest_source is not None
        assert latest_source.root_inventory_layer_id == root_id
        assert latest_source.unit_cost == Decimal("15.000000")


def test_multiple_purchase_return_reversal_layers_keep_one_immutable_root() -> None:
    factory = _database()
    _seed_sales(factory)
    ids = _seed_purchase(factory)
    root_id, _ = _configure_purchase_stock(
        factory,
        ids,
        gross=Decimal("5"),
        loss=Decimal("0"),
        remaining=Decimal("5"),
        unit_cost=Decimal("15"),
    )
    with _client(factory) as client:
        _login(client)
        for index in range(2):
            returned = client.post(
                "/api/v1/returns/documents",
                headers=_headers(client, f"purchase-derivative-source-{index:04d}"),
                json={
                    "return_type": "purchase",
                    "invoice_id": ids["invoice"],
                    "reason": f"مرتجع لإنشاء طبقة عكس رقم {index + 1}",
                    "lines": [
                        {
                            "source_line_id": ids["line"],
                            "mode": "selected_sources",
                            "sources": [
                                {"source_id": str(root_id), "quantity": "1"}
                            ],
                        }
                    ],
                },
            )
            assert returned.status_code == 201, returned.text
            reversed_result = client.post(
                f"/api/v1/returns/documents/{returned.json()['id']}/reverse",
                headers=_headers(client, f"purchase-derivative-reverse-{index:04d}"),
                json={
                    "version": returned.json()["version"],
                    "reason": "عكس لاختبار استمرار المصدر",
                },
            )
            assert reversed_result.status_code == 200, reversed_result.text

        final_return = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "purchase-all-derivatives-full-0001"),
            json={
                "return_type": "purchase",
                "invoice_id": ids["invoice"],
                "reason": "مرتجع كامل من الأصل وطبقات العكس",
                "lines": [
                    {"source_line_id": ids["line"], "mode": "full_remaining"}
                ],
            },
        )
        assert final_return.status_code == 201, final_return.text
        assert final_return.json()["lines"][0]["quantity"] == "5.000000"
        final_return_id = UUID(final_return.json()["id"])

    with factory() as db:
        derivative_layers = list(
            db.scalars(
                select(InventoryLayer).where(
                    InventoryLayer.provenance_root_layer_id == root_id
                )
            )
        )
        assert len(derivative_layers) == 2
        assert {layer.unit_cost for layer in derivative_layers} == {
            Decimal("15.000000")
        }
        final_sources = list(
            db.scalars(
                select(InvoiceReturnSource)
                .join(
                    InvoiceReturnLine,
                    InvoiceReturnLine.id == InvoiceReturnSource.invoice_return_line_id,
                )
                .where(InvoiceReturnLine.invoice_return_id == final_return_id)
            )
        )
        assert len(final_sources) == 3
        assert {source.root_inventory_layer_id for source in final_sources} == {
            root_id
        }
        assert sum((source.quantity for source in final_sources), Decimal("0")) == Decimal(
            "5.000000"
        )


def test_purchase_full_return_preserves_multiple_receipt_layer_costs() -> None:
    factory = _database()
    _seed_sales(factory)
    ids = _seed_purchase(factory)
    with factory.begin() as db:
        actor_id = db.scalar(select(User.id).where(User.normalized_username == "admin"))
        order_line = db.get(PurchaseOrderLine, UUID(ids["line"]))
        first_receipt = db.get(PurchaseReceipt, UUID(ids["receipt"]))
        invoice = db.get(SupplierInvoice, UUID(ids["invoice"]))
        balance = db.get(
            InventoryBalance,
            (UUID(ids["product"]), UUID(ids["warehouse"])),
        )
        assert actor_id is not None and order_line is not None and first_receipt is not None
        assert invoice is not None and balance is not None
        second_transaction = InventoryTransaction(
            idempotency_key="seed-second-purchase-receipt-move",
            transaction_type="receipt",
            product_id=UUID(ids["product"]),
            warehouse_id=UUID(ids["warehouse"]),
            lot_id=None,
            quantity_delta=3,
            weight_delta_kg=0,
            unit_cost=30,
            total_cost=90,
            cost_basis="quantity",
            reference_type="purchase_receipt",
            reference_id="seed-second-purchase-receipt",
            reference_line_id=ids["line"],
            reversal_of_id=None,
            notes="",
            posted_by_id=actor_id,
        )
        db.add(second_transaction)
        db.flush()
        second_receipt = PurchaseReceipt(
            receipt_number="GRN-RET-2",
            idempotency_key="seed-second-purchase-receipt",
            request_hash="4" * 64,
            purchase_order_id=first_receipt.purchase_order_id,
            status="posted",
            notes="",
            posted_by_id=actor_id,
            reversal_reason="",
        )
        db.add(second_receipt)
        db.flush()
        db.add(
            PurchaseReceiptLine(
                purchase_receipt_id=second_receipt.id,
                purchase_order_line_id=order_line.id,
                inventory_transaction_id=second_transaction.id,
                lot_number="LOT-SECOND",
                gross_quantity=3,
                gross_weight_kg=0,
                loss_quantity=0,
                loss_weight_kg=0,
                net_quantity=3,
                net_weight_kg=0,
                capitalized_cost=90,
                inventory_unit_cost=30,
            )
        )
        second_layer = InventoryLayer(
            product_id=UUID(ids["product"]),
            warehouse_id=UUID(ids["warehouse"]),
            lot_id=None,
            source_type="purchase_receipt",
            source_id=str(second_receipt.id),
            source_line_id=ids["line"],
            source_transaction_id=second_transaction.id,
            cost_basis="quantity",
            quantity_received=3,
            quantity_remaining=3,
            weight_received_kg=0,
            weight_remaining_kg=0,
            unit_cost=30,
            version=1,
        )
        db.add(second_layer)
        order_line.ordered_quantity = Decimal("8")
        order_line.received_quantity = Decimal("8")
        order_line.line_total = Decimal("160")
        invoice.total = Decimal("160")
        balance.quantity_on_hand = Decimal("8")

    with _client(factory) as client:
        _login(client)
        returned = client.post(
            "/api/v1/returns/documents",
            headers=_headers(client, "purchase-multi-receipt-full-0001"),
            json={
                "return_type": "purchase",
                "invoice_id": ids["invoice"],
                "reason": "مرتجع كامل من استلامات متعددة",
                "lines": [
                    {"source_line_id": ids["line"], "mode": "full_remaining"}
                ],
            },
        )
        assert returned.status_code == 201, returned.text
        assert returned.json()["lines"][0]["quantity"] == "8.000000"
        assert returned.json()["lines"][0]["line_total"] == "160.00"
        assert returned.json()["lines"][0]["inventory_cost"] == "165.000000"

    with factory() as db:
        sources = list(
            db.scalars(
                select(InvoiceReturnSource).order_by(InvoiceReturnSource.unit_cost)
            )
        )
        assert [(source.quantity, source.unit_cost) for source in sources] == [
            (Decimal("5.000000"), Decimal("15.000000")),
            (Decimal("3.000000"), Decimal("30.000000")),
        ]


def test_reversed_purchase_receipt_is_not_eligible_for_source_layer_return() -> None:
    factory = _database()
    _seed_sales(factory)
    ids = _seed_purchase(factory)
    with factory.begin() as db:
        original = db.get(InventoryTransaction, UUID(ids["receipt_transaction"]))
        actor_id = db.scalar(select(User.id).where(User.normalized_username == "admin"))
        assert original is not None and actor_id is not None
        db.add(
            InventoryTransaction(
                idempotency_key="seed-reversed-purchase-receipt",
                transaction_type="reversal_out",
                product_id=original.product_id,
                warehouse_id=original.warehouse_id,
                lot_id=original.lot_id,
                quantity_delta=-original.quantity_delta,
                weight_delta_kg=-original.weight_delta_kg,
                unit_cost=original.unit_cost,
                total_cost=original.total_cost,
                cost_basis=original.cost_basis,
                reference_type="reversal",
                reference_id=str(original.id),
                reference_line_id=original.reference_line_id,
                reversal_of_id=original.id,
                notes="عكس استلام الشراء",
                posted_by_id=actor_id,
            )
        )
    with _client(factory) as client:
        _login(client)
        response = client.get(
            f"/api/v1/returns/invoices/purchase/{ids['invoice']}/lines"
        )
        assert response.status_code == 409
        assert (
            response.json()["detail"]["code"]
            == "PURCHASE_RETURN_PROVENANCE_UNRESOLVED"
        )


def test_purchase_unresolved_and_ambiguous_provenance_are_blocked() -> None:
    factory = _database()
    _seed_sales(factory)
    ids = _seed_purchase(factory)
    with factory.begin() as db:
        layer = db.scalar(
            select(InventoryLayer).where(
                InventoryLayer.source_type == "purchase_receipt",
                InventoryLayer.source_id == ids["receipt"],
            )
        )
        assert layer is not None
        layer.source_id = "unresolved"
    with _client(factory) as client:
        _login(client)
        unresolved = client.get(
            f"/api/v1/returns/invoices/purchase/{ids['invoice']}/lines"
        )
        assert unresolved.status_code == 409
        assert (
            unresolved.json()["detail"]["code"]
            == "PURCHASE_RETURN_PROVENANCE_UNRESOLVED"
        )

    second_factory = _database()
    _seed_sales(second_factory)
    second_ids = _seed_purchase(second_factory)
    with second_factory.begin() as db:
        original = db.scalar(
            select(InventoryLayer).where(
                InventoryLayer.source_type == "purchase_receipt",
                InventoryLayer.source_id == second_ids["receipt"],
            )
        )
        assert original is not None
        db.add(
            InventoryLayer(
                product_id=original.product_id,
                warehouse_id=original.warehouse_id,
                lot_id=None,
                source_type=original.source_type,
                source_id=original.source_id,
                source_line_id=original.source_line_id,
                cost_basis=original.cost_basis,
                quantity_received=1,
                quantity_remaining=1,
                weight_received_kg=0,
                weight_remaining_kg=0,
                unit_cost=original.unit_cost,
                version=1,
            )
        )
    with _client(second_factory) as client:
        _login(client)
        ambiguous = client.get(
            f"/api/v1/returns/invoices/purchase/{second_ids['invoice']}/lines"
        )
        assert ambiguous.status_code == 409
        assert (
            ambiguous.json()["detail"]["code"]
            == "PURCHASE_RETURN_PROVENANCE_UNRESOLVED"
        )
