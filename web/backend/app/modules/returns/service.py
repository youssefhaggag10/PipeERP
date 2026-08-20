from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.common.decimal import money, quantity
from app.modules.identity.service import ClientContext, Principal, add_audit
from app.modules.inventory.schemas import IssueRequest, ReceiptRequest
from app.modules.inventory.service import (
    post_issue,
    post_receipt,
    reverse_purchase_return_inventory,
    reverse_sales_return_inventory,
)
from app.modules.master_data.models import Partner, Product, Warehouse
from app.modules.master_data.service import allocate_document_number
from app.modules.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    SupplierInvoice,
)
from app.modules.returns.models import InvoiceReturn, InvoiceReturnLine, ReturnRefund
from app.modules.returns.schemas import (
    CreateInvoiceReturnRequest,
    CreateRefundRequest,
    InvoiceReturnLineView,
    InvoiceReturnView,
    RefundView,
    ReturnableInvoiceView,
    ReturnableLineView,
    ReturnOptionsView,
    ReverseRequest,
)
from app.modules.sales.models import (
    CustomerInvoice,
    SalesDelivery,
    SalesDeliveryLine,
    SalesOrder,
    SalesOrderLine,
)
from app.modules.treasury.models import FinancialAccount, PaymentAllocation, PaymentTransaction

ZERO = Decimal("0")
PAYMENT_ACCOUNT_TYPES = {
    "cash": "cash",
    "bank_transfer": "bank",
    "cheque": "bank",
    "wallet": "wallet",
}


class ReturnsError(Exception):
    pass


class ReturnsNotFound(ReturnsError):
    pass


class ReturnsConflict(ReturnsError):
    pass


def _hash(payload: BaseModel) -> str:
    return sha256(payload.model_dump_json().encode()).hexdigest()


def _derived_key(key: str, value: UUID, suffix: str) -> str:
    return f"ret-{sha256(key.encode()).hexdigest()[:24]}-{str(value)[:12]}-{suffix}"


def _active_return_total(
    db: Session, *, return_type: str, invoice_id: UUID
) -> Decimal:
    column = (
        InvoiceReturn.customer_invoice_id
        if return_type == "sales"
        else InvoiceReturn.supplier_invoice_id
    )
    value = db.scalar(
        select(func.coalesce(func.sum(InvoiceReturn.total), 0)).where(
            column == invoice_id,
            InvoiceReturn.status == "posted",
        )
    )
    return money(Decimal(str(value or 0)))


def _paid_total(db: Session, *, return_type: str, invoice_id: UUID) -> Decimal:
    column = (
        PaymentAllocation.customer_invoice_id
        if return_type == "sales"
        else PaymentAllocation.supplier_invoice_id
    )
    value = db.scalar(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .join(
            PaymentTransaction,
            PaymentTransaction.id == PaymentAllocation.payment_transaction_id,
        )
        .where(column == invoice_id, PaymentTransaction.status == "posted")
    )
    return money(Decimal(str(value or 0)))


def _refunded_total(db: Session, *, return_type: str, invoice_id: UUID) -> Decimal:
    column = (
        ReturnRefund.customer_invoice_id
        if return_type == "sales"
        else ReturnRefund.supplier_invoice_id
    )
    value = db.scalar(
        select(func.coalesce(func.sum(ReturnRefund.amount), 0)).where(
            column == invoice_id,
            ReturnRefund.status == "posted",
        )
    )
    return money(Decimal(str(value or 0)))


def invoice_net_amounts(
    db: Session, *, return_type: str, invoice_id: UUID, original_total: Decimal
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    returned = _active_return_total(db, return_type=return_type, invoice_id=invoice_id)
    paid = _paid_total(db, return_type=return_type, invoice_id=invoice_id)
    refunded = _refunded_total(db, return_type=return_type, invoice_id=invoice_id)
    net = money(max(ZERO, original_total - returned))
    effective_paid = money(max(ZERO, paid - refunded))
    remaining = money(max(ZERO, net - effective_paid))
    refundable = money(max(ZERO, paid - net - refunded))
    return returned, paid, refunded, remaining, refundable


def list_returnable_invoices(
    db: Session, *, return_type: str, partner_id: UUID | None = None
) -> list[ReturnableInvoiceView]:
    result: list[ReturnableInvoiceView] = []
    if return_type == "sales":
        sales_statement = (
            select(CustomerInvoice, SalesOrder, Partner)
            .join(SalesOrder, SalesOrder.id == CustomerInvoice.sales_order_id)
            .join(Partner, Partner.id == CustomerInvoice.customer_id)
            .where(CustomerInvoice.status == "posted")
            .order_by(CustomerInvoice.invoice_date.desc(), CustomerInvoice.id.desc())
        )
        if partner_id is not None:
            sales_statement = sales_statement.where(CustomerInvoice.customer_id == partner_id)
        rows = db.execute(sales_statement)
        for invoice, order, partner in rows:
            returned, paid, refunded, remaining, refundable = invoice_net_amounts(
                db,
                return_type="sales",
                invoice_id=invoice.id,
                original_total=invoice.total,
            )
            net = money(max(ZERO, invoice.total - returned))
            result.append(
                ReturnableInvoiceView(
                    id=invoice.id,
                    invoice_number=invoice.invoice_number,
                    invoice_type="sales",
                    invoice_date=invoice.invoice_date,
                    order_number=order.order_number,
                    partner_id=partner.id,
                    partner_name_ar=partner.name_ar,
                    original_total=invoice.total,
                    returned_total=returned,
                    net_total=net,
                    paid=paid,
                    refunded=refunded,
                    remaining=remaining,
                    refundable=refundable,
                    return_status=(
                        "none" if returned == 0 else "full" if net == 0 else "partial"
                    ),
                )
            )
    elif return_type == "purchase":
        purchase_statement = (
            select(SupplierInvoice, PurchaseOrder, Partner)
            .join(PurchaseOrder, PurchaseOrder.id == SupplierInvoice.purchase_order_id)
            .join(Partner, Partner.id == SupplierInvoice.supplier_id)
            .where(SupplierInvoice.status == "posted")
            .order_by(SupplierInvoice.posted_at.desc(), SupplierInvoice.id.desc())
        )
        if partner_id is not None:
            purchase_statement = purchase_statement.where(
                SupplierInvoice.supplier_id == partner_id
            )
        rows = db.execute(purchase_statement)
        for invoice, order, partner in rows:
            returned, paid, refunded, remaining, refundable = invoice_net_amounts(
                db,
                return_type="purchase",
                invoice_id=invoice.id,
                original_total=invoice.total,
            )
            net = money(max(ZERO, invoice.total - returned))
            result.append(
                ReturnableInvoiceView(
                    id=invoice.id,
                    invoice_number=invoice.invoice_number,
                    invoice_type="purchase",
                    invoice_date=invoice.posted_at or invoice.created_at,
                    order_number=order.order_number,
                    partner_id=partner.id,
                    partner_name_ar=partner.name_ar,
                    original_total=invoice.total,
                    returned_total=returned,
                    net_total=net,
                    paid=paid,
                    refunded=refunded,
                    remaining=remaining,
                    refundable=refundable,
                    return_status=(
                        "none" if returned == 0 else "full" if net == 0 else "partial"
                    ),
                )
            )
    else:
        raise ValueError("نوع الفاتورة غير صحيح")
    return result


def _returned_line_amounts(
    db: Session, *, return_type: str, source_line_id: UUID
) -> tuple[Decimal, Decimal]:
    source_column = (
        InvoiceReturnLine.sales_order_line_id
        if return_type == "sales"
        else InvoiceReturnLine.purchase_order_line_id
    )
    row = db.execute(
        select(
            func.coalesce(func.sum(InvoiceReturnLine.quantity), 0),
            func.coalesce(func.sum(InvoiceReturnLine.weight_kg), 0),
        )
        .join(InvoiceReturn, InvoiceReturn.id == InvoiceReturnLine.invoice_return_id)
        .where(source_column == source_line_id, InvoiceReturn.status == "posted")
    ).one()
    return quantity(Decimal(str(row[0] or 0))), quantity(Decimal(str(row[1] or 0)))


def get_returnable_lines(
    db: Session, *, return_type: str, invoice_id: UUID
) -> list[ReturnableLineView]:
    result: list[ReturnableLineView] = []
    if return_type == "sales":
        invoice = db.get(CustomerInvoice, invoice_id)
        if invoice is None or invoice.status != "posted":
            raise ReturnsNotFound("فاتورة المبيعات غير موجودة أو غير معتمدة")
        rows = db.execute(
            select(SalesOrderLine, SalesDeliveryLine, Product)
            .join(Product, Product.id == SalesOrderLine.product_id)
            .join(
                SalesDeliveryLine,
                SalesDeliveryLine.sales_order_line_id == SalesOrderLine.id,
            )
            .join(
                SalesDelivery,
                (SalesDelivery.id == SalesDeliveryLine.sales_delivery_id)
                & (SalesDelivery.status == "posted"),
            )
            .where(SalesOrderLine.sales_order_id == invoice.sales_order_id)
            .order_by(SalesOrderLine.created_at, SalesOrderLine.id)
        )
        for line, delivery_line, product in rows:
            returned_quantity, returned_weight = _returned_line_amounts(
                db, return_type="sales", source_line_id=line.id
            )
            result.append(
                ReturnableLineView(
                    source_line_id=line.id,
                    product_id=line.product_id,
                    product_code=product.code,
                    product_name_ar=product.name_ar,
                    unit=line.unit,
                    unit_price=line.unit_price,
                    cost_basis="weight" if delivery_line.weight_kg > 0 else "quantity",
                    original_quantity=delivery_line.quantity,
                    returned_quantity=returned_quantity,
                    remaining_quantity=quantity(delivery_line.quantity - returned_quantity),
                    original_weight_kg=delivery_line.weight_kg,
                    returned_weight_kg=returned_weight,
                    remaining_weight_kg=quantity(delivery_line.weight_kg - returned_weight),
                )
            )
    elif return_type == "purchase":
        purchase_invoice = db.get(SupplierInvoice, invoice_id)
        if purchase_invoice is None or purchase_invoice.status != "posted":
            raise ReturnsNotFound("فاتورة المشتريات غير موجودة أو غير معتمدة")
        lines = list(
            db.scalars(
                select(PurchaseOrderLine)
                .where(PurchaseOrderLine.purchase_order_id == purchase_invoice.purchase_order_id)
                .order_by(PurchaseOrderLine.created_at, PurchaseOrderLine.id)
            )
        )
        products = {
            item.id: item
            for item in db.scalars(
                select(Product).where(Product.id.in_({line.product_id for line in lines}))
            )
        }
        for line in lines:
            received = db.execute(
                select(
                    func.coalesce(func.sum(PurchaseReceiptLine.net_quantity), 0),
                    func.coalesce(func.sum(PurchaseReceiptLine.net_weight_kg), 0),
                )
                .join(
                    PurchaseReceipt,
                    PurchaseReceipt.id == PurchaseReceiptLine.purchase_receipt_id,
                )
                .where(
                    PurchaseReceiptLine.purchase_order_line_id == line.id,
                    PurchaseReceipt.status == "posted",
                )
            ).one()
            original_quantity = quantity(Decimal(str(received[0] or 0)))
            original_weight = quantity(Decimal(str(received[1] or 0)))
            returned_quantity, returned_weight = _returned_line_amounts(
                db, return_type="purchase", source_line_id=line.id
            )
            product = products[line.product_id]
            result.append(
                ReturnableLineView(
                    source_line_id=line.id,
                    product_id=line.product_id,
                    product_code=product.code,
                    product_name_ar=product.name_ar,
                    unit="كجم" if line.cost_basis == "weight" else "وحدة",
                    unit_price=line.unit_price,
                    cost_basis=cast(Literal["quantity", "weight"], line.cost_basis),
                    original_quantity=original_quantity,
                    returned_quantity=returned_quantity,
                    remaining_quantity=quantity(original_quantity - returned_quantity),
                    original_weight_kg=original_weight,
                    returned_weight_kg=returned_weight,
                    remaining_weight_kg=quantity(original_weight - returned_weight),
                )
            )
    else:
        raise ValueError("نوع الفاتورة غير صحيح")
    return result


def _return_view(db: Session, item: InvoiceReturn) -> InvoiceReturnView:
    partner = db.get(Partner, item.partner_id)
    warehouse = db.get(Warehouse, item.warehouse_id)
    invoice: CustomerInvoice | SupplierInvoice | None = (
        db.get(CustomerInvoice, item.customer_invoice_id)
        if item.customer_invoice_id
        else db.get(SupplierInvoice, item.supplier_invoice_id)
    )
    if partner is None or warehouse is None or invoice is None:
        raise ReturnsNotFound("تعذر تحميل بيانات مستند المرتجع")
    lines = list(
        db.scalars(
            select(InvoiceReturnLine)
            .where(InvoiceReturnLine.invoice_return_id == item.id)
            .order_by(InvoiceReturnLine.created_at, InvoiceReturnLine.id)
        )
    )
    products = {
        product.id: product
        for product in db.scalars(
            select(Product).where(Product.id.in_({line.product_id for line in lines}))
        )
    }
    return InvoiceReturnView(
        id=item.id,
        return_number=item.return_number,
        return_type=cast(Literal["sales", "purchase"], item.return_type),
        invoice_id=invoice.id,
        invoice_number=invoice.invoice_number,
        partner_id=partner.id,
        partner_name_ar=partner.name_ar,
        warehouse_id=warehouse.id,
        warehouse_name_ar=warehouse.name_ar,
        return_date=item.return_date,
        total=item.total,
        reason=item.reason,
        status=cast(Literal["posted", "reversed"], item.status),
        reversal_reason=item.reversal_reason,
        version=item.version,
        lines=[
            InvoiceReturnLineView(
                id=line.id,
                source_line_id=cast(UUID, line.sales_order_line_id or line.purchase_order_line_id),
                product_id=line.product_id,
                product_code=products[line.product_id].code,
                product_name_ar=products[line.product_id].name_ar,
                quantity=line.quantity,
                weight_kg=line.weight_kg,
                cost_basis=cast(Literal["quantity", "weight"], line.cost_basis),
                unit=line.unit,
                unit_price=line.unit_price,
                line_total=line.line_total,
                inventory_cost=line.inventory_cost,
            )
            for line in lines
        ],
    )


def list_returns(db: Session, *, limit: int = 250) -> list[InvoiceReturnView]:
    rows = db.scalars(
        select(InvoiceReturn)
        .order_by(InvoiceReturn.return_date.desc(), InvoiceReturn.id.desc())
        .limit(limit)
    )
    return [_return_view(db, item) for item in rows]


def create_return(
    db: Session,
    *,
    payload: CreateInvoiceReturnRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> InvoiceReturnView:
    digest = _hash(payload)
    previous = db.scalar(
        select(InvoiceReturn).where(InvoiceReturn.idempotency_key == idempotency_key)
    )
    if previous is not None:
        if previous.request_hash != digest:
            raise ReturnsConflict("مفتاح منع التكرار مستخدم لمرتجع مختلف")
        return _return_view(db, previous)
    order: SalesOrder | PurchaseOrder | None
    if payload.return_type == "sales":
        sales_invoice = db.scalar(
            select(CustomerInvoice)
            .where(CustomerInvoice.id == payload.invoice_id)
            .with_for_update()
        )
        if sales_invoice is None or sales_invoice.status != "posted":
            raise ReturnsNotFound("فاتورة المبيعات غير موجودة أو غير معتمدة")
        order = db.get(SalesOrder, sales_invoice.sales_order_id)
        partner_id = sales_invoice.customer_id
        customer_invoice_id, supplier_invoice_id = sales_invoice.id, None
        prefix = "sales_return"
    else:
        supplier_invoice = db.scalar(
            select(SupplierInvoice)
            .where(SupplierInvoice.id == payload.invoice_id)
            .with_for_update()
        )
        if supplier_invoice is None or supplier_invoice.status != "posted":
            raise ReturnsNotFound("فاتورة المشتريات غير موجودة أو غير معتمدة")
        order = db.get(PurchaseOrder, supplier_invoice.purchase_order_id)
        partner_id = supplier_invoice.supplier_id
        customer_invoice_id, supplier_invoice_id = None, supplier_invoice.id
        prefix = "purchase_return"
    if order is None:
        raise ReturnsNotFound("أمر الفاتورة غير موجود")
    available = {
        line.source_line_id: line
        for line in get_returnable_lines(
            db, return_type=payload.return_type, invoice_id=payload.invoice_id
        )
    }
    prepared: list[tuple[ReturnableLineView, Decimal, Decimal, Decimal]] = []
    total = ZERO
    for request_line in payload.lines:
        source = available.get(request_line.source_line_id)
        if source is None:
            raise ReturnsConflict("أحد بنود المرتجع لا يخص الفاتورة")
        if payload.return_type == "sales":
            if request_line.quantity > source.remaining_quantity:
                raise ReturnsConflict(f"كمية مرتجع {source.product_name_ar} تتجاوز المتاح")
            returned_quantity = quantity(request_line.quantity)
            returned_weight = quantity(
                source.original_weight_kg * returned_quantity / source.original_quantity
            ) if source.original_weight_kg > 0 else ZERO
            basis_amount = returned_quantity
        elif source.cost_basis == "weight":
            if request_line.weight_kg > source.remaining_weight_kg:
                raise ReturnsConflict(f"وزن مرتجع {source.product_name_ar} يتجاوز المتاح")
            returned_weight = quantity(request_line.weight_kg)
            returned_quantity = quantity(
                source.original_quantity * returned_weight / source.original_weight_kg
            ) if source.original_weight_kg > 0 else ZERO
            basis_amount = returned_weight
        else:
            if request_line.quantity > source.remaining_quantity:
                raise ReturnsConflict(f"كمية مرتجع {source.product_name_ar} تتجاوز المتاح")
            returned_quantity = quantity(request_line.quantity)
            returned_weight = quantity(
                source.original_weight_kg * returned_quantity / source.original_quantity
            ) if source.original_weight_kg > 0 else ZERO
            basis_amount = returned_quantity
        line_total = money(basis_amount * source.unit_price)
        total += line_total
        prepared.append((source, returned_quantity, returned_weight, line_total))
    total = money(total)
    if total <= 0:
        raise ReturnsConflict("إجمالي المرتجع يجب أن يكون أكبر من صفر")
    document = InvoiceReturn(
        return_number=allocate_document_number(db, prefix),
        return_type=payload.return_type,
        customer_invoice_id=customer_invoice_id,
        supplier_invoice_id=supplier_invoice_id,
        partner_id=partner_id,
        warehouse_id=order.warehouse_id,
        total=total,
        reason=payload.reason.strip(),
        status="posted",
        idempotency_key=idempotency_key,
        request_hash=digest,
        posted_by_id=actor.user.id,
        reversal_reason="",
        version=1,
    )
    db.add(document)
    db.flush()
    for source, returned_quantity, returned_weight, line_total in prepared:
        if payload.return_type == "sales":
            delivery_line = db.scalar(
                select(SalesDeliveryLine).where(
                    SalesDeliveryLine.sales_order_line_id == source.source_line_id
                )
            )
            if delivery_line is None:
                raise ReturnsNotFound("حركة تسليم بند المبيعات غير موجودة")
            basis: Literal["quantity", "weight"] = (
                "weight" if delivery_line.weight_kg > 0 else "quantity"
            )
            original_basis = (
                delivery_line.weight_kg if basis == "weight" else delivery_line.quantity
            )
            unit_cost = quantity(delivery_line.cost_amount / original_basis)
            transaction = post_receipt(
                db,
                payload=ReceiptRequest(
                    product_id=source.product_id,
                    warehouse_id=order.warehouse_id,
                    quantity=returned_quantity,
                    weight_kg=returned_weight,
                    cost_basis=basis,
                    unit_cost=unit_cost,
                    lot_number=f"RET-{document.return_number}-{source.product_code}",
                    reference_type="sales_return",
                    reference_id=str(document.id),
                    reference_line_id=str(source.source_line_id),
                    notes=f"{document.return_number} — {document.reason}",
                ),
                idempotency_key=_derived_key(idempotency_key, source.source_line_id, "in"),
                actor_user_id=actor.user.id,
                client=client,
                transaction_type="return_in",
            )
        else:
            basis = source.cost_basis
            amount = returned_weight if basis == "weight" else returned_quantity
            transaction = post_issue(
                db,
                payload=IssueRequest(
                    product_id=source.product_id,
                    warehouse_id=order.warehouse_id,
                    amount=amount,
                    cost_basis=basis,
                    reference_type="purchase_return",
                    reference_id=str(document.id),
                    reference_line_id=str(source.source_line_id),
                    notes=f"{document.return_number} — {document.reason}",
                ),
                idempotency_key=_derived_key(idempotency_key, source.source_line_id, "out"),
                actor_user_id=actor.user.id,
                client=client,
                transaction_type="return_out",
            )
        db.add(
            InvoiceReturnLine(
                invoice_return_id=document.id,
                sales_order_line_id=(
                    source.source_line_id if payload.return_type == "sales" else None
                ),
                purchase_order_line_id=(
                    source.source_line_id if payload.return_type == "purchase" else None
                ),
                product_id=source.product_id,
                inventory_transaction_id=transaction.id,
                quantity=returned_quantity,
                weight_kg=returned_weight,
                cost_basis=basis,
                unit=source.unit,
                unit_price=source.unit_price,
                line_total=line_total,
                inventory_cost=transaction.total_cost,
            )
        )
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type=f"returns.{payload.return_type}.post",
        entity_type="invoice_return",
        entity_id=str(document.id),
        outcome="success",
        client=client,
        after_state={"return_number": document.return_number, "total": str(total)},
    )
    db.flush()
    return _return_view(db, document)


def reverse_return(
    db: Session,
    *,
    return_id: UUID,
    payload: ReverseRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> InvoiceReturnView:
    document = db.scalar(
        select(InvoiceReturn).where(InvoiceReturn.id == return_id).with_for_update()
    )
    if document is None:
        raise ReturnsNotFound("مستند المرتجع غير موجود")
    if document.reversal_idempotency_key == idempotency_key:
        return _return_view(db, document)
    if document.status != "posted":
        raise ReturnsConflict("تم عكس مستند المرتجع بالفعل")
    if document.version != payload.version:
        raise ReturnsConflict("تغير مستند المرتجع؛ حدّث الصفحة")
    if _refunded_total(
        db,
        return_type=document.return_type,
        invoice_id=cast(UUID, document.customer_invoice_id or document.supplier_invoice_id),
    ) > 0:
        raise ReturnsConflict("اعكس استردادات الفاتورة أولًا قبل عكس المرتجع")
    lines = list(
        db.scalars(
            select(InvoiceReturnLine)
            .where(InvoiceReturnLine.invoice_return_id == document.id)
            .order_by(InvoiceReturnLine.id)
            .with_for_update()
        )
    )
    for line in lines:
        if document.return_type == "sales":
            reversed_transaction = reverse_sales_return_inventory(
                db,
                transaction_id=line.inventory_transaction_id,
                sales_return_id=document.id,
                sales_order_line_id=cast(UUID, line.sales_order_line_id),
                idempotency_key=_derived_key(idempotency_key, line.id, "reverse"),
                actor_user_id=actor.user.id,
                client=client,
                reason=payload.reason,
            )
        else:
            reversed_transaction = reverse_purchase_return_inventory(
                db,
                transaction_id=line.inventory_transaction_id,
                purchase_return_id=document.id,
                purchase_order_line_id=cast(UUID, line.purchase_order_line_id),
                idempotency_key=_derived_key(idempotency_key, line.id, "reverse"),
                actor_user_id=actor.user.id,
                client=client,
                reason=payload.reason,
            )
        line.reversal_inventory_transaction_id = reversed_transaction.id
    document.status = "reversed"
    document.reversed_by_id = actor.user.id
    document.reversed_at = datetime.now(UTC)
    document.reversal_reason = payload.reason.strip()
    document.reversal_idempotency_key = idempotency_key
    document.version += 1
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="returns.document.reverse",
        entity_type="invoice_return",
        entity_id=str(document.id),
        outcome="success",
        client=client,
    )
    db.flush()
    return _return_view(db, document)


def _refund_view(db: Session, item: ReturnRefund) -> RefundView:
    partner = db.get(Partner, item.partner_id)
    account = db.get(FinancialAccount, item.financial_account_id)
    invoice: CustomerInvoice | SupplierInvoice | None = (
        db.get(CustomerInvoice, item.customer_invoice_id)
        if item.customer_invoice_id
        else db.get(SupplierInvoice, item.supplier_invoice_id)
    )
    if partner is None or account is None or invoice is None:
        raise ReturnsNotFound("تعذر تحميل بيانات الاسترداد")
    return RefundView(
        id=item.id,
        refund_number=item.refund_number,
        refund_type=cast(
            Literal["customer_refund", "supplier_refund"], item.refund_type
        ),
        invoice_id=invoice.id,
        invoice_number=invoice.invoice_number,
        partner_id=partner.id,
        partner_name_ar=partner.name_ar,
        financial_account_id=account.id,
        financial_account_name_ar=account.name_ar,
        refund_date=item.refund_date,
        amount=item.amount,
        payment_method=cast(
            Literal["cash", "bank_transfer", "cheque", "wallet"],
            item.payment_method,
        ),
        notes=item.notes,
        status=cast(Literal["posted", "reversed"], item.status),
        reversal_reason=item.reversal_reason,
        version=item.version,
    )


def list_refunds(db: Session, *, limit: int = 250) -> list[RefundView]:
    rows = db.scalars(
        select(ReturnRefund)
        .order_by(ReturnRefund.refund_date.desc(), ReturnRefund.id.desc())
        .limit(limit)
    )
    return [_refund_view(db, item) for item in rows]


def create_refund(
    db: Session,
    *,
    payload: CreateRefundRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> RefundView:
    digest = _hash(payload)
    previous = db.scalar(
        select(ReturnRefund).where(ReturnRefund.idempotency_key == idempotency_key)
    )
    if previous is not None:
        if previous.request_hash != digest:
            raise ReturnsConflict("مفتاح منع التكرار مستخدم لاسترداد مختلف")
        return _refund_view(db, previous)
    return_type = "sales" if payload.refund_type == "customer_refund" else "purchase"
    if return_type == "sales":
        sales_invoice = db.scalar(
            select(CustomerInvoice)
            .where(CustomerInvoice.id == payload.invoice_id)
            .with_for_update()
        )
        if sales_invoice is None or sales_invoice.status != "posted":
            raise ReturnsNotFound("فاتورة المبيعات غير موجودة أو غير معتمدة")
        partner_id = sales_invoice.customer_id
        customer_invoice_id, supplier_invoice_id = sales_invoice.id, None
        invoice_id = sales_invoice.id
        original_total = sales_invoice.total
    else:
        supplier_invoice = db.scalar(
            select(SupplierInvoice)
            .where(SupplierInvoice.id == payload.invoice_id)
            .with_for_update()
        )
        if supplier_invoice is None or supplier_invoice.status != "posted":
            raise ReturnsNotFound("فاتورة المشتريات غير موجودة أو غير معتمدة")
        partner_id = supplier_invoice.supplier_id
        customer_invoice_id, supplier_invoice_id = None, supplier_invoice.id
        invoice_id = supplier_invoice.id
        original_total = supplier_invoice.total
    _, _, _, _, refundable = invoice_net_amounts(
        db,
        return_type=return_type,
        invoice_id=invoice_id,
        original_total=original_total,
    )
    amount = money(payload.amount)
    if amount > refundable:
        raise ReturnsConflict(f"المبلغ أكبر من المتاح للاسترداد ({refundable:,.2f})")
    account = db.scalar(
        select(FinancialAccount)
        .where(FinancialAccount.id == payload.financial_account_id)
        .with_for_update()
    )
    if account is None or not account.is_active:
        raise ReturnsNotFound("الحساب المالي غير موجود أو غير نشط")
    if PAYMENT_ACCOUNT_TYPES[payload.payment_method] != account.account_type:
        raise ReturnsConflict("طريقة الدفع لا تتوافق مع نوع الحساب المالي")
    item = ReturnRefund(
        refund_number=allocate_document_number(db, payload.refund_type),
        refund_type=payload.refund_type,
        customer_invoice_id=customer_invoice_id,
        supplier_invoice_id=supplier_invoice_id,
        partner_id=partner_id,
        financial_account_id=account.id,
        amount=amount,
        payment_method=payload.payment_method,
        notes=payload.notes.strip(),
        status="posted",
        idempotency_key=idempotency_key,
        request_hash=digest,
        posted_by_id=actor.user.id,
        reversal_reason="",
        version=1,
    )
    db.add(item)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type=f"returns.{payload.refund_type}.post",
        entity_type="return_refund",
        entity_id=str(item.id),
        outcome="success",
        client=client,
        after_state={"refund_number": item.refund_number, "amount": str(amount)},
    )
    return _refund_view(db, item)


def reverse_refund(
    db: Session,
    *,
    refund_id: UUID,
    payload: ReverseRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> RefundView:
    item = db.scalar(select(ReturnRefund).where(ReturnRefund.id == refund_id).with_for_update())
    if item is None:
        raise ReturnsNotFound("حركة الاسترداد غير موجودة")
    if item.reversal_idempotency_key == idempotency_key:
        return _refund_view(db, item)
    if item.status != "posted":
        raise ReturnsConflict("تم عكس حركة الاسترداد بالفعل")
    if item.version != payload.version:
        raise ReturnsConflict("تغيرت حركة الاسترداد؛ حدّث الصفحة")
    item.status = "reversed"
    item.reversed_by_id = actor.user.id
    item.reversed_at = datetime.now(UTC)
    item.reversal_reason = payload.reason.strip()
    item.reversal_idempotency_key = idempotency_key
    item.version += 1
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="returns.refund.reverse",
        entity_type="return_refund",
        entity_id=str(item.id),
        outcome="success",
        client=client,
    )
    db.flush()
    return _refund_view(db, item)


def return_options(db: Session) -> ReturnOptionsView:
    accounts = db.scalars(
        select(FinancialAccount)
        .where(FinancialAccount.is_active.is_(True))
        .order_by(FinancialAccount.is_default.desc(), FinancialAccount.name_ar)
    )
    return ReturnOptionsView(
        accounts=[
            {
                "id": str(item.id),
                "code": item.code,
                "name_ar": item.name_ar,
                "type": item.account_type,
            }
            for item in accounts
        ]
    )
