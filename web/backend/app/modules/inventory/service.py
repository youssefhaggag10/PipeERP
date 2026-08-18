import unicodedata
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
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
    InventoryOption,
    InventoryOptionsView,
    IssueRequest,
    ReceiptRequest,
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
) -> InventoryTransaction:
    if transaction_type not in {
        "receipt",
        "transfer_in",
        "adjustment_in",
        "return_in",
        "production_output",
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
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        reference_line_id=payload.reference_line_id,
        reversal_of_id=None,
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
) -> InventoryTransaction:
    if transaction_type not in {
        "issue",
        "transfer_out",
        "adjustment_out",
        "return_out",
        "production_issue",
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
                InventoryLayer.cost_basis == payload.cost_basis,
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
                    unit_cost=layer.unit_cost,
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
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        reference_line_id=payload.reference_line_id,
        reversal_of_id=None,
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
            reference_type=transaction.reference_type,
            reference_id=transaction.reference_id,
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
        reference_type=transaction.reference_type,
        reference_id=transaction.reference_id,
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
