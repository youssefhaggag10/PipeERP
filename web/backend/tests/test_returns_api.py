import os
from collections.abc import Generator
from decimal import Decimal
from secrets import token_urlsafe
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
    InventoryBalance,
    InventoryLayer,
    InventoryTransaction,
)
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
from app.modules.returns.models import InvoiceReturn, InvoiceReturnLine, ReturnRefund  # noqa: E402
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
        db.add_all(
            [
                InventoryLayer(
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
        }


def test_purchase_return_uses_fifo_and_supplier_refund_is_capped() -> None:
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
