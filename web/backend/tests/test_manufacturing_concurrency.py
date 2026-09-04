import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
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
from app.modules.inventory.models import InventoryBalance, InventoryLayer
from app.modules.manufacturing.models import (
    ManufacturingMaterialIssue,
    ManufacturingOrder,
    ManufacturingOrderMaterial,
    ManufacturingOrderOutput,
    ManufacturingRecipe,
    ManufacturingRecipeComponent,
    ManufacturingRecipeOutput,
)
from app.modules.manufacturing.schemas import TransitionRequest
from app.modules.manufacturing.service import ManufacturingConflict, start_order
from app.modules.master_data.models import Product, UnitOfMeasure, Warehouse


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="PostgreSQL manufacturing-order row-lock test",
)
def test_five_concurrent_starts_issue_the_same_plan_only_once() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], pool_size=6)
    suffix = uuid4().hex[:10].upper()
    with Session(engine) as db, db.begin():
        actor = db.scalar(select(User).order_by(User.created_at))
        if actor is None:
            actor = create_initial_admin(
                db,
                username=f"manufacturing-admin-{suffix.lower()}",
                display_name="مدير اختبار التصنيع",
                password="Manufacturing-admin-password-2026",
                client=ClientContext("127.0.0.1", "test", "manufacturing-concurrency"),
            )
        unit = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "KG"))
        warehouse = db.scalar(select(Warehouse).where(Warehouse.code == "MAIN"))
        assert unit is not None and warehouse is not None
        raw = Product(
            code=f"MFG-RAW-{suffix}",
            normalized_code=f"MFG-RAW-{suffix}",
            name_ar="خامة اختبار بدء متزامن",
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
            code=f"MFG-FG-{suffix}",
            normalized_code=f"MFG-FG-{suffix}",
            name_ar="منتج اختبار بدء متزامن",
            product_type="finished_good",
            unit_id=unit.id,
            category_id=None,
            min_stock=0,
            track_lots=True,
            standard_weight_kg=Decimal("1"),
            weight_tolerance_percent=5,
            is_active=True,
            version=1,
        )
        scrap = Product(
            code=f"MFG-SCRAP-{suffix}",
            normalized_code=f"MFG-SCRAP-{suffix}",
            name_ar="كسر اختبار بدء متزامن",
            product_type="waste",
            unit_id=unit.id,
            category_id=None,
            min_stock=0,
            track_lots=True,
            standard_weight_kg=0,
            weight_tolerance_percent=5,
            is_active=True,
            version=1,
        )
        db.add_all([raw, output, scrap])
        db.flush()
        recipe = ManufacturingRecipe(
            code=f"MFG-RCP-{suffix}",
            normalized_code=f"MFG-RCP-{suffix}",
            name_ar=f"خلطة تزامن {suffix}",
            normalized_name=f"خلطة تزامن {suffix}".casefold(),
            scrap_product_id=scrap.id,
            suggested_scrap_per_batch=0,
            notes="",
            is_active=True,
            version=1,
            created_by_id=actor.id,
        )
        db.add(recipe)
        db.flush()
        db.add_all(
            [
                ManufacturingRecipeOutput(recipe_id=recipe.id, product_id=output.id),
                ManufacturingRecipeComponent(
                    recipe_id=recipe.id,
                    product_id=raw.id,
                    quantity_per_batch=Decimal("10"),
                    display_order=1,
                ),
            ]
        )
        order = ManufacturingOrder(
            order_number=f"MO-CON-{suffix}",
            recipe_id=recipe.id,
            warehouse_id=warehouse.id,
            status="draft",
            order_date=datetime.now(UTC),
            planned_batches=1,
            issued_batches=0,
            actual_batches=0,
            target_weight_kg=Decimal("10"),
            planned_input_weight_kg=Decimal("10"),
            returned_scrap_quantity=0,
            material_cost=0,
            finished_cost=0,
            weight_variance_kg=0,
            notes="",
            create_idempotency_key=f"mfg-create-{suffix}",
            create_request_hash="0" * 64,
            created_by_id=actor.id,
            version=1,
        )
        db.add(order)
        db.flush()
        material = ManufacturingOrderMaterial(
            manufacturing_order_id=order.id,
            product_id=raw.id,
            component_kind="material",
            quantity_per_batch=Decimal("10"),
            planned_quantity=Decimal("10"),
            issued_quantity=0,
            used_quantity=0,
            returned_quantity=0,
            issued_cost=0,
            used_cost=0,
        )
        db.add_all(
            [
                material,
                ManufacturingOrderOutput(
                    manufacturing_order_id=order.id,
                    product_id=output.id,
                    planned_quantity=Decimal("10"),
                    standard_weight_kg=Decimal("1"),
                    good_quantity=0,
                    defective_quantity=0,
                    actual_weight_kg=0,
                    unit_cost=0,
                    line_cost=0,
                ),
                InventoryBalance(
                    product_id=raw.id,
                    warehouse_id=warehouse.id,
                    quantity_on_hand=Decimal("100"),
                    weight_on_hand_kg=0,
                    version=1,
                ),
                InventoryLayer(
                    product_id=raw.id,
                    warehouse_id=warehouse.id,
                    lot_id=None,
                    source_type="opening",
                    source_id=None,
                    source_line_id=None,
                    cost_basis="quantity",
                    quantity_received=Decimal("100"),
                    quantity_remaining=Decimal("100"),
                    weight_received_kg=0,
                    weight_remaining_kg=0,
                    unit_cost=Decimal("2"),
                    received_at=datetime.now(UTC),
                    version=1,
                ),
            ]
        )
        db.flush()
        actor_id = actor.id
        order_id = order.id
        material_id = material.id
        raw_id = raw.id
        warehouse_id = warehouse.id

    barrier = Barrier(5)

    def begin(index: int) -> str:
        try:
            with Session(engine) as db, db.begin():
                actor = db.get(User, actor_id)
                assert actor is not None
                barrier.wait()
                result = start_order(
                    db,
                    order_id=order_id,
                    payload=TransitionRequest(version=1),
                    idempotency_key=f"manufacturing-concurrency-{suffix}-{index}",
                    actor=cast(Principal, SimpleNamespace(user=actor)),
                    client=ClientContext("127.0.0.1", "test", f"start-{index}"),
                )
                return result.status
        except ManufacturingConflict:
            return "rejected"

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(begin, range(5)))

    assert results.count("in_progress") == 1
    assert results.count("rejected") == 4
    with Session(engine) as db:
        stored_order = db.get(ManufacturingOrder, order_id)
        balance = db.get(InventoryBalance, (raw_id, warehouse_id))
        assert stored_order is not None and stored_order.issued_batches == 1
        assert balance is not None and balance.quantity_on_hand == Decimal("90.000000")
        assert (
            db.scalar(
                select(func.count(ManufacturingMaterialIssue.id)).where(
                    ManufacturingMaterialIssue.order_material_id == material_id
                )
            )
            == 1
        )
