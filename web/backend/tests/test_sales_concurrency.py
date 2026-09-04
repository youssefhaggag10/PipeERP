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
from app.modules.inventory.models import InventoryBalance
from app.modules.inventory.schemas import ReceiptRequest
from app.modules.inventory.service import post_receipt
from app.modules.master_data.models import Partner, Product, UnitOfMeasure, Warehouse
from app.modules.sales.models import CustomerInvoice, SalesDelivery
from app.modules.sales.schemas import CreatePieceLineRequest, CreatePieceOrderRequest
from app.modules.sales.service import SalesConflict, create_piece_order, deliver_sales_order


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL sales-order row-lock test",
)
def test_five_concurrent_deliveries_post_stock_and_invoice_once() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], pool_size=6)
    suffix = uuid4().hex[:10].upper()
    with Session(engine) as db, db.begin():
        actor = db.scalar(select(User).order_by(User.created_at))
        if actor is None:
            actor = create_initial_admin(
                db,
                username=f"sales-admin-{suffix.lower()}",
                display_name="مدير اختبار المبيعات",
                password=f"Sales-test-7!{token_urlsafe(18)}",
                client=ClientContext("127.0.0.1", "test", "sales-concurrency"),
            )
        unit = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "KG"))
        warehouse = db.scalar(select(Warehouse).where(Warehouse.code == "MAIN"))
        assert unit is not None and warehouse is not None
        customer = Partner(
            code=f"CUS-{suffix}",
            normalized_code=f"CUS-{suffix}",
            name_ar="عميل اختبار تسليم متزامن",
            phone="",
            address="",
            tax_number="",
            is_customer=True,
            is_supplier=False,
            is_active=True,
            version=1,
        )
        product = Product(
            code=f"SALE-{suffix}",
            normalized_code=f"SALE-{suffix}",
            name_ar="منتج اختبار تسليم متزامن",
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
        db.add_all([customer, product])
        db.flush()
        actor_id = actor.id
        warehouse_id = warehouse.id
        product_id = product.id
        post_receipt(
            db,
            payload=ReceiptRequest(
                product_id=product.id,
                warehouse_id=warehouse.id,
                quantity=Decimal("10"),
                weight_kg=Decimal("100"),
                cost_basis="quantity",
                unit_cost=Decimal("40"),
                lot_number=f"LOT-{suffix}",
                reference_type="sales_concurrency_test",
            ),
            idempotency_key=f"sales-stock-{suffix}",
            actor_user_id=actor.id,
            client=ClientContext("127.0.0.1", "test", "sales-concurrency"),
        )
        order = create_piece_order(
            db,
            payload=CreatePieceOrderRequest(
                customer_id=customer.id,
                warehouse_id=warehouse.id,
                lines=[
                    CreatePieceLineRequest(
                        product_id=product.id,
                        quantity=Decimal("6"),
                        unit_price=Decimal("100"),
                    )
                ],
            ),
            actor=cast(Principal, SimpleNamespace(user=actor)),
            client=ClientContext("127.0.0.1", "test", "sales-concurrency"),
        )
        order_id = order.id
        version = order.version

    barrier = Barrier(5)

    def deliver(index: int) -> str:
        try:
            with Session(engine) as db, db.begin():
                actor = db.get(User, actor_id)
                assert actor is not None
                barrier.wait()
                delivered = deliver_sales_order(
                    db,
                    order_id=order_id,
                    version=version,
                    idempotency_key=f"sales-concurrency-{suffix}-{index}",
                    actor=cast(Principal, SimpleNamespace(user=actor)),
                    client=ClientContext("127.0.0.1", "test", f"delivery-{index}"),
                )
                assert delivered.delivery is not None
                return str(delivered.delivery.id)
        except SalesConflict:
            return "rejected"

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(deliver, range(5)))

    assert results.count("rejected") == 4
    assert len(set(results) - {"rejected"}) == 1
    with Session(engine) as db:
        balance = db.get(InventoryBalance, (product_id, warehouse_id))
        assert balance is not None
        assert balance.quantity_on_hand == Decimal("4.000000")
        assert balance.weight_on_hand_kg == Decimal("40.000000")
        assert (
            db.scalar(
                select(func.count(SalesDelivery.id)).where(SalesDelivery.sales_order_id == order_id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count(CustomerInvoice.id)).where(
                    CustomerInvoice.sales_order_id == order_id
                )
            )
            == 1
        )
