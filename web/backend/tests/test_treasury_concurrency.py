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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.identity.models import User
from app.modules.identity.service import ClientContext, Principal, create_initial_admin
from app.modules.master_data.models import Partner, Warehouse
from app.modules.sales.models import CustomerInvoice, SalesOrder
from app.modules.treasury.models import FinancialAccount, PaymentAllocation, PaymentTransaction
from app.modules.treasury.schemas import InvoiceAllocationRequest, PostPaymentRequest
from app.modules.treasury.service import TreasuryConflict, post_payment


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL payment-allocation row-lock test",
)
def test_five_concurrent_receipts_cannot_allocate_the_same_invoice_twice() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], pool_size=6)
    suffix = uuid4().hex[:10].upper()
    with Session(engine) as db, db.begin():
        actor = db.scalar(select(User).order_by(User.created_at))
        if actor is None:
            actor = create_initial_admin(
                db,
                username=f"treasury-admin-{suffix.lower()}",
                display_name="مدير اختبار الخزانة",
                password=f"Treasury-test-8!{token_urlsafe(18)}",
                client=ClientContext("127.0.0.1", "test", "treasury-concurrency"),
            )
        warehouse = db.scalar(select(Warehouse).where(Warehouse.code == "MAIN"))
        assert warehouse is not None
        customer = Partner(
            code=f"CUS-TR-{suffix}",
            normalized_code=f"CUS-TR-{suffix}",
            name_ar="عميل اختبار تحصيل متزامن",
            phone="",
            address="",
            tax_number="",
            is_customer=True,
            is_supplier=False,
            is_active=True,
            version=1,
        )
        account = FinancialAccount(
            code=f"CASH-{suffix}",
            normalized_code=f"CASH-{suffix}",
            name_ar="خزينة اختبار التزامن",
            account_type="cash",
            opening_balance=0,
            is_default=False,
            is_active=True,
            notes="",
            version=1,
        )
        db.add_all([customer, account])
        db.flush()
        order = SalesOrder(
            order_number=f"SO-TR-{suffix}",
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
            invoice_number=f"SI-TR-{suffix}",
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
            reversal_reason="",
            version=1,
        )
        db.add(invoice)
        db.flush()
        actor_id = actor.id
        customer_id = customer.id
        account_id = account.id
        invoice_id = invoice.id

    barrier = Barrier(5)

    def collect(index: int) -> str:
        try:
            with Session(engine) as db, db.begin():
                actor = db.get(User, actor_id)
                assert actor is not None
                barrier.wait()
                payment = post_payment(
                    db,
                    payload=PostPaymentRequest(
                        transaction_type="customer_receipt",
                        partner_id=customer_id,
                        financial_account_id=account_id,
                        amount=Decimal("100"),
                        payment_method="cash",
                        allocations=[
                            InvoiceAllocationRequest(
                                invoice_id=invoice_id,
                                amount=Decimal("100"),
                            )
                        ],
                    ),
                    idempotency_key=f"treasury-concurrency-{suffix}-{index}",
                    actor=cast(Principal, SimpleNamespace(user=actor)),
                    client=ClientContext("127.0.0.1", "test", f"receipt-{index}"),
                )
                return str(payment.id)
        except (TreasuryConflict, IntegrityError):
            return "rejected"

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(collect, range(5)))

    assert results.count("rejected") == 4
    assert len(set(results) - {"rejected"}) == 1
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count(PaymentTransaction.id)).where(
                    PaymentTransaction.partner_id == customer_id,
                    PaymentTransaction.status == "posted",
                )
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
                    PaymentAllocation.customer_invoice_id == invoice_id
                )
            )
            == Decimal("100.00")
        )
