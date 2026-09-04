import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.modules.identity.models import User
from app.modules.identity.service import ClientContext, create_initial_admin
from app.modules.inventory.models import InventoryBalance, InventoryTransaction
from app.modules.inventory.schemas import IssueRequest, ReceiptRequest
from app.modules.inventory.service import InsufficientStock, post_issue, post_receipt
from app.modules.master_data.models import Product, UnitOfMeasure, Warehouse


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL row-lock test",
)
def test_five_concurrent_issues_cannot_double_allocate_or_go_negative() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], pool_size=6)
    suffix = uuid4().hex[:10].upper()
    with Session(engine) as db, db.begin():
        actor = db.scalar(select(User).order_by(User.created_at))
        if actor is None:
            actor = create_initial_admin(
                db,
                username=f"inventory-admin-{suffix.lower()}",
                display_name="مدير اختبار المخزون",
                password="Inventory-admin-password-2026",
                client=ClientContext("127.0.0.1", "test", "inventory-concurrency"),
            )
        unit = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "KG"))
        warehouse = db.scalar(select(Warehouse).where(Warehouse.code == "MAIN"))
        assert unit is not None and warehouse is not None
        product = Product(
            code=f"FIFO-{suffix}",
            normalized_code=f"FIFO-{suffix}",
            name_ar="خامة اختبار التزامن",
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
        db.add(product)
        db.flush()
        actor_id = actor.id
        product_id = product.id
        warehouse_id = warehouse.id
        post_receipt(
            db,
            payload=ReceiptRequest(
                product_id=product_id,
                warehouse_id=warehouse_id,
                quantity=Decimal("5"),
                weight_kg=Decimal("0"),
                cost_basis="quantity",
                unit_cost=Decimal("3"),
                lot_number=f"LOT-{suffix}",
                reference_type="concurrency_test",
            ),
            idempotency_key=f"concurrency-receipt-{suffix}",
            actor_user_id=actor_id,
            client=ClientContext("127.0.0.1", "test", "inventory-concurrency"),
        )

    barrier = Barrier(5)

    def issue(index: int) -> str:
        with Session(engine) as db, db.begin():
            barrier.wait()
            transaction = post_issue(
                db,
                payload=IssueRequest(
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    amount=Decimal("1"),
                    cost_basis="quantity",
                    reference_type="concurrency_test",
                    reference_id=str(index),
                ),
                idempotency_key=f"concurrency-issue-{suffix}-{index}",
                actor_user_id=actor_id,
                client=ClientContext("127.0.0.1", "test", f"issue-{index}"),
            )
            return str(transaction.id)

    with ThreadPoolExecutor(max_workers=5) as executor:
        transaction_ids = list(executor.map(issue, range(5)))

    assert len(set(transaction_ids)) == 5
    with Session(engine) as db:
        balance = db.get(InventoryBalance, (product_id, warehouse_id))
        assert balance is not None
        assert balance.quantity_on_hand == 0
        issue_count = db.scalar(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.product_id == product_id,
                InventoryTransaction.transaction_type == "issue",
            )
        )
        assert issue_count == 5

    with pytest.raises(InsufficientStock), Session(engine) as db, db.begin():
        post_issue(
            db,
            payload=IssueRequest(
                product_id=product_id,
                warehouse_id=warehouse_id,
                amount=Decimal("1"),
                cost_basis="quantity",
                reference_type="concurrency_test",
            ),
            idempotency_key=f"concurrency-overdraw-{suffix}",
            actor_user_id=actor_id,
            client=ClientContext("127.0.0.1", "test", "overdraw"),
        )
