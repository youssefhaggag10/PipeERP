import unicodedata
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.common.decimal import quantity
from app.domain.inventory.fifo import FifoLayer, allocate_fifo
from app.modules.identity.service import ClientContext, add_audit
from app.modules.inventory.models import (
    InventoryAllocation,
    InventoryBalance,
    InventoryLayer,
    InventoryLot,
    InventoryTransaction,
)
from app.modules.inventory.schemas import (
    AdjustmentRequest,
    BalanceView,
    CostBasis,
    InventoryOption,
    InventoryOptionsView,
    IssueRequest,
    ReceiptRequest,
    ReversalRequest,
    TransactionView,
    TransferRequest,
)
from app.modules.master_data.models import Product, Warehouse


class InventoryError(Exception):
    pass


class InventoryNotFound(InventoryError):
    pass


class InsufficientStock(InventoryError):
    pass


class InventoryConflict(InventoryError):
    pass


def _existing_transaction(db: Session, idempotency_key: str) -> InventoryTransaction | None:
    return db.scalar(
        select(InventoryTransaction).where(InventoryTransaction.idempotency_key == idempotency_key)
    )


def _validate_idempotent_request(
    transaction: InventoryTransaction,
    *,
    transaction_type: str,
    product_id: UUID,
    warehouse_id: UUID,
) -> InventoryTransaction:
    if (
        transaction.transaction_type != transaction_type
        or transaction.product_id != product_id
        or transaction.warehouse_id != warehouse_id
    ):
        raise InventoryConflict("مفتاح منع التكرار مستخدم بالفعل لطلب مختلف")
    return transaction


def _lock_context(db: Session, product_id: UUID, warehouse_id: UUID) -> None:
    product = db.scalar(select(Product).where(Product.id == product_id).with_for_update())
    if product is None or not product.is_active:
        raise InventoryNotFound("المنتج غير موجود أو غير نشط")
    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None or not warehouse.is_active:
        raise InventoryNotFound("المخزن غير موجود أو غير نشط")


def _locked_balance(db: Session, product_id: UUID, warehouse_id: UUID) -> InventoryBalance:
    balance = db.scalar(
        select(InventoryBalance)
        .where(
            InventoryBalance.product_id == product_id,
            InventoryBalance.warehouse_id == warehouse_id,
        )
        .with_for_update()
    )
    if balance is None:
        balance = InventoryBalance(
            product_id=product_id,
            warehouse_id=warehouse_id,
            quantity_on_hand=Decimal("0"),
            weight_on_hand_kg=Decimal("0"),
            version=1,
        )
        db.add(balance)
        db.flush()
    return balance


def _unit_cost_for_basis(layer: InventoryLayer, requested_basis: str) -> Decimal:
    if layer.cost_basis == requested_basis:
        return layer.unit_cost
    source_remaining = (
        layer.weight_remaining_kg if layer.cost_basis == "weight" else layer.quantity_remaining
    )
    requested_remaining = (
        layer.quantity_remaining if requested_basis == "quantity" else layer.weight_remaining_kg
    )
    if source_remaining <= 0 or requested_remaining <= 0:
        return Decimal("0")
    return quantity(layer.unit_cost * source_remaining / requested_remaining)


def _get_or_create_lot(
    db: Session,
    *,
    product_id: UUID,
    warehouse_id: UUID,
    lot_number: str,
) -> InventoryLot | None:
    normalized = unicodedata.normalize("NFKC", lot_number).strip().upper()
    if not normalized:
        return None
    lot = db.scalar(
        select(InventoryLot).where(
            InventoryLot.product_id == product_id,
            InventoryLot.warehouse_id == warehouse_id,
            InventoryLot.normalized_lot_number == normalized,
        )
    )
    if lot is None:
        lot = InventoryLot(
            product_id=product_id,
            warehouse_id=warehouse_id,
            lot_number=lot_number.strip(),
            normalized_lot_number=normalized,
        )
        db.add(lot)
        db.flush()
    return lot


def post_receipt(
    db: Session,
    *,
    payload: ReceiptRequest,
    idempotency_key: str,
    actor_user_id: UUID,
    client: ClientContext,
    transaction_type: str = "receipt",
    reversal_of_id: UUID | None = None,
) -> InventoryTransaction:
    if transaction_type not in {
        "receipt",
        "transfer_in",
        "adjustment_in",
        "return_in",
        "production_output",
        "reversal_in",
    }:
        raise ValueError("نوع حركة الإدخال غير صالح")
    existing = _existing_transaction(db, idempotency_key)
    if existing is not None:
        return _validate_idempotent_request(
            existing,
            transaction_type=transaction_type,
            product_id=payload.product_id,
            warehouse_id=payload.warehouse_id,
        )
    _lock_context(db, payload.product_id, payload.warehouse_id)
    existing = _existing_transaction(db, idempotency_key)
    if existing is not None:
        return _validate_idempotent_request(
            existing,
            transaction_type=transaction_type,
            product_id=payload.product_id,
            warehouse_id=payload.warehouse_id,
        )

    lot = _get_or_create_lot(
        db,
        product_id=payload.product_id,
        warehouse_id=payload.warehouse_id,
        lot_number=payload.lot_number,
    )
    received_quantity = quantity(payload.quantity)
    received_weight = quantity(payload.weight_kg)
    basis_amount = received_quantity if payload.cost_basis == "quantity" else received_weight
    total_cost = quantity(basis_amount * payload.unit_cost)
    transaction = InventoryTransaction(
        idempotency_key=idempotency_key,
        transaction_type=transaction_type,
        product_id=payload.product_id,
        warehouse_id=payload.warehouse_id,
        lot_id=lot.id if lot else None,
        quantity_delta=received_quantity,
        weight_delta_kg=received_weight,
        unit_cost=payload.unit_cost,
        total_cost=total_cost,
        cost_basis=payload.cost_basis,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        reference_line_id=payload.reference_line_id,
        reversal_of_id=reversal_of_id,
        notes=payload.notes.strip(),
        posted_by_id=actor_user_id,
    )
    db.add(transaction)
    db.flush()
    db.add(
        InventoryLayer(
            product_id=payload.product_id,
            warehouse_id=payload.warehouse_id,
            lot_id=lot.id if lot else None,
            source_type=payload.reference_type,
            source_id=payload.reference_id,
            source_line_id=payload.reference_line_id,
            cost_basis=payload.cost_basis,
            quantity_received=received_quantity,
            quantity_remaining=received_quantity,
            weight_received_kg=received_weight,
            weight_remaining_kg=received_weight,
            unit_cost=payload.unit_cost,
            received_at=datetime.now(UTC),
            version=1,
        )
    )
    balance = _locked_balance(db, payload.product_id, payload.warehouse_id)
    balance.quantity_on_hand = quantity(balance.quantity_on_hand + received_quantity)
    balance.weight_on_hand_kg = quantity(balance.weight_on_hand_kg + received_weight)
    balance.version += 1
    add_audit(
        db,
        actor_user_id=actor_user_id,
        event_type=f"inventory.{transaction_type}.post",
        entity_type="inventory_transaction",
        entity_id=str(transaction.id),
        outcome="success",
        client=client,
        after_state={
            "product_id": str(payload.product_id),
            "warehouse_id": str(payload.warehouse_id),
            "quantity": str(received_quantity),
            "weight_kg": str(received_weight),
        },
    )
    db.flush()
    return transaction


def post_issue(
    db: Session,
    *,
    payload: IssueRequest,
    idempotency_key: str,
    actor_user_id: UUID,
    client: ClientContext,
    transaction_type: str = "issue",
    reversal_of_id: UUID | None = None,
) -> InventoryTransaction:
    if transaction_type not in {
        "issue",
        "transfer_out",
        "adjustment_out",
        "return_out",
        "production_issue",
        "reversal_out",
    }:
        raise ValueError("نوع حركة الإخراج غير صالح")
    existing = _existing_transaction(db, idempotency_key)
    if existing is not None:
        return _validate_idempotent_request(
            existing,
            transaction_type=transaction_type,
            product_id=payload.product_id,
            warehouse_id=payload.warehouse_id,
        )
    _lock_context(db, payload.product_id, payload.warehouse_id)
    existing = _existing_transaction(db, idempotency_key)
    if existing is not None:
        return _validate_idempotent_request(
            existing,
            transaction_type=transaction_type,
            product_id=payload.product_id,
            warehouse_id=payload.warehouse_id,
        )
    balance = _locked_balance(db, payload.product_id, payload.warehouse_id)
    layers = list(
        db.scalars(
            select(InventoryLayer)
            .where(
                InventoryLayer.product_id == payload.product_id,
                InventoryLayer.warehouse_id == payload.warehouse_id,
            )
            .order_by(InventoryLayer.received_at, InventoryLayer.id)
            .with_for_update()
        )
    )
    try:
        allocations = allocate_fifo(
            layers=[
                FifoLayer(
                    layer_id=str(layer.id),
                    received_at=layer.received_at,
                    sequence=index,
                    quantity_remaining=layer.quantity_remaining,
                    weight_remaining_kg=layer.weight_remaining_kg,
                    unit_cost=_unit_cost_for_basis(layer, payload.cost_basis),
                )
                for index, layer in enumerate(layers)
            ],
            amount=payload.amount,
            cost_basis=payload.cost_basis,
        )
    except ValueError as exc:
        raise InsufficientStock(str(exc)) from exc

    layer_by_id = {str(layer.id): layer for layer in layers}
    issued_quantity = sum((item.quantity for item in allocations), Decimal("0"))
    issued_weight = sum((item.weight_kg for item in allocations), Decimal("0"))
    total_cost = sum((item.total_cost for item in allocations), Decimal("0"))
    average_cost = quantity(total_cost / payload.amount)
    transaction = InventoryTransaction(
        idempotency_key=idempotency_key,
        transaction_type=transaction_type,
        product_id=payload.product_id,
        warehouse_id=payload.warehouse_id,
        lot_id=None,
        quantity_delta=-issued_quantity,
        weight_delta_kg=-issued_weight,
        unit_cost=average_cost,
        total_cost=total_cost,
        cost_basis=payload.cost_basis,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        reference_line_id=payload.reference_line_id,
        reversal_of_id=reversal_of_id,
        notes=payload.notes.strip(),
        posted_by_id=actor_user_id,
    )
    db.add(transaction)
    db.flush()
    for item in allocations:
        layer = layer_by_id[item.layer_id]
        layer.quantity_remaining = quantity(layer.quantity_remaining - item.quantity)
        layer.weight_remaining_kg = quantity(layer.weight_remaining_kg - item.weight_kg)
        layer.version += 1
        db.add(
            InventoryAllocation(
                outbound_transaction_id=transaction.id,
                source_layer_id=layer.id,
                quantity=item.quantity,
                weight_kg=item.weight_kg,
                unit_cost=item.unit_cost,
                total_cost=item.total_cost,
            )
        )
    balance.quantity_on_hand = quantity(balance.quantity_on_hand - issued_quantity)
    balance.weight_on_hand_kg = quantity(balance.weight_on_hand_kg - issued_weight)
    if balance.quantity_on_hand < 0 or balance.weight_on_hand_kg < 0:
        raise InsufficientStock("لا يمكن أن ينتج عن الحركة رصيد سالب")
    balance.version += 1
    add_audit(
        db,
        actor_user_id=actor_user_id,
        event_type=f"inventory.{transaction_type}.post",
        entity_type="inventory_transaction",
        entity_id=str(transaction.id),
        outcome="success",
        client=client,
        after_state={
            "product_id": str(payload.product_id),
            "warehouse_id": str(payload.warehouse_id),
            "quantity": str(issued_quantity),
            "weight_kg": str(issued_weight),
            "total_cost": str(total_cost),
        },
    )
    db.flush()
    return transaction


def post_exact_paired_issue(
    db: Session,
    *,
    product_id: UUID,
    warehouse_id: UUID,
    requested_quantity: Decimal,
    requested_weight_kg: Decimal,
    idempotency_key: str,
    reference_type: str,
    reference_id: str,
    reference_line_id: str,
    notes: str,
    actor_user_id: UUID,
    client: ClientContext,
) -> InventoryTransaction:
    """Issue an exact piece count and exact commercial weight from FIFO layers.

    Finished pipe is counted in pieces but sold using the actual scale weight.
    The normal one-dimensional FIFO helper deliberately derives the paired
    dimension proportionally; weight-card delivery instead has two authoritative
    dimensions, so both are locked, validated and depleted together here.
    """
    requested_quantity = quantity(requested_quantity)
    requested_weight_kg = quantity(requested_weight_kg)
    if requested_quantity <= 0 or requested_weight_kg <= 0:
        raise ValueError("عدد المواسير والوزن الفعلي يجب أن يكونا أكبر من صفر")
    existing = _existing_transaction(db, idempotency_key)
    if existing is not None:
        return _validate_idempotent_request(
            existing,
            transaction_type="issue",
            product_id=product_id,
            warehouse_id=warehouse_id,
        )
    _lock_context(db, product_id, warehouse_id)
    balance = _locked_balance(db, product_id, warehouse_id)
    layers = list(
        db.scalars(
            select(InventoryLayer)
            .where(
                InventoryLayer.product_id == product_id,
                InventoryLayer.warehouse_id == warehouse_id,
                InventoryLayer.quantity_remaining > 0,
                InventoryLayer.weight_remaining_kg > 0,
            )
            .order_by(InventoryLayer.received_at, InventoryLayer.id)
            .with_for_update()
        )
    )
    available_quantity = sum((layer.quantity_remaining for layer in layers), Decimal("0"))
    available_weight = sum((layer.weight_remaining_kg for layer in layers), Decimal("0"))
    if available_quantity < requested_quantity:
        raise InsufficientStock(
            f"عدد المواسير غير كافٍ. المتاح {available_quantity} والمطلوب {requested_quantity}"
        )
    if available_weight < requested_weight_kg:
        raise InsufficientStock(
            f"الوزن المخزني غير كافٍ. المتاح {available_weight} والمطلوب {requested_weight_kg}"
        )

    average_sale_weight = requested_weight_kg / requested_quantity
    remaining_quantity = requested_quantity
    remaining_weight = requested_weight_kg
    prepared: list[tuple[InventoryLayer, Decimal, Decimal, Decimal]] = []
    total_cost = Decimal("0")
    for layer in layers:
        if remaining_quantity == 0:
            break
        max_quantity_by_weight = quantity(layer.weight_remaining_kg / average_sale_weight)
        take_quantity = min(
            remaining_quantity,
            layer.quantity_remaining,
            max_quantity_by_weight,
        )
        if take_quantity <= 0:
            continue
        take_weight = (
            remaining_weight
            if take_quantity == remaining_quantity
            else quantity(take_quantity * average_sale_weight)
        )
        if take_weight > layer.weight_remaining_kg:
            take_weight = layer.weight_remaining_kg
            take_quantity = quantity(take_weight / average_sale_weight)
        allocation_cost = quantity(
            take_weight * layer.unit_cost
            if layer.cost_basis == "weight"
            else take_quantity * layer.unit_cost
        )
        prepared.append((layer, take_quantity, take_weight, allocation_cost))
        total_cost += allocation_cost
        remaining_quantity = quantity(remaining_quantity - take_quantity)
        remaining_weight = quantity(remaining_weight - take_weight)
    if remaining_quantity != 0 or remaining_weight != 0:
        raise InsufficientStock(
            "الرصيد الإجمالي موجود لكن نسب العدد والوزن داخل طبقات FIFO لا تكفي كارتة الوزن"
        )

    average_cost = quantity(total_cost / requested_weight_kg)
    transaction = InventoryTransaction(
        idempotency_key=idempotency_key,
        transaction_type="issue",
        product_id=product_id,
        warehouse_id=warehouse_id,
        lot_id=None,
        quantity_delta=-requested_quantity,
        weight_delta_kg=-requested_weight_kg,
        unit_cost=average_cost,
        total_cost=quantity(total_cost),
        cost_basis="weight",
        reference_type=reference_type,
        reference_id=reference_id,
        reference_line_id=reference_line_id,
        reversal_of_id=None,
        notes=notes.strip(),
        posted_by_id=actor_user_id,
    )
    db.add(transaction)
    db.flush()
    for layer, take_quantity, take_weight, allocation_cost in prepared:
        layer.quantity_remaining = quantity(layer.quantity_remaining - take_quantity)
        layer.weight_remaining_kg = quantity(layer.weight_remaining_kg - take_weight)
        layer.version += 1
        allocation_unit_cost = quantity(allocation_cost / take_weight)
        db.add(
            InventoryAllocation(
                outbound_transaction_id=transaction.id,
                source_layer_id=layer.id,
                quantity=take_quantity,
                weight_kg=take_weight,
                unit_cost=allocation_unit_cost,
                total_cost=allocation_cost,
            )
        )
    balance.quantity_on_hand = quantity(balance.quantity_on_hand - requested_quantity)
    balance.weight_on_hand_kg = quantity(balance.weight_on_hand_kg - requested_weight_kg)
    if balance.quantity_on_hand < 0 or balance.weight_on_hand_kg < 0:
        raise InsufficientStock("لا يمكن أن ينتج عن تسليم كارتة الوزن رصيد سالب")
    balance.version += 1
    add_audit(
        db,
        actor_user_id=actor_user_id,
        event_type="inventory.weight_sale.issue",
        entity_type="inventory_transaction",
        entity_id=str(transaction.id),
        outcome="success",
        client=client,
        after_state={
            "product_id": str(product_id),
            "quantity": str(requested_quantity),
            "weight_kg": str(requested_weight_kg),
            "total_cost": str(total_cost),
        },
    )
    db.flush()
    return transaction


def post_transfer(
    db: Session,
    *,
    payload: TransferRequest,
    idempotency_key: str,
    actor_user_id: UUID,
    client: ClientContext,
) -> tuple[str, InventoryTransaction, InventoryTransaction]:
    digest = sha256(idempotency_key.encode("utf-8")).hexdigest()
    reference_id = payload.reference_id or digest[:32]
    outbound = post_issue(
        db,
        payload=IssueRequest(
            product_id=payload.product_id,
            warehouse_id=payload.source_warehouse_id,
            amount=payload.amount,
            cost_basis=payload.cost_basis,
            reference_type="inventory_transfer",
            reference_id=reference_id,
            notes=payload.notes,
        ),
        idempotency_key=f"transfer-out-{digest}",
        actor_user_id=actor_user_id,
        client=client,
        transaction_type="transfer_out",
    )
    inbound = post_receipt(
        db,
        payload=ReceiptRequest(
            product_id=payload.product_id,
            warehouse_id=payload.destination_warehouse_id,
            quantity=-outbound.quantity_delta,
            weight_kg=-outbound.weight_delta_kg,
            cost_basis=payload.cost_basis,
            unit_cost=outbound.unit_cost,
            reference_type="inventory_transfer",
            reference_id=reference_id,
            notes=payload.notes,
        ),
        idempotency_key=f"transfer-in-{digest}",
        actor_user_id=actor_user_id,
        client=client,
        transaction_type="transfer_in",
    )
    return reference_id, outbound, inbound


def post_adjustment(
    db: Session,
    *,
    payload: AdjustmentRequest,
    idempotency_key: str,
    actor_user_id: UUID,
    client: ClientContext,
) -> InventoryTransaction:
    if payload.direction == "increase":
        return post_receipt(
            db,
            payload=ReceiptRequest(
                product_id=payload.product_id,
                warehouse_id=payload.warehouse_id,
                quantity=payload.quantity,
                weight_kg=payload.weight_kg,
                cost_basis=payload.cost_basis,
                unit_cost=payload.unit_cost,
                reference_type="stock_adjustment",
                notes=payload.reason,
            ),
            idempotency_key=idempotency_key,
            actor_user_id=actor_user_id,
            client=client,
            transaction_type="adjustment_in",
        )
    amount = payload.quantity if payload.cost_basis == "quantity" else payload.weight_kg
    return post_issue(
        db,
        payload=IssueRequest(
            product_id=payload.product_id,
            warehouse_id=payload.warehouse_id,
            amount=amount,
            cost_basis=payload.cost_basis,
            reference_type="stock_adjustment",
            notes=payload.reason,
        ),
        idempotency_key=idempotency_key,
        actor_user_id=actor_user_id,
        client=client,
        transaction_type="adjustment_out",
    )


def reverse_purchase_receipt_inventory(
    db: Session,
    *,
    transaction_id: UUID,
    purchase_receipt_id: UUID,
    purchase_order_line_id: UUID,
    idempotency_key: str,
    actor_user_id: UUID,
    client: ClientContext,
    reason: str,
) -> InventoryTransaction:
    original = db.scalar(
        select(InventoryTransaction)
        .where(InventoryTransaction.id == transaction_id)
        .with_for_update()
    )
    if original is None:
        raise InventoryNotFound("حركة استلام المشتريات غير موجودة")
    if (
        original.transaction_type != "receipt"
        or original.reference_type != "purchase_receipt"
        or original.reference_id != str(purchase_receipt_id)
        or original.reference_line_id != str(purchase_order_line_id)
    ):
        raise InventoryConflict("حركة المخزون لا تطابق سند استلام المشتريات")
    previous_reversal = db.scalar(
        select(InventoryTransaction).where(InventoryTransaction.reversal_of_id == original.id)
    )
    if previous_reversal is not None:
        if previous_reversal.idempotency_key == idempotency_key:
            return previous_reversal
        raise InventoryConflict("تم عكس حركة الاستلام من قبل")
    _lock_context(db, original.product_id, original.warehouse_id)
    layer = db.scalar(
        select(InventoryLayer)
        .where(
            InventoryLayer.product_id == original.product_id,
            InventoryLayer.warehouse_id == original.warehouse_id,
            InventoryLayer.source_type == "purchase_receipt",
            InventoryLayer.source_id == str(purchase_receipt_id),
            InventoryLayer.source_line_id == str(purchase_order_line_id),
        )
        .with_for_update()
    )
    if layer is None:
        raise InventoryConflict("تعذر العثور على طبقة FIFO الخاصة بسند الاستلام")
    if (
        layer.quantity_remaining != layer.quantity_received
        or layer.weight_remaining_kg != layer.weight_received_kg
    ):
        raise InventoryConflict("لا يمكن عكس الاستلام بعد صرف جزء من طبقته المخزنية")
    balance = _locked_balance(db, original.product_id, original.warehouse_id)
    if (
        balance.quantity_on_hand < layer.quantity_received
        or balance.weight_on_hand_kg < layer.weight_received_kg
    ):
        raise InsufficientStock("الرصيد الحالي لا يسمح بعكس سند الاستلام")
    reversal = InventoryTransaction(
        idempotency_key=idempotency_key,
        transaction_type="reversal_out",
        product_id=original.product_id,
        warehouse_id=original.warehouse_id,
        lot_id=original.lot_id,
        quantity_delta=-layer.quantity_received,
        weight_delta_kg=-layer.weight_received_kg,
        unit_cost=original.unit_cost,
        total_cost=original.total_cost,
        cost_basis=original.cost_basis,
        reference_type="purchase_receipt_reversal",
        reference_id=str(purchase_receipt_id),
        reference_line_id=str(purchase_order_line_id),
        reversal_of_id=original.id,
        notes=reason.strip(),
        posted_by_id=actor_user_id,
    )
    db.add(reversal)
    db.flush()
    db.add(
        InventoryAllocation(
            outbound_transaction_id=reversal.id,
            source_layer_id=layer.id,
            quantity=layer.quantity_received,
            weight_kg=layer.weight_received_kg,
            unit_cost=original.unit_cost,
            total_cost=original.total_cost,
        )
    )
    layer.quantity_remaining = Decimal("0")
    layer.weight_remaining_kg = Decimal("0")
    layer.version += 1
    balance.quantity_on_hand = quantity(balance.quantity_on_hand - layer.quantity_received)
    balance.weight_on_hand_kg = quantity(balance.weight_on_hand_kg - layer.weight_received_kg)
    balance.version += 1
    add_audit(
        db,
        actor_user_id=actor_user_id,
        event_type="inventory.purchase_receipt.reversal",
        entity_type="inventory_transaction",
        entity_id=str(reversal.id),
        outcome="success",
        client=client,
        after_state={
            "original_transaction_id": str(original.id),
            "purchase_receipt_id": str(purchase_receipt_id),
            "quantity": str(layer.quantity_received),
            "weight_kg": str(layer.weight_received_kg),
        },
    )
    db.flush()
    return reversal


def reverse_sales_return_inventory(
    db: Session,
    *,
    transaction_id: UUID,
    sales_return_id: UUID,
    sales_order_line_id: UUID,
    idempotency_key: str,
    actor_user_id: UUID,
    client: ClientContext,
    reason: str,
) -> InventoryTransaction:
    """Remove the untouched FIFO layer created by a sales return at its original cost."""
    original = db.scalar(
        select(InventoryTransaction)
        .where(InventoryTransaction.id == transaction_id)
        .with_for_update()
    )
    if original is None:
        raise InventoryNotFound("حركة مخزون مرتجع المبيعات غير موجودة")
    if (
        original.transaction_type != "return_in"
        or original.reference_type != "sales_return"
        or original.reference_id != str(sales_return_id)
        or original.reference_line_id != str(sales_order_line_id)
    ):
        raise InventoryConflict("حركة المخزون لا تطابق بند مرتجع المبيعات")
    previous_reversal = db.scalar(
        select(InventoryTransaction).where(InventoryTransaction.reversal_of_id == original.id)
    )
    if previous_reversal is not None:
        if previous_reversal.idempotency_key == idempotency_key:
            return previous_reversal
        raise InventoryConflict("تم عكس حركة مرتجع المبيعات من قبل")
    _lock_context(db, original.product_id, original.warehouse_id)
    layer = db.scalar(
        select(InventoryLayer)
        .where(
            InventoryLayer.product_id == original.product_id,
            InventoryLayer.warehouse_id == original.warehouse_id,
            InventoryLayer.source_type == "sales_return",
            InventoryLayer.source_id == str(sales_return_id),
            InventoryLayer.source_line_id == str(sales_order_line_id),
        )
        .with_for_update()
    )
    if layer is None:
        raise InventoryConflict("تعذر العثور على طبقة FIFO الخاصة بمرتجع المبيعات")
    if (
        layer.quantity_remaining != layer.quantity_received
        or layer.weight_remaining_kg != layer.weight_received_kg
    ):
        raise InventoryConflict("لا يمكن عكس المرتجع بعد صرف جزء من طبقته المخزنية")
    balance = _locked_balance(db, original.product_id, original.warehouse_id)
    if (
        balance.quantity_on_hand < layer.quantity_received
        or balance.weight_on_hand_kg < layer.weight_received_kg
    ):
        raise InsufficientStock("الرصيد الحالي لا يسمح بعكس مرتجع المبيعات")
    reversal = InventoryTransaction(
        idempotency_key=idempotency_key,
        transaction_type="reversal_out",
        product_id=original.product_id,
        warehouse_id=original.warehouse_id,
        lot_id=original.lot_id,
        quantity_delta=-layer.quantity_received,
        weight_delta_kg=-layer.weight_received_kg,
        unit_cost=original.unit_cost,
        total_cost=original.total_cost,
        cost_basis=original.cost_basis,
        reference_type="sales_return_reversal",
        reference_id=str(sales_return_id),
        reference_line_id=str(sales_order_line_id),
        reversal_of_id=original.id,
        notes=reason.strip(),
        posted_by_id=actor_user_id,
    )
    db.add(reversal)
    db.flush()
    db.add(
        InventoryAllocation(
            outbound_transaction_id=reversal.id,
            source_layer_id=layer.id,
            quantity=layer.quantity_received,
            weight_kg=layer.weight_received_kg,
            unit_cost=original.unit_cost,
            total_cost=original.total_cost,
        )
    )
    layer.quantity_remaining = Decimal("0")
    layer.weight_remaining_kg = Decimal("0")
    layer.version += 1
    balance.quantity_on_hand = quantity(balance.quantity_on_hand - layer.quantity_received)
    balance.weight_on_hand_kg = quantity(balance.weight_on_hand_kg - layer.weight_received_kg)
    balance.version += 1
    add_audit(
        db,
        actor_user_id=actor_user_id,
        event_type="inventory.sales_return.reversal",
        entity_type="inventory_transaction",
        entity_id=str(reversal.id),
        outcome="success",
        client=client,
        after_state={
            "original_transaction_id": str(original.id),
            "sales_return_id": str(sales_return_id),
            "quantity": str(layer.quantity_received),
            "weight_kg": str(layer.weight_received_kg),
        },
    )
    db.flush()
    return reversal


def reverse_purchase_return_inventory(
    db: Session,
    *,
    transaction_id: UUID,
    purchase_return_id: UUID,
    purchase_order_line_id: UUID,
    idempotency_key: str,
    actor_user_id: UUID,
    client: ClientContext,
    reason: str,
) -> InventoryTransaction:
    """Restore a supplier-return issue using the exact quantity, weight and FIFO cost."""
    original = db.scalar(
        select(InventoryTransaction)
        .where(InventoryTransaction.id == transaction_id)
        .with_for_update()
    )
    if original is None:
        raise InventoryNotFound("حركة مخزون مرتجع المشتريات غير موجودة")
    if (
        original.transaction_type != "return_out"
        or original.reference_type != "purchase_return"
        or original.reference_id != str(purchase_return_id)
        or original.reference_line_id != str(purchase_order_line_id)
    ):
        raise InventoryConflict("حركة المخزون لا تطابق بند مرتجع المشتريات")
    previous_reversal = db.scalar(
        select(InventoryTransaction).where(InventoryTransaction.reversal_of_id == original.id)
    )
    if previous_reversal is not None:
        if previous_reversal.idempotency_key == idempotency_key:
            return previous_reversal
        raise InventoryConflict("تم عكس حركة مرتجع المشتريات من قبل")
    return post_receipt(
        db,
        payload=ReceiptRequest(
            product_id=original.product_id,
            warehouse_id=original.warehouse_id,
            quantity=-original.quantity_delta,
            weight_kg=-original.weight_delta_kg,
            cost_basis=cast(CostBasis, original.cost_basis),
            unit_cost=original.unit_cost,
            reference_type="purchase_return_reversal",
            reference_id=str(purchase_return_id),
            reference_line_id=str(purchase_order_line_id),
            notes=reason,
        ),
        idempotency_key=idempotency_key,
        actor_user_id=actor_user_id,
        client=client,
        transaction_type="reversal_in",
        reversal_of_id=original.id,
    )


def reverse_transaction(
    db: Session,
    *,
    transaction_id: UUID,
    payload: ReversalRequest,
    idempotency_key: str,
    actor_user_id: UUID,
    client: ClientContext,
) -> InventoryTransaction:
    original = db.scalar(
        select(InventoryTransaction)
        .where(InventoryTransaction.id == transaction_id)
        .with_for_update()
    )
    if original is None:
        raise InventoryNotFound("حركة المخزون غير موجودة")
    if original.reversal_of_id is not None:
        raise InventoryConflict("لا يمكن عكس حركة عكسية")
    if original.transaction_type not in {"receipt", "issue", "adjustment_in", "adjustment_out"}:
        raise InventoryConflict("هذه الحركة تُعكس من مستندها التشغيلي وليس من كارت المخزون")
    previous_reversal = db.scalar(
        select(InventoryTransaction).where(InventoryTransaction.reversal_of_id == original.id)
    )
    if previous_reversal is not None:
        if previous_reversal.idempotency_key == idempotency_key:
            return previous_reversal
        raise InventoryConflict("تم عكس هذه الحركة من قبل")

    basis = cast(CostBasis, original.cost_basis)
    if original.quantity_delta > 0 or original.weight_delta_kg > 0:
        amount = original.quantity_delta if basis == "quantity" else original.weight_delta_kg
        return post_issue(
            db,
            payload=IssueRequest(
                product_id=original.product_id,
                warehouse_id=original.warehouse_id,
                amount=amount,
                cost_basis=basis,
                reference_type="movement_reversal",
                reference_id=str(original.id),
                notes=payload.reason,
            ),
            idempotency_key=idempotency_key,
            actor_user_id=actor_user_id,
            client=client,
            transaction_type="reversal_out",
            reversal_of_id=original.id,
        )
    return post_receipt(
        db,
        payload=ReceiptRequest(
            product_id=original.product_id,
            warehouse_id=original.warehouse_id,
            quantity=-original.quantity_delta,
            weight_kg=-original.weight_delta_kg,
            cost_basis=basis,
            unit_cost=original.unit_cost,
            reference_type="movement_reversal",
            reference_id=str(original.id),
            notes=payload.reason,
        ),
        idempotency_key=idempotency_key,
        actor_user_id=actor_user_id,
        client=client,
        transaction_type="reversal_in",
        reversal_of_id=original.id,
    )


def list_balances(db: Session) -> list[BalanceView]:
    rows = db.execute(
        select(
            InventoryBalance,
            Product.code,
            Product.name_ar,
            Warehouse.name_ar.label("warehouse_name_ar"),
        )
        .join(Product, Product.id == InventoryBalance.product_id)
        .join(Warehouse, Warehouse.id == InventoryBalance.warehouse_id)
        .order_by(Product.code, Warehouse.name_ar)
    )
    return [
        BalanceView(
            product_id=balance.product_id,
            warehouse_id=balance.warehouse_id,
            quantity_on_hand=balance.quantity_on_hand,
            weight_on_hand_kg=balance.weight_on_hand_kg,
            version=balance.version,
            product_code=product_code,
            product_name_ar=product_name_ar,
            warehouse_name_ar=warehouse_name_ar,
        )
        for balance, product_code, product_name_ar, warehouse_name_ar in rows
    ]


def list_transactions(db: Session, *, limit: int = 100) -> list[TransactionView]:
    rows = db.execute(
        select(
            InventoryTransaction,
            Product.code,
            Product.name_ar,
            Warehouse.name_ar.label("warehouse_name_ar"),
        )
        .join(Product, Product.id == InventoryTransaction.product_id)
        .join(Warehouse, Warehouse.id == InventoryTransaction.warehouse_id)
        .order_by(InventoryTransaction.posted_at.desc(), InventoryTransaction.id.desc())
        .limit(limit)
    )
    return [
        TransactionView(
            id=transaction.id,
            idempotency_key=transaction.idempotency_key,
            transaction_type=transaction.transaction_type,
            product_id=transaction.product_id,
            warehouse_id=transaction.warehouse_id,
            lot_id=transaction.lot_id,
            quantity_delta=transaction.quantity_delta,
            weight_delta_kg=transaction.weight_delta_kg,
            unit_cost=transaction.unit_cost,
            total_cost=transaction.total_cost,
            cost_basis=cast(CostBasis, transaction.cost_basis),
            reference_type=transaction.reference_type,
            reference_id=transaction.reference_id,
            reversal_of_id=transaction.reversal_of_id,
            product_code=product_code,
            product_name_ar=product_name_ar,
            warehouse_name_ar=warehouse_name_ar,
            notes=transaction.notes,
            posted_at=transaction.posted_at,
        )
        for transaction, product_code, product_name_ar, warehouse_name_ar in rows
    ]


def transaction_view(db: Session, transaction: InventoryTransaction) -> TransactionView:
    product = db.get(Product, transaction.product_id)
    warehouse = db.get(Warehouse, transaction.warehouse_id)
    if product is None or warehouse is None:
        raise InventoryNotFound("تعذر تحميل بيانات المنتج أو المخزن المرتبطة بالحركة")
    return TransactionView(
        id=transaction.id,
        idempotency_key=transaction.idempotency_key,
        transaction_type=transaction.transaction_type,
        product_id=transaction.product_id,
        warehouse_id=transaction.warehouse_id,
        lot_id=transaction.lot_id,
        quantity_delta=transaction.quantity_delta,
        weight_delta_kg=transaction.weight_delta_kg,
        unit_cost=transaction.unit_cost,
        total_cost=transaction.total_cost,
        cost_basis=cast(CostBasis, transaction.cost_basis),
        reference_type=transaction.reference_type,
        reference_id=transaction.reference_id,
        reversal_of_id=transaction.reversal_of_id,
        product_code=product.code,
        product_name_ar=product.name_ar,
        warehouse_name_ar=warehouse.name_ar,
        notes=transaction.notes,
        posted_at=transaction.posted_at,
    )


def inventory_options(db: Session) -> InventoryOptionsView:
    products = db.execute(
        select(Product.id, Product.code, Product.name_ar)
        .where(Product.is_active.is_(True), Product.product_type != "service")
        .order_by(Product.code)
    )
    warehouses = db.execute(
        select(Warehouse.id, Warehouse.code, Warehouse.name_ar)
        .where(Warehouse.is_active.is_(True))
        .order_by(Warehouse.is_default.desc(), Warehouse.code)
    )
    return InventoryOptionsView(
        products=[
            InventoryOption(id=row.id, code=row.code, name_ar=row.name_ar) for row in products
        ],
        warehouses=[
            InventoryOption(id=row.id, code=row.code, name_ar=row.name_ar) for row in warehouses
        ],
    )
