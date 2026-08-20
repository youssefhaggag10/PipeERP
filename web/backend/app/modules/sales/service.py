from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.common.decimal import money, quantity
from app.domain.sales.weight_card import calculate_weight_card
from app.domain.sales.weight_card import line as weight_line
from app.modules.identity.service import ClientContext, Principal, add_audit
from app.modules.inventory.schemas import IssueRequest, ReversalRequest
from app.modules.inventory.service import (
    InsufficientStock,
    InventoryConflict,
    post_exact_paired_issue,
    post_issue,
    reverse_transaction,
)
from app.modules.master_data.models import Partner, Product, UnitOfMeasure, Warehouse
from app.modules.master_data.service import allocate_document_number
from app.modules.sales.models import (
    CustomerInvoice,
    SalesDelivery,
    SalesDeliveryLine,
    SalesOrder,
    SalesOrderLine,
    SalesQuotation,
    SalesQuotationLine,
    SalesWeightCard,
    SalesWeightCardLine,
)
from app.modules.sales.schemas import (
    BillingMethod,
    CreatePieceOrderRequest,
    CreateQuotationRequest,
    CreateWeightSaleRequest,
    CustomerInvoiceView,
    PricingMode,
    QuotationLineView,
    QuotationView,
    SalesDeliveryLineView,
    SalesDeliveryView,
    SalesOption,
    SalesOptionsView,
    SalesOrderLineView,
    SalesOrderView,
    WeightCardLineView,
    WeightCardView,
    WeightMode,
)

WeightCardStatus = Literal["draft", "posted", "cancelled"]
DeliveryStatus = Literal["posted", "reversed"]
OrderStatus = Literal["draft", "delivered", "reversed", "cancelled"]
QuotationStatus = Literal["draft", "sent", "accepted", "rejected", "cancelled"]


class SalesError(Exception):
    pass


class SalesNotFound(SalesError):
    pass


class SalesConflict(SalesError):
    pass


def _delivery_hash(order_id: UUID, version: int) -> str:
    return sha256(f"{order_id}:{version}".encode()).hexdigest()


def _load_products(db: Session, product_ids: set[UUID]) -> dict[UUID, Product]:
    return {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_(product_ids)))
    }


def _invoice_view(invoice: CustomerInvoice | None) -> CustomerInvoiceView | None:
    return CustomerInvoiceView.model_validate(invoice) if invoice is not None else None


def _weight_card_view(db: Session, card: SalesWeightCard) -> WeightCardView:
    rows = list(
        db.scalars(
            select(SalesWeightCardLine)
            .where(SalesWeightCardLine.weight_card_id == card.id)
            .order_by(SalesWeightCardLine.created_at, SalesWeightCardLine.id)
        )
    )
    products = _load_products(db, {row.product_id for row in rows})
    return WeightCardView(
        id=card.id,
        card_number=card.card_number,
        card_date=card.card_date,
        vehicle_number=card.vehicle_number,
        gross_weight_kg=card.gross_weight_kg,
        tare_weight_kg=card.tare_weight_kg,
        net_weight_kg=card.net_weight_kg,
        weight_mode=cast(WeightMode, card.weight_mode),
        pricing_mode=cast(PricingMode, card.pricing_mode),
        uniform_price_per_kg=card.uniform_price_per_kg,
        subtotal=card.subtotal,
        use_vehicle_scale=card.use_vehicle_scale,
        status=cast(WeightCardStatus, card.status),
        notes=card.notes,
        lines=[
            WeightCardLineView(
                id=row.id,
                sales_order_line_id=row.sales_order_line_id,
                product_id=row.product_id,
                product_code=products[row.product_id].code,
                product_name_ar=products[row.product_id].name_ar,
                quantity_pieces=row.quantity_pieces,
                standard_weight_kg=row.standard_weight_kg,
                theoretical_weight_kg=row.theoretical_weight_kg,
                actual_weight_kg=row.actual_weight_kg,
                price_per_kg=row.price_per_kg,
                line_total=row.line_total,
                notes=row.notes,
            )
            for row in rows
        ],
    )


def _delivery_view(db: Session, delivery: SalesDelivery | None) -> SalesDeliveryView | None:
    if delivery is None:
        return None
    lines = list(
        db.scalars(
            select(SalesDeliveryLine)
            .where(SalesDeliveryLine.sales_delivery_id == delivery.id)
            .order_by(SalesDeliveryLine.created_at, SalesDeliveryLine.id)
        )
    )
    order_lines = {
        item.id: item
        for item in db.scalars(
            select(SalesOrderLine).where(
                SalesOrderLine.id.in_({line.sales_order_line_id for line in lines})
            )
        )
    }
    products = _load_products(db, {line.product_id for line in order_lines.values()})
    return SalesDeliveryView(
        id=delivery.id,
        delivery_number=delivery.delivery_number,
        sales_order_id=delivery.sales_order_id,
        status=cast(DeliveryStatus, delivery.status),
        posted_at=delivery.posted_at,
        reversed_at=delivery.reversed_at,
        reversal_reason=delivery.reversal_reason,
        lines=[
            SalesDeliveryLineView(
                id=line.id,
                sales_order_line_id=line.sales_order_line_id,
                inventory_transaction_id=line.inventory_transaction_id,
                product_code=products[order_lines[line.sales_order_line_id].product_id].code,
                product_name_ar=products[order_lines[line.sales_order_line_id].product_id].name_ar,
                quantity=line.quantity,
                weight_kg=line.weight_kg,
                cost_amount=line.cost_amount,
            )
            for line in lines
        ],
    )


def _order_view(db: Session, order: SalesOrder) -> SalesOrderView:
    customer = db.get(Partner, order.customer_id)
    warehouse = db.get(Warehouse, order.warehouse_id)
    if customer is None or warehouse is None:
        raise SalesNotFound("بيانات العميل أو المخزن المرتبطة بأمر البيع غير موجودة")
    lines = list(
        db.scalars(
            select(SalesOrderLine)
            .where(SalesOrderLine.sales_order_id == order.id)
            .order_by(SalesOrderLine.created_at, SalesOrderLine.id)
        )
    )
    products = _load_products(db, {line.product_id for line in lines})
    cards = list(
        db.scalars(
            select(SalesWeightCard)
            .where(SalesWeightCard.sales_order_id == order.id)
            .order_by(SalesWeightCard.card_date, SalesWeightCard.id)
        )
    )
    invoice = db.scalar(select(CustomerInvoice).where(CustomerInvoice.sales_order_id == order.id))
    delivery = db.scalar(select(SalesDelivery).where(SalesDelivery.sales_order_id == order.id))
    return SalesOrderView(
        id=order.id,
        order_number=order.order_number,
        customer_id=order.customer_id,
        customer_code=customer.code,
        customer_name_ar=customer.name_ar,
        warehouse_id=order.warehouse_id,
        warehouse_name_ar=warehouse.name_ar,
        billing_method=cast(BillingMethod, order.billing_method),
        status=cast(OrderStatus, order.status),
        order_date=order.order_date,
        notes=order.notes,
        subtotal=order.subtotal,
        discount_amount=order.discount_amount,
        transport_amount=order.transport_amount,
        tax_amount=order.tax_amount,
        total=order.total,
        version=order.version,
        lines=[
            SalesOrderLineView(
                id=item.id,
                product_id=item.product_id,
                product_code=products[item.product_id].code,
                product_name_ar=products[item.product_id].name_ar,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=item.unit_price,
                line_total=item.line_total,
                standard_weight_kg=item.standard_weight_kg,
                billing_weight_kg=item.billing_weight_kg,
                price_per_kg=item.price_per_kg,
                notes=item.notes,
            )
            for item in lines
        ],
        weight_cards=[_weight_card_view(db, card) for card in cards],
        invoice=_invoice_view(invoice),
        delivery=_delivery_view(db, delivery),
    )


def sales_options(db: Session) -> SalesOptionsView:
    customers = list(
        db.scalars(
            select(Partner)
            .where(Partner.is_active.is_(True), Partner.is_customer.is_(True))
            .order_by(Partner.code)
        )
    )
    warehouses = list(
        db.scalars(
            select(Warehouse)
            .where(Warehouse.is_active.is_(True))
            .order_by(Warehouse.is_default.desc(), Warehouse.code)
        )
    )
    products = list(
        db.scalars(
            select(Product)
            .where(Product.is_active.is_(True), Product.product_type == "finished_good")
            .order_by(Product.code)
        )
    )
    units = {
        item.id: item.symbol
        for item in db.scalars(
            select(UnitOfMeasure).where(
                UnitOfMeasure.id.in_({product.unit_id for product in products})
            )
        )
    }
    return SalesOptionsView(
        customers=[SalesOption(id=x.id, code=x.code, name_ar=x.name_ar) for x in customers],
        warehouses=[SalesOption(id=x.id, code=x.code, name_ar=x.name_ar) for x in warehouses],
        products=[
            SalesOption(
                id=x.id,
                code=x.code,
                name_ar=x.name_ar,
                standard_weight_kg=x.standard_weight_kg,
                unit_symbol=units.get(x.unit_id, ""),
            )
            for x in products
        ],
    )


def list_sales_orders(db: Session, *, limit: int = 100) -> list[SalesOrderView]:
    orders = list(
        db.scalars(select(SalesOrder).order_by(SalesOrder.order_date.desc()).limit(limit))
    )
    return [_order_view(db, order) for order in orders]


def get_sales_order(db: Session, order_id: UUID) -> SalesOrderView:
    order = db.get(SalesOrder, order_id)
    if order is None:
        raise SalesNotFound("أمر البيع غير موجود")
    return _order_view(db, order)


def get_delivery_billing_method(db: Session, delivery_id: UUID) -> BillingMethod:
    billing_method = db.scalar(
        select(SalesOrder.billing_method)
        .join(SalesDelivery, SalesDelivery.sales_order_id == SalesOrder.id)
        .where(SalesDelivery.id == delivery_id)
    )
    if billing_method is None:
        raise SalesNotFound("سند التسليم غير موجود")
    return cast(BillingMethod, billing_method)


def _validate_header(db: Session, customer_id: UUID, warehouse_id: UUID) -> None:
    customer = db.get(Partner, customer_id)
    if customer is None or not customer.is_active or not customer.is_customer:
        raise SalesNotFound("العميل غير موجود أو غير نشط")
    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None or not warehouse.is_active:
        raise SalesNotFound("المخزن غير موجود أو غير نشط")


def create_piece_order(
    db: Session,
    *,
    payload: CreatePieceOrderRequest,
    actor: Principal,
    client: ClientContext,
) -> SalesOrderView:
    _validate_header(db, payload.customer_id, payload.warehouse_id)
    products = _load_products(db, {line.product_id for line in payload.lines})
    if len(products) != len(payload.lines) or any(
        not product.is_active or product.product_type != "finished_good"
        for product in products.values()
    ):
        raise SalesNotFound("يوجد منتج غير موجود أو غير صالح للبيع")
    subtotal = sum((money(line.quantity * line.unit_price) for line in payload.lines), Decimal("0"))
    order = SalesOrder(
        order_number=allocate_document_number(db, "sales_order"),
        customer_id=payload.customer_id,
        warehouse_id=payload.warehouse_id,
        billing_method="piece",
        status="draft",
        notes=payload.notes.strip(),
        subtotal=money(subtotal),
        discount_amount=Decimal("0"),
        transport_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        total=money(subtotal),
        version=1,
        created_by_id=actor.user.id,
    )
    db.add(order)
    db.flush()
    for source in payload.lines:
        product = products[source.product_id]
        db.add(
            SalesOrderLine(
                sales_order_id=order.id,
                product_id=source.product_id,
                quantity=quantity(source.quantity),
                unit=source.unit.strip(),
                unit_price=source.unit_price,
                line_total=money(source.quantity * source.unit_price),
                standard_weight_kg=product.standard_weight_kg,
                billing_weight_kg=Decimal("0"),
                price_per_kg=Decimal("0"),
                notes=source.notes.strip(),
            )
        )
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="sales.order.create",
        entity_type="sales_order",
        entity_id=str(order.id),
        outcome="success",
        client=client,
        after_state={"order_number": order.order_number, "billing_method": "piece"},
    )
    db.flush()
    return _order_view(db, order)


def create_weight_sale(
    db: Session,
    *,
    payload: CreateWeightSaleRequest,
    actor: Principal,
    client: ClientContext,
) -> SalesOrderView:
    _validate_header(db, payload.customer_id, payload.warehouse_id)
    products = _load_products(db, {line.product_id for line in payload.lines})
    if len(products) != len(payload.lines) or any(
        not product.is_active or product.product_type != "finished_good"
        for product in products.values()
    ):
        raise SalesNotFound("يوجد منتج غير صالح للبيع بالوزن")
    total_actual_weight = (
        quantity(payload.gross_weight_kg - payload.tare_weight_kg)
        if payload.use_vehicle_scale
        else payload.total_actual_weight_kg
    )
    calculated = calculate_weight_card(
        lines=[
            weight_line(
                index,
                source.quantity,
                products[source.product_id].standard_weight_kg,
                actual_weight_kg=source.actual_weight_kg,
                price_per_kg=source.price_per_kg,
            )
            for index, source in enumerate(payload.lines)
        ],
        weight_mode=payload.weight_mode,
        pricing_mode=payload.pricing_mode,
        total_actual_weight_kg=total_actual_weight,
        uniform_price_per_kg=payload.uniform_price_per_kg,
    )
    if payload.use_vehicle_scale and payload.weight_mode == "per_line":
        scale_net = quantity(payload.gross_weight_kg - payload.tare_weight_kg)
        if abs(scale_net - calculated.total_weight_kg) > Decimal("0.001"):
            raise ValueError("مجموع أوزان البنود لا يساوي صافي وزن ميزان السيارة")
    total = money(
        calculated.subtotal
        - payload.discount_amount
        + payload.transport_amount
        + payload.tax_amount
    )
    if total < 0:
        raise ValueError("صافي الفاتورة لا يمكن أن يكون سالبًا")
    order = SalesOrder(
        order_number=allocate_document_number(db, "sales_order"),
        customer_id=payload.customer_id,
        warehouse_id=payload.warehouse_id,
        billing_method="weight",
        status="draft",
        notes=payload.notes.strip(),
        subtotal=calculated.subtotal,
        discount_amount=payload.discount_amount,
        transport_amount=payload.transport_amount,
        tax_amount=payload.tax_amount,
        total=total,
        version=1,
        created_by_id=actor.user.id,
    )
    db.add(order)
    db.flush()
    card = SalesWeightCard(
        sales_order_id=order.id,
        card_number=allocate_document_number(db, "weight_card"),
        vehicle_number=payload.vehicle_number.strip(),
        gross_weight_kg=payload.gross_weight_kg,
        tare_weight_kg=payload.tare_weight_kg,
        net_weight_kg=calculated.total_weight_kg,
        weight_mode=payload.weight_mode,
        pricing_mode=payload.pricing_mode,
        uniform_price_per_kg=payload.uniform_price_per_kg or Decimal("0"),
        subtotal=calculated.subtotal,
        use_vehicle_scale=payload.use_vehicle_scale,
        status="draft",
        notes=payload.notes.strip(),
    )
    db.add(card)
    db.flush()
    for source, priced in zip(payload.lines, calculated.lines, strict=True):
        effective_piece_price = quantity(priced.line_total / priced.pieces)
        order_line = SalesOrderLine(
            sales_order_id=order.id,
            product_id=source.product_id,
            quantity=priced.pieces,
            unit=source.unit.strip(),
            unit_price=effective_piece_price,
            line_total=priced.line_total,
            standard_weight_kg=priced.standard_weight_kg,
            billing_weight_kg=priced.allocated_weight_kg,
            price_per_kg=priced.price_per_kg,
            notes=source.notes.strip(),
        )
        db.add(order_line)
        db.flush()
        db.add(
            SalesWeightCardLine(
                weight_card_id=card.id,
                sales_order_line_id=order_line.id,
                product_id=source.product_id,
                quantity_pieces=priced.pieces,
                standard_weight_kg=priced.standard_weight_kg,
                theoretical_weight_kg=priced.theoretical_weight_kg,
                actual_weight_kg=priced.allocated_weight_kg,
                price_per_kg=priced.price_per_kg,
                line_total=priced.line_total,
                notes=source.notes.strip(),
            )
        )
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="sales.weight.create",
        entity_type="sales_order",
        entity_id=str(order.id),
        outcome="success",
        client=client,
        after_state={
            "order_number": order.order_number,
            "card_number": card.card_number,
            "net_weight_kg": str(card.net_weight_kg),
        },
    )
    db.flush()
    return _order_view(db, order)


def deliver_sales_order(
    db: Session,
    *,
    order_id: UUID,
    version: int,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> SalesOrderView:
    order = db.scalar(select(SalesOrder).where(SalesOrder.id == order_id).with_for_update())
    if order is None:
        raise SalesNotFound("أمر البيع غير موجود")
    request_hash = _delivery_hash(order_id, version)
    previous = db.scalar(
        select(SalesDelivery).where(SalesDelivery.idempotency_key == idempotency_key)
    )
    if previous is not None:
        if previous.sales_order_id != order_id or previous.request_hash != request_hash:
            raise SalesConflict("مفتاح منع التكرار مستخدم لتسليم مختلف")
        return _order_view(db, order)
    if order.status != "draft":
        raise SalesConflict("يمكن تسليم أمر بيع مسودة فقط")
    if order.version != version:
        raise SalesConflict("تغير أمر البيع؛ حدّث الصفحة ثم أعد المحاولة")
    lines = list(
        db.scalars(
            select(SalesOrderLine)
            .where(SalesOrderLine.sales_order_id == order.id)
            .order_by(SalesOrderLine.created_at, SalesOrderLine.id)
            .with_for_update()
        )
    )
    if not lines:
        raise SalesConflict("أمر البيع لا يحتوي على بنود")
    card = None
    weight_by_line: dict[UUID, SalesWeightCardLine] = {}
    if order.billing_method == "weight":
        card = db.scalar(
            select(SalesWeightCard)
            .where(
                SalesWeightCard.sales_order_id == order.id,
                SalesWeightCard.status == "draft",
            )
            .with_for_update()
        )
        if card is None:
            raise SalesConflict("كارتة الوزن غير موجودة أو تم إلغاؤها")
        weight_by_line = {
            item.sales_order_line_id: item
            for item in db.scalars(
                select(SalesWeightCardLine).where(SalesWeightCardLine.weight_card_id == card.id)
            )
        }
        if set(weight_by_line) != {line.id for line in lines}:
            raise SalesConflict("يجب استكمال وزن كل بنود الأمر قبل الاعتماد")

    delivery = SalesDelivery(
        delivery_number=allocate_document_number(db, "sales_delivery"),
        sales_order_id=order.id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status="posted",
        posted_by_id=actor.user.id,
        reversal_reason="",
    )
    db.add(delivery)
    db.flush()
    key_digest = sha256(idempotency_key.encode()).hexdigest()
    try:
        for index, order_line in enumerate(lines):
            child_key = f"sale-{key_digest}-{index}"
            if order.billing_method == "weight":
                weight_line_row = weight_by_line[order_line.id]
                transaction = post_exact_paired_issue(
                    db,
                    product_id=order_line.product_id,
                    warehouse_id=order.warehouse_id,
                    requested_quantity=order_line.quantity,
                    requested_weight_kg=weight_line_row.actual_weight_kg,
                    idempotency_key=child_key,
                    reference_type="sales_delivery",
                    reference_id=str(delivery.id),
                    reference_line_id=str(order_line.id),
                    notes=f"{order.order_number} / {card.card_number if card else ''}",
                    actor_user_id=actor.user.id,
                    client=client,
                )
            else:
                transaction = post_issue(
                    db,
                    payload=IssueRequest(
                        product_id=order_line.product_id,
                        warehouse_id=order.warehouse_id,
                        amount=order_line.quantity,
                        cost_basis="quantity",
                        reference_type="sales_delivery",
                        reference_id=str(delivery.id),
                        reference_line_id=str(order_line.id),
                        notes=order.order_number,
                    ),
                    idempotency_key=child_key,
                    actor_user_id=actor.user.id,
                    client=client,
                )
            db.add(
                SalesDeliveryLine(
                    sales_delivery_id=delivery.id,
                    sales_order_line_id=order_line.id,
                    inventory_transaction_id=transaction.id,
                    quantity=-transaction.quantity_delta,
                    weight_kg=-transaction.weight_delta_kg,
                    cost_amount=transaction.total_cost,
                )
            )
    except (InsufficientStock, InventoryConflict) as exc:
        raise SalesConflict(str(exc)) from exc
    order.status = "delivered"
    order.version += 1
    if card is not None:
        card.status = "posted"
    invoice = CustomerInvoice(
        invoice_number=allocate_document_number(db, "sales_invoice"),
        sales_order_id=order.id,
        customer_id=order.customer_id,
        invoice_type="weight" if order.billing_method == "weight" else "standard",
        status="posted",
        subtotal=order.subtotal,
        discount_amount=order.discount_amount,
        transport_amount=order.transport_amount,
        tax_amount=order.tax_amount,
        total=order.total,
        notes=order.notes,
        version=1,
    )
    db.add(invoice)
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="sales.delivery.post",
        entity_type="sales_delivery",
        entity_id=str(delivery.id),
        outcome="success",
        client=client,
        after_state={
            "delivery_number": delivery.delivery_number,
            "order_number": order.order_number,
            "invoice_number": invoice.invoice_number,
            "billing_method": order.billing_method,
        },
    )
    db.flush()
    return _order_view(db, order)


def cancel_sales_order(
    db: Session,
    *,
    order_id: UUID,
    version: int,
    reason: str,
    actor: Principal,
    client: ClientContext,
) -> SalesOrderView:
    order = db.scalar(select(SalesOrder).where(SalesOrder.id == order_id).with_for_update())
    if order is None:
        raise SalesNotFound("أمر البيع غير موجود")
    if order.status != "draft":
        raise SalesConflict("يمكن إلغاء أمر بيع مسودة فقط")
    if order.version != version:
        raise SalesConflict("تغير أمر البيع؛ حدّث الصفحة ثم أعد المحاولة")
    card = db.scalar(
        select(SalesWeightCard).where(SalesWeightCard.sales_order_id == order.id).with_for_update()
    )
    if card is not None:
        card.status = "cancelled"
    order.status = "cancelled"
    order.version += 1
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="sales.order.cancel",
        entity_type="sales_order",
        entity_id=str(order.id),
        outcome="success",
        client=client,
        after_state={
            "reason": reason.strip(),
            "order_number": order.order_number,
            "billing_method": order.billing_method,
        },
    )
    db.flush()
    return _order_view(db, order)


def reverse_sales_delivery(
    db: Session,
    *,
    delivery_id: UUID,
    reason: str,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> SalesOrderView:
    delivery = db.scalar(
        select(SalesDelivery).where(SalesDelivery.id == delivery_id).with_for_update()
    )
    if delivery is None:
        raise SalesNotFound("سند التسليم غير موجود")
    order = db.scalar(
        select(SalesOrder).where(SalesOrder.id == delivery.sales_order_id).with_for_update()
    )
    if order is None:
        raise SalesNotFound("أمر البيع المرتبط بالتسليم غير موجود")
    if delivery.status == "reversed":
        if delivery.reversal_idempotency_key == idempotency_key:
            return _order_view(db, order)
        raise SalesConflict("تم عكس سند التسليم من قبل")
    invoice = db.scalar(
        select(CustomerInvoice).where(CustomerInvoice.sales_order_id == order.id).with_for_update()
    )
    if invoice is None or invoice.status != "posted":
        raise SalesConflict("فاتورة العميل المرتبطة غير موجودة أو معكوسة")
    lines = list(
        db.scalars(
            select(SalesDeliveryLine).where(SalesDeliveryLine.sales_delivery_id == delivery.id)
        )
    )
    digest = sha256(idempotency_key.encode()).hexdigest()
    for index, item in enumerate(lines):
        try:
            reverse_transaction(
                db,
                transaction_id=item.inventory_transaction_id,
                payload=ReversalRequest(reason=reason),
                idempotency_key=f"sale-reversal-{digest}-{index}",
                actor_user_id=actor.user.id,
                client=client,
            )
        except (InsufficientStock, InventoryConflict) as exc:
            raise SalesConflict(str(exc)) from exc
    now = datetime.now(UTC)
    delivery.status = "reversed"
    delivery.reversal_idempotency_key = idempotency_key
    delivery.reversed_by_id = actor.user.id
    delivery.reversed_at = now
    delivery.reversal_reason = reason.strip()
    invoice.status = "reversed"
    invoice.reversed_at = now
    invoice.reversal_reason = reason.strip()
    invoice.version += 1
    order.status = "reversed"
    order.version += 1
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="sales.delivery.reverse",
        entity_type="sales_delivery",
        entity_id=str(delivery.id),
        outcome="success",
        client=client,
        after_state={"reason": reason.strip(), "order_status": order.status},
    )
    db.flush()
    return _order_view(db, order)


def _quotation_view(db: Session, quotation: SalesQuotation) -> QuotationView:
    customer = db.get(Partner, quotation.customer_id)
    if customer is None:
        raise SalesNotFound("عميل عرض السعر غير موجود")
    lines = list(
        db.scalars(
            select(SalesQuotationLine)
            .where(SalesQuotationLine.quotation_id == quotation.id)
            .order_by(SalesQuotationLine.created_at, SalesQuotationLine.id)
        )
    )
    return QuotationView(
        id=quotation.id,
        quotation_number=quotation.quotation_number,
        customer_id=quotation.customer_id,
        customer_code=customer.code,
        customer_name_ar=customer.name_ar,
        quotation_date=quotation.quotation_date,
        valid_until=quotation.valid_until,
        status=cast(QuotationStatus, quotation.status),
        total=quotation.total,
        notes=quotation.notes,
        version=quotation.version,
        lines=[QuotationLineView.model_validate(line) for line in lines],
    )


def create_quotation(
    db: Session,
    *,
    payload: CreateQuotationRequest,
    actor: Principal,
    client: ClientContext,
) -> QuotationView:
    customer = db.get(Partner, payload.customer_id)
    if customer is None or not customer.is_customer or not customer.is_active:
        raise SalesNotFound("العميل غير موجود أو غير نشط")
    referenced = {line.product_id for line in payload.lines if line.product_id is not None}
    if referenced and len(_load_products(db, referenced)) != len(referenced):
        raise SalesNotFound("يوجد منتج غير موجود في عرض السعر")
    total = sum((money(line.quantity * line.unit_price) for line in payload.lines), Decimal("0"))
    quotation = SalesQuotation(
        quotation_number=allocate_document_number(db, "sales_quotation"),
        customer_id=payload.customer_id,
        valid_until=payload.valid_until,
        status="draft",
        total=money(total),
        notes=payload.notes.strip(),
        version=1,
        created_by_id=actor.user.id,
    )
    db.add(quotation)
    db.flush()
    for source in payload.lines:
        db.add(
            SalesQuotationLine(
                quotation_id=quotation.id,
                product_id=source.product_id,
                item_name=source.item_name.strip(),
                quantity=quantity(source.quantity),
                unit=source.unit.strip(),
                unit_price=source.unit_price,
                line_total=money(source.quantity * source.unit_price),
                notes=source.notes.strip(),
            )
        )
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="sales.quotation.create",
        entity_type="sales_quotation",
        entity_id=str(quotation.id),
        outcome="success",
        client=client,
        after_state={"quotation_number": quotation.quotation_number, "total": str(total)},
    )
    db.flush()
    return _quotation_view(db, quotation)


def list_quotations(db: Session, *, limit: int = 100) -> list[QuotationView]:
    rows = list(
        db.scalars(
            select(SalesQuotation).order_by(SalesQuotation.quotation_date.desc()).limit(limit)
        )
    )
    return [_quotation_view(db, row) for row in rows]
