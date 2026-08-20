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
from app.modules.master_data.models import Partner, Warehouse
from app.modules.returns.models import InvoiceReturn, ReturnRefund
from app.modules.returns.schemas import CreateRefundRequest
from app.modules.returns.service import ReturnsConflict, create_refund
from app.modules.sales.models import CustomerInvoice, SalesOrder
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
