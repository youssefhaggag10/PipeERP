from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.common.decimal import money, quantity
from app.domain.purchasing.costing import calculate_receipt_cost, validate_partial_receipt
from app.modules.identity.service import ClientContext, Principal, add_audit
from app.modules.inventory.schemas import ReceiptRequest
from app.modules.inventory.service import (
    InsufficientStock,
    InventoryConflict,
    InventoryNotFound,
    post_receipt,
    reverse_purchase_receipt_inventory,
)
from app.modules.master_data.models import Partner, Product, UnitOfMeasure, Warehouse
from app.modules.master_data.service import allocate_document_number
from app.modules.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    SupplierInvoice,
)
from app.modules.purchasing.schemas import (
    CreatePurchaseOrderRequest,
    CreateSupplierInvoiceRequest,
    PostPurchaseReceiptRequest,
    PurchaseOption,
    PurchaseOptionsView,
    PurchaseOrderLineView,
    PurchaseOrderView,
    PurchaseReceiptLineView,
    PurchaseReceiptView,
    ReceivePurchaseOrderRequest,
    ReversePurchaseReceiptRequest,
    ReverseSupplierInvoiceRequest,
    SupplierInvoiceView,
)
from app.modules.returns.models import InvoiceReturn
from app.modules.treasury.models import FinancialAccount, PaymentAllocation, PaymentTransaction


class PurchasingError(Exception):
    pass


class PurchasingNotFound(PurchasingError):
    pass


class PurchasingConflict(PurchasingError):
    pass


def _request_hash(payload: PostPurchaseReceiptRequest) -> str:
    return sha256(payload.model_dump_json().encode()).hexdigest()


def _order_view(db: Session, order: PurchaseOrder) -> PurchaseOrderView:
    supplier = db.get(Partner, order.supplier_id)
    warehouse = db.get(Warehouse, order.warehouse_id)
    if supplier is None or warehouse is None:
        raise PurchasingNotFound("بيانات المورد أو المخزن المرتبطة بأمر الشراء غير موجودة")
    lines = list(
        db.scalars(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id == order.id)
            .order_by(PurchaseOrderLine.created_at, PurchaseOrderLine.id)
        )
    )
    products = {
        item.id: item
        for item in db.scalars(
            select(Product).where(Product.id.in_({line.product_id for line in lines}))
        )
    }
    supplier_invoice = db.scalar(
        select(SupplierInvoice).where(SupplierInvoice.purchase_order_id == order.id)
    )
    return PurchaseOrderView(
        id=order.id,
        order_number=order.order_number,
        supplier_id=order.supplier_id,
        supplier_code=supplier.code,
        supplier_name_ar=supplier.name_ar,
        warehouse_id=order.warehouse_id,
        warehouse_name_ar=warehouse.name_ar,
        status=order.status,  # type: ignore[arg-type]
        order_date=order.order_date,
        notes=order.notes,
        total=order.total,
        version=order.version,
        supplier_invoice=(
            SupplierInvoiceView.model_validate(supplier_invoice)
            if supplier_invoice is not None
            else None
        ),
        lines=[
            PurchaseOrderLineView(
                id=line.id,
                product_id=line.product_id,
                product_code=products[line.product_id].code,
                product_name_ar=products[line.product_id].name_ar,
                cost_basis=line.cost_basis,  # type: ignore[arg-type]
                ordered_quantity=line.ordered_quantity,
                ordered_weight_kg=line.ordered_weight_kg,
                received_quantity=line.received_quantity,
                received_weight_kg=line.received_weight_kg,
                unit_price=line.unit_price,
                additional_unit_cost=line.additional_unit_cost,
                lot_number=line.lot_number,
                purchase_loss_quantity=line.purchase_loss_quantity,
                net_quantity=line.net_quantity,
                inventory_unit_cost=line.inventory_unit_cost,
                line_total=line.line_total,
                version=line.version,
            )
            for line in lines
        ],
    )


def list_purchase_orders(db: Session, *, limit: int = 100) -> list[PurchaseOrderView]:
    orders = list(
        db.scalars(select(PurchaseOrder).order_by(PurchaseOrder.order_date.desc()).limit(limit))
    )
    return [_order_view(db, order) for order in orders]


def get_purchase_order(db: Session, order_id: UUID) -> PurchaseOrderView:
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise PurchasingNotFound("أمر الشراء غير موجود")
    return _order_view(db, order)


def purchase_options(db: Session) -> PurchaseOptionsView:
    suppliers = list(
        db.scalars(
            select(Partner)
            .where(Partner.is_active.is_(True), Partner.is_supplier.is_(True))
            .order_by(Partner.name_ar)
        )
    )
    warehouses = list(
        db.scalars(
            select(Warehouse)
            .where(Warehouse.is_active.is_(True), Warehouse.is_default.is_(True))
            .order_by(Warehouse.name_ar)
        )
    )
    if not warehouses:
        fallback = db.scalar(
            select(Warehouse).where(Warehouse.is_active.is_(True)).order_by(Warehouse.name_ar)
        )
        warehouses = [fallback] if fallback is not None else []
    products = list(
        db.scalars(
            select(Product)
            .where(Product.is_active.is_(True), Product.product_type != "service")
            .order_by(Product.name_ar)
        )
    )
    units = {
        item.id: item
        for item in db.scalars(
            select(UnitOfMeasure).where(UnitOfMeasure.id.in_({item.unit_id for item in products}))
        )
    }
    financial_accounts = list(
        db.scalars(
            select(FinancialAccount)
            .where(FinancialAccount.is_active.is_(True))
            .order_by(FinancialAccount.is_default.desc(), FinancialAccount.name_ar)
        )
    )
    return PurchaseOptionsView(
        suppliers=[
            PurchaseOption(id=item.id, code=item.code, name_ar=item.name_ar) for item in suppliers
        ],
        warehouses=[
            PurchaseOption(id=item.id, code=item.code, name_ar=item.name_ar) for item in warehouses
        ],
        products=[
            PurchaseOption(
                id=item.id,
                code=item.code,
                name_ar=item.name_ar,
                unit_symbol=units[item.unit_id].symbol,
            )
            for item in products
        ],
        financial_accounts=[
            PurchaseOption(
                id=item.id,
                code=item.code,
                name_ar=item.name_ar,
                account_type=item.account_type,
            )
            for item in financial_accounts
        ],
    )


def _post_purchase_advance(
    db: Session,
    *,
    order: PurchaseOrder,
    payload: CreatePurchaseOrderRequest,
    actor: Principal,
    client: ClientContext,
) -> None:
    if payload.advance_amount <= 0:
        return
    if payload.advance_amount > order.total:
        raise PurchasingConflict("الدفعة المقدمة أكبر من إجمالي أمر الشراء")
    if payload.advance_financial_account_id is None:
        raise PurchasingConflict("اختر حساب الخزينة أو البنك للدفعة المقدمة")
    from app.modules.treasury.schemas import PostPaymentRequest
    from app.modules.treasury.service import post_payment

    post_payment(
        db,
        payload=PostPaymentRequest(
            transaction_type="supplier_payment",
            partner_id=order.supplier_id,
            financial_account_id=payload.advance_financial_account_id,
            amount=payload.advance_amount,
            payment_method=payload.advance_payment_method,
            reference_type="purchase",
            reference_id=order.id,
            notes=f"دفعة مقدمة عند إنشاء أمر الشراء {order.order_number}",
        ),
        idempotency_key=f"purchase-order-advance-{order.id}",
        actor=actor,
        client=client,
    )


def create_purchase_order(
    db: Session,
    *,
    payload: CreatePurchaseOrderRequest,
    actor: Principal,
    client: ClientContext,
) -> PurchaseOrderView:
    if payload.advance_amount > 0:
        raise PurchasingConflict("سداد المورد يتم من شاشة الحسابات بعد استلام أمر الشراء")
    supplier = db.get(Partner, payload.supplier_id)
    if supplier is None or not supplier.is_active or not supplier.is_supplier:
        raise PurchasingNotFound("المورد غير موجود أو غير نشط")
    warehouse = db.scalar(
        select(Warehouse).where(Warehouse.is_active.is_(True), Warehouse.is_default.is_(True))
    )
    if warehouse is None:
        warehouse = db.scalar(
            select(Warehouse).where(Warehouse.is_active.is_(True)).order_by(Warehouse.name_ar)
        )
    if warehouse is None:
        raise PurchasingNotFound("لا يوجد مخزن مصنع نشط")
    products = {
        item.id: item
        for item in db.scalars(
            select(Product).where(Product.id.in_({line.product_id for line in payload.lines}))
        )
    }
    for line in payload.lines:
        product = products.get(line.product_id)
        if product is None or not product.is_active or product.product_type == "service":
            raise PurchasingNotFound("أحد منتجات أمر الشراء غير موجود أو غير صالح للمخزون")
    order = PurchaseOrder(
        order_number=allocate_document_number(db, "purchase_order"),
        supplier_id=payload.supplier_id,
        warehouse_id=warehouse.id,
        status="draft",
        notes=payload.notes.strip(),
        total=Decimal("0"),
        version=1,
        created_by_id=actor.user.id,
    )
    db.add(order)
    db.flush()
    total = Decimal("0")
    for payload_line in payload.lines:
        product = products[payload_line.product_id]
        ordered_quantity = quantity(payload_line.ordered_quantity)
        ordered_weight = quantity(payload_line.ordered_weight_kg)
        basis_amount = ordered_quantity if payload_line.cost_basis == "quantity" else ordered_weight
        default_loss = Decimal("0")
        purchase_loss = quantity(
            payload_line.purchase_loss_quantity
            if payload_line.purchase_loss_quantity is not None
            else default_loss
        )
        if purchase_loss >= ordered_quantity and ordered_quantity > 0:
            raise PurchasingConflict("فقد الشراء يجب أن يكون أقل من الكمية")
        net_quantity = quantity(ordered_quantity - purchase_loss)
        # Supplier payable excludes internal processing/handling cost. That
        # extra cost is capitalized into FIFO only when goods are received.
        line_total = money(basis_amount * payload_line.unit_price)
        inventory_total = basis_amount * (
            payload_line.unit_price + payload_line.additional_unit_cost
        )
        net_basis = net_quantity if payload_line.cost_basis == "quantity" else ordered_weight
        inventory_unit_cost = quantity(inventory_total / net_basis)
        lot_number = payload_line.lot_number.strip() or f"PUR-{order.order_number}-{product.code}"
        total += line_total
        db.add(
            PurchaseOrderLine(
                purchase_order_id=order.id,
                product_id=payload_line.product_id,
                cost_basis=payload_line.cost_basis,
                ordered_quantity=ordered_quantity,
                ordered_weight_kg=ordered_weight,
                unit_price=quantity(payload_line.unit_price),
                additional_unit_cost=quantity(payload_line.additional_unit_cost),
                lot_number=lot_number,
                purchase_loss_quantity=purchase_loss,
                net_quantity=net_quantity,
                inventory_unit_cost=inventory_unit_cost,
                line_total=line_total,
                received_quantity=Decimal("0"),
                received_weight_kg=Decimal("0"),
                version=1,
            )
        )
    order.total = money(total)
    db.flush()
    _post_purchase_advance(db, order=order, payload=payload, actor=actor, client=client)
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="purchasing.order.create",
        entity_type="purchase_order",
        entity_id=str(order.id),
        outcome="success",
        client=client,
        after_state={
            "order_number": order.order_number,
            "supplier_id": str(order.supplier_id),
            "total": str(order.total),
        },
    )
    db.flush()
    return _order_view(db, order)


def approve_purchase_order(
    db: Session,
    *,
    order_id: UUID,
    version: int,
    actor: Principal,
    client: ClientContext,
) -> PurchaseOrderView:
    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id).with_for_update())
    if order is None:
        raise PurchasingNotFound("أمر الشراء غير موجود")
    if order.version != version:
        raise PurchasingConflict("عدّل مستخدم آخر أمر الشراء؛ حدّث الصفحة ثم أعد المحاولة")
    if order.status != "draft":
        raise PurchasingConflict("يمكن اعتماد أمر الشراء وهو في حالة مسودة فقط")
    order.status = "approved"
    order.version += 1
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="purchasing.order.approve",
        entity_type="purchase_order",
        entity_id=str(order.id),
        outcome="success",
        client=client,
        before_state={"status": "draft", "version": version},
        after_state={"status": order.status, "version": order.version},
    )
    db.flush()
    return _order_view(db, order)


def _receipt_view(db: Session, receipt: PurchaseReceipt) -> PurchaseReceiptView:
    rows = db.execute(
        select(PurchaseReceiptLine, PurchaseOrderLine, Product)
        .join(PurchaseOrderLine, PurchaseOrderLine.id == PurchaseReceiptLine.purchase_order_line_id)
        .join(Product, Product.id == PurchaseOrderLine.product_id)
        .where(PurchaseReceiptLine.purchase_receipt_id == receipt.id)
        .order_by(PurchaseReceiptLine.created_at, PurchaseReceiptLine.id)
    ).all()
    return PurchaseReceiptView(
        id=receipt.id,
        receipt_number=receipt.receipt_number,
        purchase_order_id=receipt.purchase_order_id,
        status=receipt.status,  # type: ignore[arg-type]
        notes=receipt.notes,
        posted_at=receipt.posted_at,
        reversed_at=receipt.reversed_at,
        reversal_reason=receipt.reversal_reason,
        lines=[
            PurchaseReceiptLineView(
                id=receipt_line.id,
                purchase_order_line_id=receipt_line.purchase_order_line_id,
                inventory_transaction_id=receipt_line.inventory_transaction_id,
                product_code=product.code,
                product_name_ar=product.name_ar,
                lot_number=receipt_line.lot_number,
                gross_quantity=receipt_line.gross_quantity,
                gross_weight_kg=receipt_line.gross_weight_kg,
                loss_quantity=receipt_line.loss_quantity,
                loss_weight_kg=receipt_line.loss_weight_kg,
                net_quantity=receipt_line.net_quantity,
                net_weight_kg=receipt_line.net_weight_kg,
                capitalized_cost=receipt_line.capitalized_cost,
                inventory_unit_cost=receipt_line.inventory_unit_cost,
            )
            for receipt_line, _, product in rows
        ],
    )


def list_purchase_receipts(db: Session, *, order_id: UUID) -> list[PurchaseReceiptView]:
    if db.get(PurchaseOrder, order_id) is None:
        raise PurchasingNotFound("أمر الشراء غير موجود")
    receipts = list(
        db.scalars(
            select(PurchaseReceipt)
            .where(PurchaseReceipt.purchase_order_id == order_id)
            .order_by(PurchaseReceipt.posted_at.desc(), PurchaseReceipt.id.desc())
        )
    )
    return [_receipt_view(db, receipt) for receipt in receipts]


def post_purchase_receipt(
    db: Session,
    *,
    order_id: UUID,
    payload: PostPurchaseReceiptRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> PurchaseReceiptView:
    payload_hash = _request_hash(payload)
    existing = db.scalar(
        select(PurchaseReceipt).where(PurchaseReceipt.idempotency_key == idempotency_key)
    )
    if existing is not None:
        if existing.purchase_order_id != order_id or existing.request_hash != payload_hash:
            raise PurchasingConflict("مفتاح منع التكرار مستخدم بالفعل لطلب مختلف")
        return _receipt_view(db, existing)

    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id).with_for_update())
    if order is None:
        raise PurchasingNotFound("أمر الشراء غير موجود")
    if order.status not in {"approved", "partially_received"}:
        raise PurchasingConflict("يجب اعتماد أمر الشراء قبل تسجيل الاستلام")
    order_lines = {
        line.id: line
        for line in db.scalars(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id == order.id)
            .with_for_update()
        )
    }
    if any(item.purchase_order_line_id not in order_lines for item in payload.lines):
        raise PurchasingNotFound("أحد بنود الاستلام لا يتبع أمر الشراء")

    receipt = PurchaseReceipt(
        receipt_number=allocate_document_number(db, "purchase_receipt"),
        idempotency_key=idempotency_key,
        request_hash=payload_hash,
        purchase_order_id=order.id,
        status="posted",
        notes=payload.notes.strip(),
        posted_by_id=actor.user.id,
    )
    db.add(receipt)
    db.flush()

    for received in payload.lines:
        line = order_lines[received.purchase_order_line_id]
        product = db.get(Product, line.product_id)
        if product is None:
            raise PurchasingNotFound("الصنف المرتبط ببند الشراء غير موجود")
        gross_quantity = quantity(received.gross_quantity)
        gross_weight = quantity(received.gross_weight_kg)
        loss_quantity = quantity(received.loss_quantity)
        loss_weight = quantity(received.loss_weight_kg)
        gross_basis = gross_quantity if line.cost_basis == "quantity" else gross_weight
        loss_basis = loss_quantity if line.cost_basis == "quantity" else loss_weight
        ordered_basis = (
            line.ordered_quantity if line.cost_basis == "quantity" else line.ordered_weight_kg
        )
        previous_basis = (
            line.received_quantity if line.cost_basis == "quantity" else line.received_weight_kg
        )
        validate_partial_receipt(
            ordered_amount=ordered_basis,
            previously_received_amount=previous_basis,
            current_received_amount=gross_basis,
        )
        if gross_quantity + line.received_quantity > line.ordered_quantity:
            raise PurchasingConflict("العدد المستلم يتجاوز العدد المتبقي في أمر الشراء")
        if gross_weight + line.received_weight_kg > line.ordered_weight_kg:
            raise PurchasingConflict("الوزن المستلم يتجاوز الوزن المتبقي في أمر الشراء")
        costing = calculate_receipt_cost(
            gross_amount=gross_basis,
            loss_amount=loss_basis,
            unit_price=line.unit_price,
            additional_unit_cost=line.additional_unit_cost,
        )
        net_quantity = quantity(gross_quantity - loss_quantity)
        net_weight = quantity(gross_weight - loss_weight)
        if (line.cost_basis == "quantity" and net_quantity <= 0) or (
            line.cost_basis == "weight" and net_weight <= 0
        ):
            raise PurchasingConflict("صافي الاستلام يجب أن يكون أكبر من صفر")
        lot_number = received.lot_number.strip() or f"{receipt.receipt_number}-{product.code}"
        child_key = sha256(f"purchase:{idempotency_key}:{line.id}".encode()).hexdigest()
        transaction = post_receipt(
            db,
            payload=ReceiptRequest(
                product_id=line.product_id,
                warehouse_id=order.warehouse_id,
                quantity=net_quantity,
                weight_kg=net_weight,
                cost_basis=line.cost_basis,  # type: ignore[arg-type]
                unit_cost=costing.inventory_unit_cost,
                lot_number=lot_number,
                reference_type="purchase_receipt",
                reference_id=str(receipt.id),
                reference_line_id=str(line.id),
                notes=payload.notes,
            ),
            idempotency_key=child_key,
            actor_user_id=actor.user.id,
            client=client,
        )
        db.add(
            PurchaseReceiptLine(
                purchase_receipt_id=receipt.id,
                purchase_order_line_id=line.id,
                inventory_transaction_id=transaction.id,
                lot_number=lot_number,
                gross_quantity=gross_quantity,
                gross_weight_kg=gross_weight,
                loss_quantity=loss_quantity,
                loss_weight_kg=loss_weight,
                net_quantity=net_quantity,
                net_weight_kg=net_weight,
                capitalized_cost=costing.capitalized_cost,
                inventory_unit_cost=costing.inventory_unit_cost,
            )
        )
        line.received_quantity = quantity(line.received_quantity + gross_quantity)
        line.received_weight_kg = quantity(line.received_weight_kg + gross_weight)
        line.version += 1

    all_received = all(
        (line.received_quantity >= line.ordered_quantity)
        if line.cost_basis == "quantity"
        else (line.received_weight_kg >= line.ordered_weight_kg)
        for line in order_lines.values()
    )
    order.status = "received" if all_received else "partially_received"
    order.version += 1
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="purchasing.receipt.post",
        entity_type="purchase_receipt",
        entity_id=str(receipt.id),
        outcome="success",
        client=client,
        after_state={
            "receipt_number": receipt.receipt_number,
            "purchase_order_id": str(order.id),
            "order_status": order.status,
            "line_count": len(payload.lines),
        },
    )
    db.flush()
    return _receipt_view(db, receipt)


def create_supplier_invoice(
    db: Session,
    *,
    order_id: UUID,
    payload: CreateSupplierInvoiceRequest,
    actor: Principal,
    client: ClientContext,
) -> SupplierInvoiceView:
    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id).with_for_update())
    if order is None:
        raise PurchasingNotFound("أمر الشراء غير موجود")
    if order.status != "received":
        raise PurchasingConflict("يجب استلام أمر الشراء بالكامل قبل تسجيل فاتورة المورد")
    existing = db.scalar(
        select(SupplierInvoice).where(SupplierInvoice.purchase_order_id == order.id)
    )
    if existing is not None:
        raise PurchasingConflict("تم تسجيل فاتورة مورد لأمر الشراء بالفعل")
    invoice_number = allocate_document_number(db, "purchase_invoice")
    invoice = SupplierInvoice(
        invoice_number=invoice_number,
        supplier_invoice_number=payload.supplier_invoice_number.strip() or invoice_number,
        purchase_order_id=order.id,
        supplier_id=order.supplier_id,
        status="posted",
        total=order.total,
        posted_at=datetime.now(UTC),
        version=1,
    )
    db.add(invoice)
    db.flush()
    from app.modules.treasury.service import apply_order_advances_to_invoice

    apply_order_advances_to_invoice(
        db,
        reference_type="purchase",
        reference_id=order.id,
        invoice=invoice,
    )
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="purchasing.invoice.post",
        entity_type="supplier_invoice",
        entity_id=str(invoice.id),
        outcome="success",
        client=client,
        after_state={
            "invoice_number": invoice.invoice_number,
            "supplier_invoice_number": invoice.supplier_invoice_number,
            "total": str(invoice.total),
        },
    )
    return SupplierInvoiceView.model_validate(invoice)


def receive_purchase_order(
    db: Session,
    *,
    order_id: UUID,
    payload: ReceivePurchaseOrderRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> PurchaseOrderView:
    """Mirror the desktop action: receive every remaining line and post its invoice."""
    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id).with_for_update())
    if order is None:
        raise PurchasingNotFound("أمر الشراء غير موجود")
    if order.status == "received":
        return _order_view(db, order)
    if order.version != payload.version:
        raise PurchasingConflict("عدّل مستخدم آخر أمر الشراء؛ حدّث الصفحة ثم أعد المحاولة")
    if order.status not in {"draft", "approved", "partially_received"}:
        raise PurchasingConflict("لا يمكن استلام أمر الشراء في حالته الحالية")

    lines = list(
        db.scalars(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id == order.id)
            .order_by(PurchaseOrderLine.created_at, PurchaseOrderLine.id)
            .with_for_update()
        )
    )
    receipt_lines = []
    for line in lines:
        remaining_quantity = quantity(line.ordered_quantity - line.received_quantity)
        remaining_weight = quantity(line.ordered_weight_kg - line.received_weight_kg)
        if remaining_quantity <= 0 and remaining_weight <= 0:
            continue
        receipt_lines.append(
            {
                "purchase_order_line_id": line.id,
                "gross_quantity": remaining_quantity,
                "gross_weight_kg": remaining_weight,
                "loss_quantity": (
                    line.purchase_loss_quantity
                    if line.received_quantity == 0
                    else Decimal("0")
                ),
                "loss_weight_kg": Decimal("0"),
                "lot_number": line.lot_number,
            }
        )
    if not receipt_lines:
        raise PurchasingConflict("لا توجد كميات متبقية لاستلامها")

    # The web database keeps the intermediate status for compatibility, but the
    # user-facing workflow performs this transition inside one atomic action.
    if order.status == "draft":
        order.status = "approved"
        db.flush()
    post_purchase_receipt(
        db,
        order_id=order.id,
        payload=PostPurchaseReceiptRequest.model_validate(
            {"notes": order.notes, "lines": receipt_lines}
        ),
        idempotency_key=idempotency_key,
        actor=actor,
        client=client,
    )
    refreshed = db.get(PurchaseOrder, order.id)
    if refreshed is None or refreshed.status != "received":
        raise PurchasingConflict("تعذر استلام جميع بنود أمر الشراء")
    existing_invoice = db.scalar(
        select(SupplierInvoice).where(SupplierInvoice.purchase_order_id == order.id)
    )
    if existing_invoice is None:
        create_supplier_invoice(
            db,
            order_id=order.id,
            payload=CreateSupplierInvoiceRequest(),
            actor=actor,
            client=client,
        )
    db.flush()
    return _order_view(db, refreshed)


def reverse_supplier_invoice(
    db: Session,
    *,
    invoice_id: UUID,
    payload: ReverseSupplierInvoiceRequest,
    actor: Principal,
    client: ClientContext,
) -> SupplierInvoiceView:
    invoice = db.scalar(
        select(SupplierInvoice).where(SupplierInvoice.id == invoice_id).with_for_update()
    )
    if invoice is None:
        raise PurchasingNotFound("فاتورة المورد غير موجودة")
    if invoice.status == "reversed":
        raise PurchasingConflict("تم عكس فاتورة المورد من قبل")
    posted_return = db.scalar(
        select(InvoiceReturn.id).where(
            InvoiceReturn.supplier_invoice_id == invoice.id,
            InvoiceReturn.status == "posted",
        )
    )
    if posted_return is not None:
        raise PurchasingConflict("يجب عكس مرتجع المشتريات المرتبط بالفاتورة أولًا")

    allocations = list(
        db.scalars(
            select(PaymentAllocation).where(PaymentAllocation.supplier_invoice_id == invoice.id)
        )
    )
    payment_ids = {allocation.payment_transaction_id for allocation in allocations}
    payments = list(
        db.scalars(
            select(PaymentTransaction)
            .where(PaymentTransaction.id.in_(payment_ids))
            .with_for_update()
        )
    ) if payment_ids else []
    for allocation in allocations:
        db.delete(allocation)
    for payment in payments:
        if payment.supplier_invoice_id == invoice.id:
            payment.supplier_invoice_id = None

    invoice.status = "reversed"
    invoice.version += 1
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="purchasing.invoice.reverse",
        entity_type="supplier_invoice",
        entity_id=str(invoice.id),
        outcome="success",
        client=client,
        before_state={"status": "posted", "version": invoice.version - 1},
        after_state={
            "status": "reversed",
            "version": invoice.version,
            "reason": payload.reason.strip(),
            "released_payment_allocations": len(allocations),
        },
    )
    db.flush()
    return SupplierInvoiceView.model_validate(invoice)


def reverse_purchase_receipt(
    db: Session,
    *,
    receipt_id: UUID,
    payload: ReversePurchaseReceiptRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> PurchaseReceiptView:
    receipt = db.scalar(
        select(PurchaseReceipt).where(PurchaseReceipt.id == receipt_id).with_for_update()
    )
    if receipt is None:
        raise PurchasingNotFound("سند الاستلام غير موجود")
    if receipt.status == "reversed":
        if receipt.reversal_idempotency_key == idempotency_key:
            return _receipt_view(db, receipt)
        raise PurchasingConflict("تم عكس سند الاستلام من قبل")
    invoice = db.scalar(
        select(SupplierInvoice).where(
            SupplierInvoice.purchase_order_id == receipt.purchase_order_id,
            SupplierInvoice.status == "posted",
        )
    )
    if invoice is not None:
        raise PurchasingConflict("يجب عكس فاتورة المورد قبل عكس سند الاستلام")
    order = db.scalar(
        select(PurchaseOrder).where(PurchaseOrder.id == receipt.purchase_order_id).with_for_update()
    )
    if order is None:
        raise PurchasingNotFound("أمر الشراء المرتبط بسند الاستلام غير موجود")
    order_lines = {
        line.id: line
        for line in db.scalars(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id == order.id)
            .with_for_update()
        )
    }
    receipt_lines = list(
        db.scalars(
            select(PurchaseReceiptLine)
            .where(PurchaseReceiptLine.purchase_receipt_id == receipt.id)
            .order_by(PurchaseReceiptLine.id)
        )
    )
    for receipt_line in receipt_lines:
        order_line = order_lines.get(receipt_line.purchase_order_line_id)
        if order_line is None:
            raise PurchasingConflict("تعذر تحميل بند أمر الشراء المرتبط بالاستلام")
        child_key = sha256(
            f"purchase-reversal:{idempotency_key}:{receipt_line.id}".encode()
        ).hexdigest()
        try:
            reverse_purchase_receipt_inventory(
                db,
                transaction_id=receipt_line.inventory_transaction_id,
                purchase_receipt_id=receipt.id,
                purchase_order_line_id=order_line.id,
                idempotency_key=child_key,
                actor_user_id=actor.user.id,
                client=client,
                reason=payload.reason,
            )
        except InventoryNotFound as exc:
            raise PurchasingNotFound(str(exc)) from exc
        except (InventoryConflict, InsufficientStock) as exc:
            raise PurchasingConflict(str(exc)) from exc
        order_line.received_quantity = quantity(
            order_line.received_quantity - receipt_line.gross_quantity
        )
        order_line.received_weight_kg = quantity(
            order_line.received_weight_kg - receipt_line.gross_weight_kg
        )
        if order_line.received_quantity < 0 or order_line.received_weight_kg < 0:
            raise PurchasingConflict("عكس الاستلام سينتج كميات مستلمة سالبة")
        order_line.version += 1

    any_received = any(
        (
            line.received_quantity > 0
            if line.cost_basis == "quantity"
            else line.received_weight_kg > 0
        )
        for line in order_lines.values()
    )
    all_received = all(
        (line.received_quantity >= line.ordered_quantity)
        if line.cost_basis == "quantity"
        else (line.received_weight_kg >= line.ordered_weight_kg)
        for line in order_lines.values()
    )
    order.status = (
        "received" if all_received else "partially_received" if any_received else "approved"
    )
    order.version += 1
    receipt.status = "reversed"
    receipt.reversal_idempotency_key = idempotency_key
    receipt.reversed_by_id = actor.user.id
    receipt.reversed_at = datetime.now(UTC)
    receipt.reversal_reason = payload.reason.strip()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="purchasing.receipt.reverse",
        entity_type="purchase_receipt",
        entity_id=str(receipt.id),
        outcome="success",
        client=client,
        before_state={"status": "posted"},
        after_state={
            "status": receipt.status,
            "order_status": order.status,
            "reason": receipt.reversal_reason,
        },
    )
    db.flush()
    return _receipt_view(db, receipt)
