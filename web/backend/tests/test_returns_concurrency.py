import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from secrets import token_urlsafe
from threading import Barrier
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.modules.identity.models import User
from app.modules.identity.service import ClientContext, Principal, create_initial_admin
from app.modules.inventory.models import InventoryBalance, InventoryLayer, InventoryTransaction
from app.modules.inventory.schemas import ReceiptRequest
from app.modules.inventory.service import post_receipt
from app.modules.master_data.models import Partner, Product, UnitOfMeasure, Warehouse
from app.modules.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    SupplierInvoice,
)
from app.modules.returns.models import InvoiceReturn, ReturnRefund
from app.modules.returns.schemas import CreateInvoiceReturnRequest, CreateRefundRequest
from app.modules.returns.service import ReturnsConflict, create_refund, create_return
from app.modules.sales.models import CustomerInvoice, SalesOrder, SalesOrderLine
from app.modules.sales.schemas import CreatePieceLineRequest, CreatePieceOrderRequest
from app.modules.sales.service import create_piece_order, deliver_sales_order
from app.modules.treasury.models import (
    FinancialAccount,
    PaymentAllocation,
    PaymentTransaction,
)


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL customer-invoice row-lock test",
)
def test_five_concurrent_refunds_consume_the_available_balance_only_once() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], pool_size=6)
    suffix = uuid4().hex[:10].upper()
    with Session(engine) as db, db.begin():
        actor = db.scalar(select(User).order_by(User.created_at))
        if actor is None:
            actor = create_initial_admin(
                db,
                username=f"returns-admin-{suffix.lower()}",
                display_name="مدير اختبار المرتجعات",
                password=token_urlsafe(32),
                client=ClientContext("127.0.0.1", "test", "returns-concurrency"),
            )
        warehouse = db.scalar(select(Warehouse).where(Warehouse.code == "MAIN"))
        assert warehouse is not None
        customer = Partner(
            code=f"RET-CUS-{suffix}",
            normalized_code=f"RET-CUS-{suffix}",
            name_ar="عميل اختبار الاسترداد المتزامن",
            phone="",
            address="",
            tax_number="",
            is_customer=True,
            is_supplier=False,
            is_active=True,
            version=1,
        )
        account = FinancialAccount(
            code=f"RET-CASH-{suffix}",
            normalized_code=f"RET-CASH-{suffix}",
            name_ar="خزينة اختبار الاسترداد المتزامن",
            account_type="cash",
            opening_balance=Decimal("1000"),
            is_default=False,
            is_active=True,
            notes="",
            version=1,
        )
        db.add_all([customer, account])
        db.flush()
        order = SalesOrder(
            order_number=f"RET-SO-{suffix}",
            customer_id=customer.id,
            warehouse_id=warehouse.id,
            billing_method="piece",
            status="delivered",
            notes="",
            subtotal=Decimal("100"),
            discount_amount=0,
            transport_amount=0,
            tax_amount=0,
            total=Decimal("100"),
            version=1,
            created_by_id=actor.id,
        )
        db.add(order)
        db.flush()
        invoice = CustomerInvoice(
            invoice_number=f"RET-SI-{suffix}",
            sales_order_id=order.id,
            customer_id=customer.id,
            invoice_type="standard",
            status="posted",
            subtotal=Decimal("100"),
            discount_amount=0,
            transport_amount=0,
            tax_amount=0,
            total=Decimal("100"),
            notes="",
            version=1,
        )
        db.add(invoice)
        db.flush()
        payment = PaymentTransaction(
            transaction_number=f"RET-CR-{suffix}",
            transaction_type="customer_receipt",
            partner_id=customer.id,
            financial_account_id=account.id,
            amount=Decimal("100"),
            payment_method="cash",
            reference_type="sale",
            reference_id=order.id,
            customer_invoice_id=invoice.id,
            supplier_invoice_id=None,
            idempotency_key=f"ret-payment-{suffix}",
            request_hash="0" * 64,
            status="posted",
            notes="",
            posted_by_id=actor.id,
            reversal_reason="",
        )
        db.add(payment)
        db.flush()
        db.add_all(
            [
                PaymentAllocation(
                    payment_transaction_id=payment.id,
                    customer_invoice_id=invoice.id,
                    supplier_invoice_id=None,
                    amount=Decimal("100"),
                ),
                InvoiceReturn(
                    return_number=f"RET-SR-{suffix}",
                    return_type="sales",
                    customer_invoice_id=invoice.id,
                    supplier_invoice_id=None,
                    partner_id=customer.id,
                    warehouse_id=warehouse.id,
                    total=Decimal("100"),
                    reason="مرتجع كامل لاختبار قفل رصيد الاسترداد",
                    status="posted",
                    idempotency_key=f"ret-document-{suffix}",
                    request_hash="1" * 64,
                    posted_by_id=actor.id,
                    reversal_reason="",
                    version=1,
                ),
            ]
        )
        db.flush()
        actor_id = actor.id
        invoice_id = invoice.id
        account_id = account.id

    barrier = Barrier(5)

    def refund(index: int) -> str:
        try:
            with Session(engine) as db, db.begin():
                actor = db.get(User, actor_id)
                assert actor is not None
                barrier.wait()
                result = create_refund(
                    db,
                    payload=CreateRefundRequest(
                        refund_type="customer_refund",
                        invoice_id=invoice_id,
                        financial_account_id=account_id,
                        amount=Decimal("100"),
                        payment_method="cash",
                        notes="اختبار خمسة مستخدمين",
                    ),
                    idempotency_key=f"refund-concurrency-{suffix}-{index}",
                    actor=cast(Principal, SimpleNamespace(user=actor)),
                    client=ClientContext("127.0.0.1", "test", f"refund-{index}"),
                )
                return result.status
        except ReturnsConflict:
            return "rejected"

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(refund, range(5)))

    assert results.count("posted") == 1
    assert results.count("rejected") == 4
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count(ReturnRefund.id)).where(
                    ReturnRefund.customer_invoice_id == invoice_id,
                    ReturnRefund.status == "posted",
                )
            )
            == 1
        )
        assert db.scalar(
            select(func.sum(ReturnRefund.amount)).where(
                ReturnRefund.customer_invoice_id == invoice_id,
                ReturnRefund.status == "posted",
            )
        ) == Decimal("100.00")


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL source-layer return row-lock test",
)
def test_two_concurrent_full_sales_returns_cannot_exceed_delivery_allocation() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], pool_size=4)
    suffix = uuid4().hex[:10].upper()
    with Session(engine) as db, db.begin():
        actor = db.scalar(select(User).order_by(User.created_at))
        if actor is None:
            actor = create_initial_admin(
                db,
                username=f"source-return-admin-{suffix.lower()}",
                display_name="مدير اختبار مصدر المرتجع",
                password=token_urlsafe(32),
                client=ClientContext("127.0.0.1", "test", "returns-concurrency"),
            )
        unit = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "KG"))
        warehouse = db.scalar(select(Warehouse).where(Warehouse.code == "MAIN"))
        assert unit is not None
        assert warehouse is not None
        customer = Partner(
            code=f"SRC-RET-CUS-{suffix}",
            normalized_code=f"SRC-RET-CUS-{suffix}",
            name_ar="عميل اختبار مصدر المرتجع المتزامن",
            phone="",
            address="",
            tax_number="",
            is_customer=True,
            is_supplier=False,
            is_active=True,
            version=1,
        )
        product = Product(
            code=f"SRC-RET-PROD-{suffix}",
            normalized_code=f"SRC-RET-PROD-{suffix}",
            name_ar="منتج اختبار مصدر المرتجع المتزامن",
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
        db.add_all([customer, product])
        db.flush()
        post_receipt(
            db,
            payload=ReceiptRequest(
                product_id=product.id,
                warehouse_id=warehouse.id,
                quantity=Decimal("2"),
                weight_kg=0,
                cost_basis="quantity",
                unit_cost=Decimal("125"),
                lot_number=f"SRC-RET-LOT-{suffix}",
                reference_type="returns_concurrency_test",
            ),
            idempotency_key=f"source-return-stock-{suffix}",
            actor_user_id=actor.id,
            client=ClientContext("127.0.0.1", "test", "returns-concurrency"),
        )
        order = create_piece_order(
            db,
            payload=CreatePieceOrderRequest(
                customer_id=customer.id,
                warehouse_id=warehouse.id,
                lines=[
                    CreatePieceLineRequest(
                        product_id=product.id,
                        quantity=Decimal("2"),
                        unit_price=Decimal("200"),
                    )
                ],
            ),
            actor=cast(Principal, SimpleNamespace(user=actor)),
            client=ClientContext("127.0.0.1", "test", "returns-concurrency"),
        )
        delivered = deliver_sales_order(
            db,
            order_id=order.id,
            version=order.version,
            idempotency_key=f"source-return-delivery-{suffix}",
            actor=cast(Principal, SimpleNamespace(user=actor)),
            client=ClientContext("127.0.0.1", "test", "returns-concurrency"),
        )
        invoice = db.scalar(
            select(CustomerInvoice).where(CustomerInvoice.sales_order_id == order.id)
        )
        line_id = db.scalar(
            select(SalesOrderLine.id).where(SalesOrderLine.sales_order_id == order.id)
        )
        assert delivered.delivery is not None
        assert invoice is not None
        assert line_id is not None
        actor_id = actor.id
        invoice_id = invoice.id

    barrier = Barrier(2)

    def return_all(index: int) -> str:
        try:
            with Session(engine) as db, db.begin():
                actor = db.get(User, actor_id)
                assert actor is not None
                barrier.wait()
                result = create_return(
                    db,
                    payload=CreateInvoiceReturnRequest.model_validate(
                        {
                            "return_type": "sales",
                            "invoice_id": invoice_id,
                            "reason": "اختبار مرتجع كامل متزامن",
                            "lines": [
                                {
                                    "source_line_id": line_id,
                                    "mode": "full_remaining",
                                }
                            ],
                        }
                    ),
                    idempotency_key=f"source-return-concurrency-{suffix}-{index}",
                    actor=cast(Principal, SimpleNamespace(user=actor)),
                    client=ClientContext(
                        "127.0.0.1", "test", f"source-return-{index}"
                    ),
                )
                return result.status
        except ReturnsConflict:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(return_all, range(2)))

    assert results.count("posted") == 1
    assert results.count("rejected") == 1
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count(InvoiceReturn.id)).where(
                    InvoiceReturn.customer_invoice_id == invoice_id,
                    InvoiceReturn.status == "posted",
                )
            )
            == 1
        )


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL purchase-return source-layer row-lock test",
)
def test_two_concurrent_full_purchase_returns_cannot_consume_root_twice() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], pool_size=4)
    suffix = uuid4().hex[:10].upper()
    with Session(engine) as db, db.begin():
        actor = db.scalar(select(User).order_by(User.created_at))
        if actor is None:
            actor = create_initial_admin(
                db,
                username=f"purchase-return-admin-{suffix.lower()}",
                display_name="مدير اختبار مرتجع الشراء",
                password=token_urlsafe(32),
                client=ClientContext("127.0.0.1", "test", "returns-concurrency"),
            )
        unit = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "KG"))
        warehouse = db.scalar(select(Warehouse).where(Warehouse.code == "MAIN"))
        assert unit is not None
        assert warehouse is not None
        supplier = Partner(
            code=f"SRC-RET-SUP-{suffix}",
            normalized_code=f"SRC-RET-SUP-{suffix}",
            name_ar="مورد اختبار مرتجع الشراء المتزامن",
            phone="",
            address="",
            tax_number="",
            is_customer=False,
            is_supplier=True,
            is_active=True,
            version=1,
        )
        product = Product(
            code=f"SRC-RET-RAW-{suffix}",
            normalized_code=f"SRC-RET-RAW-{suffix}",
            name_ar="خامة اختبار مرتجع الشراء المتزامن",
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
            order_number=f"SRC-RET-PO-{suffix}",
            supplier_id=supplier.id,
            warehouse_id=warehouse.id,
            status="received",
            notes="",
            total=Decimal("2000"),
            version=1,
            created_by_id=actor.id,
        )
        db.add(order)
        db.flush()
        line = PurchaseOrderLine(
            purchase_order_id=order.id,
            product_id=product.id,
            cost_basis="quantity",
            ordered_quantity=Decimal("10"),
            ordered_weight_kg=0,
            unit_price=Decimal("200"),
            additional_unit_cost=0,
            line_total=Decimal("2000"),
            received_quantity=Decimal("10"),
            received_weight_kg=0,
            version=1,
        )
        db.add(line)
        db.flush()
        receipt = PurchaseReceipt(
            receipt_number=f"SRC-RET-GRN-{suffix}",
            idempotency_key=f"source-return-receipt-{suffix}",
            request_hash="5" * 64,
            purchase_order_id=order.id,
            status="posted",
            notes="",
            posted_by_id=actor.id,
            reversal_reason="",
        )
        db.add(receipt)
        db.flush()
        transaction = InventoryTransaction(
            idempotency_key=f"source-return-receipt-move-{suffix}",
            transaction_type="receipt",
            product_id=product.id,
            warehouse_id=warehouse.id,
            lot_id=None,
            quantity_delta=Decimal("10"),
            weight_delta_kg=0,
            unit_cost=Decimal("150"),
            total_cost=Decimal("1500"),
            cost_basis="quantity",
            reference_type="purchase_receipt",
            reference_id=str(receipt.id),
            reference_line_id=str(line.id),
            reversal_of_id=None,
            notes="",
            posted_by_id=actor.id,
        )
        db.add(transaction)
        db.flush()
        db.add(
            PurchaseReceiptLine(
                purchase_receipt_id=receipt.id,
                purchase_order_line_id=line.id,
                inventory_transaction_id=transaction.id,
                lot_number=f"SRC-RET-LOT-{suffix}",
                gross_quantity=Decimal("10"),
                gross_weight_kg=0,
                loss_quantity=0,
                loss_weight_kg=0,
                net_quantity=Decimal("10"),
                net_weight_kg=0,
                capitalized_cost=Decimal("1500"),
                inventory_unit_cost=Decimal("150"),
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
                    source_line_id=str(line.id),
                    source_transaction_id=transaction.id,
                    cost_basis="quantity",
                    quantity_received=Decimal("10"),
                    quantity_remaining=Decimal("10"),
                    weight_received_kg=0,
                    weight_remaining_kg=0,
                    unit_cost=Decimal("150"),
                    version=1,
                ),
                InventoryBalance(
                    product_id=product.id,
                    warehouse_id=warehouse.id,
                    quantity_on_hand=Decimal("10"),
                    weight_on_hand_kg=0,
                    version=1,
                ),
            ]
        )
        invoice = SupplierInvoice(
            invoice_number=f"SRC-RET-PI-{suffix}",
            supplier_invoice_number=f"EXT-{suffix}",
            purchase_order_id=order.id,
            supplier_id=supplier.id,
            status="posted",
            total=Decimal("2000"),
            version=1,
        )
        db.add(invoice)
        db.flush()
        actor_id = actor.id
        invoice_id = invoice.id
        line_id = line.id

    barrier = Barrier(2)

    def return_all(index: int) -> str:
        try:
            with Session(engine) as db, db.begin():
                actor = db.get(User, actor_id)
                assert actor is not None
                barrier.wait()
                result = create_return(
                    db,
                    payload=CreateInvoiceReturnRequest.model_validate(
                        {
                            "return_type": "purchase",
                            "invoice_id": invoice_id,
                            "reason": "اختبار مرتجع شراء كامل متزامن",
                            "lines": [
                                {
                                    "source_line_id": line_id,
                                    "mode": "full_remaining",
                                }
                            ],
                        }
                    ),
                    idempotency_key=f"purchase-return-concurrency-{suffix}-{index}",
                    actor=cast(Principal, SimpleNamespace(user=actor)),
                    client=ClientContext(
                        "127.0.0.1", "test", f"purchase-return-{index}"
                    ),
                )
                return result.status
        except ReturnsConflict:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(return_all, range(2)))

    assert results.count("posted") == 1
    assert results.count("rejected") == 1
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count(InvoiceReturn.id)).where(
                    InvoiceReturn.supplier_invoice_id == invoice_id,
                    InvoiceReturn.status == "posted",
                )
            )
            == 1
        )
