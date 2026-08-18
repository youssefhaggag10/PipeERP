import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
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
from app.modules.master_data.models import Partner, Product, UnitOfMeasure, Warehouse
from app.modules.purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseReceipt
from app.modules.purchasing.schemas import (
    PostPurchaseReceiptRequest,
    PurchaseReceiptLineRequest,
)
from app.modules.purchasing.service import PurchasingConflict, post_purchase_receipt


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL purchase-order row-lock test",
)
def test_five_concurrent_receipts_cannot_over_receive_purchase_order() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], pool_size=6)
    suffix = uuid4().hex[:10].upper()
    with Session(engine) as db, db.begin():
        actor = db.scalar(select(User).order_by(User.created_at))
        if actor is None:
            actor = create_initial_admin(
                db,
                username=f"purchase-admin-{suffix.lower()}",
                display_name="مدير اختبار المشتريات",
                password="Purchase-admin-password-2026",
                client=ClientContext("127.0.0.1", "test", "purchase-concurrency"),
            )
        unit = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "KG"))
        warehouse = db.scalar(select(Warehouse).where(Warehouse.code == "MAIN"))
        assert unit is not None and warehouse is not None
        supplier = Partner(
            code=f"SUP-{suffix}",
            normalized_code=f"SUP-{suffix}",
            name_ar="مورد اختبار التزامن",
            phone="",
            address="",
            tax_number="",
            is_customer=False,
            is_supplier=True,
            is_active=True,
            version=1,
        )
        product = Product(
            code=f"PUR-{suffix}",
            normalized_code=f"PUR-{suffix}",
            name_ar="خامة اختبار استلام متزامن",
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
            order_number=f"PO-CON-{suffix}",
            supplier_id=supplier.id,
            warehouse_id=warehouse.id,
            status="approved",
            notes="",
            total=Decimal("100.00"),
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
            ordered_weight_kg=Decimal("0"),
            unit_price=Decimal("10"),
            additional_unit_cost=Decimal("0"),
            line_total=Decimal("100"),
            received_quantity=Decimal("0"),
            received_weight_kg=Decimal("0"),
            version=1,
        )
        db.add(line)
        db.flush()
        actor_id = actor.id
        order_id = order.id
        line_id = line.id
        product_id = product.id
        warehouse_id = warehouse.id

    barrier = Barrier(5)

    def receive(index: int) -> str:
        try:
            with Session(engine) as db, db.begin():
                actor = db.get(User, actor_id)
                assert actor is not None
                barrier.wait()
                receipt = post_purchase_receipt(
                    db,
                    order_id=order_id,
                    payload=PostPurchaseReceiptRequest(
                        lines=[
                            PurchaseReceiptLineRequest(
                                purchase_order_line_id=line_id,
                                gross_quantity=Decimal("3"),
                                lot_number=f"LOT-{suffix}-{index}",
                            )
                        ]
                    ),
                    idempotency_key=f"purchase-concurrency-{suffix}-{index}",
                    actor=cast(Principal, SimpleNamespace(user=actor)),
                    client=ClientContext("127.0.0.1", "test", f"receipt-{index}"),
                )
                return str(receipt.id)
        except (PurchasingConflict, ValueError):
            return "rejected"

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(receive, range(5)))

    assert results.count("rejected") == 2
    assert len(set(results) - {"rejected"}) == 3
    with Session(engine) as db:
        stored_line = db.get(PurchaseOrderLine, line_id)
        balance = db.get(InventoryBalance, (product_id, warehouse_id))
        assert stored_line is not None and stored_line.received_quantity == Decimal("9.000000")
        assert balance is not None and balance.quantity_on_hand == Decimal("9.000000")
        assert (
            db.scalar(
                select(func.count(PurchaseReceipt.id)).where(
                    PurchaseReceipt.purchase_order_id == order_id
                )
            )
            == 3
        )
