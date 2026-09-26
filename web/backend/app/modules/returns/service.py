from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.common.decimal import money, quantity
from app.modules.identity.service import ClientContext, Principal, add_audit
from app.modules.inventory.models import (
    InventoryAllocation,
    InventoryLayer,
    InventoryLot,
    InventoryTransaction,
)
from app.modules.inventory.schemas import ReceiptRequest
from app.modules.inventory.service import (
    lock_inventory_contexts,
    post_exact_layer_issue,
    post_receipt,
    receipt_layer_for_transaction,
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
from app.modules.returns.models import (
    InvoiceReturn,
    InvoiceReturnLine,
    InvoiceReturnSource,
    ReturnRefund,
)
from app.modules.returns.schemas import (
    CreateInvoiceReturnRequest,
    CreateRefundRequest,
    InvoiceReturnLineView,
    InvoiceReturnView,
    RefundView,
    ReturnableInvoiceView,
    ReturnableLineView,
    ReturnableSourceView,
    ReturnLineRequest,
    ReturnOptionsView,
    ReturnSourceRequest,
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


class ReturnsBusinessConflict(ReturnsConflict):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SourceCandidate:
    source_id: UUID
    source_kind: Literal["sales_delivery_allocation", "purchase_receipt_layer"]
    product_id: UUID
    warehouse_id: UUID
    warehouse_name_ar: str
    lot_number: str
    source_reference: str
    source_date: datetime
    stable_label: str
    cost_basis: Literal["quantity", "weight"]
    original_quantity: Decimal
    original_weight_kg: Decimal
    already_returned_quantity: Decimal
    already_returned_weight_kg: Decimal
    remaining_quantity: Decimal
    remaining_weight_kg: Decimal
    unit_cost: Decimal
    root_layer_id: UUID
    original_allocation_id: UUID | None = None
    purchase_receipt_line_id: UUID | None = None
    consumed_layer_id: UUID | None = None


@dataclass(frozen=True)
class PreparedSource:
    candidate: SourceCandidate
    quantity: Decimal
    weight_kg: Decimal
    total_cost: Decimal


@dataclass(frozen=True)
class ReturnContext:
    order: SalesOrder | PurchaseOrder
    partner_id: UUID
    customer_invoice_id: UUID | None
    supplier_invoice_id: UUID | None
    number_prefix: str


@dataclass(frozen=True)
class PreparedReturnLine:
    source: ReturnableLineView
    quantity: Decimal
    weight_kg: Decimal
    line_total: Decimal
    sources: list[PreparedSource]


@dataclass(frozen=True)
class RefundInvoiceContext:
    return_type: Literal["sales", "purchase"]
    invoice_id: UUID
    partner_id: UUID
    customer_invoice_id: UUID | None
    supplier_invoice_id: UUID | None
    original_total: Decimal


def _hash(payload: BaseModel) -> str:
    return sha256(payload.model_dump_json().encode()).hexdigest()


def _derived_key(key: str, value: UUID, suffix: str) -> str:
    return f"ret-{sha256(key.encode()).hexdigest()[:24]}-{str(value)[:12]}-{suffix}"


def _active_return_total(db: Session, *, return_type: str, invoice_id: UUID) -> Decimal:
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
                    return_status=("none" if returned == 0 else "full" if net == 0 else "partial"),
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
            purchase_statement = purchase_statement.where(SupplierInvoice.supplier_id == partner_id)
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
                    return_status=("none" if returned == 0 else "full" if net == 0 else "partial"),
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


def _returned_source_amounts(
    db: Session,
    *,
    original_allocation_id: UUID | None = None,
    consumed_layer_id: UUID | None = None,
) -> tuple[Decimal, Decimal]:
    statement = (
        select(
            func.coalesce(func.sum(InvoiceReturnSource.quantity), 0),
            func.coalesce(func.sum(InvoiceReturnSource.weight_kg), 0),
        )
        .join(
            InvoiceReturnLine,
            InvoiceReturnLine.id == InvoiceReturnSource.invoice_return_line_id,
        )
        .join(InvoiceReturn, InvoiceReturn.id == InvoiceReturnLine.invoice_return_id)
        .where(InvoiceReturn.status == "posted")
    )
    if original_allocation_id is not None:
        statement = statement.where(
            InvoiceReturnSource.original_inventory_allocation_id == original_allocation_id
        )
    elif consumed_layer_id is not None:
        statement = statement.where(
            InvoiceReturnSource.consumed_inventory_layer_id == consumed_layer_id
        )
    else:
        raise ValueError("يجب تحديد مصدر لحساب الكمية المرتجعة")
    row = db.execute(statement).one()
    return quantity(Decimal(str(row[0] or 0))), quantity(Decimal(str(row[1] or 0)))


def _source_view(candidate: SourceCandidate) -> ReturnableSourceView:
    return ReturnableSourceView(
        source_id=candidate.source_id,
        source_kind=candidate.source_kind,
        lot_number=candidate.lot_number,
        source_reference=candidate.source_reference,
        source_date=candidate.source_date,
        warehouse_id=candidate.warehouse_id,
        warehouse_name_ar=candidate.warehouse_name_ar,
        stable_label=candidate.stable_label,
        original_quantity=candidate.original_quantity,
        already_returned_quantity=candidate.already_returned_quantity,
        remaining_returnable_quantity=candidate.remaining_quantity,
        original_weight_kg=candidate.original_weight_kg,
        already_returned_weight_kg=candidate.already_returned_weight_kg,
        remaining_returnable_weight_kg=candidate.remaining_weight_kg,
    )


def _sales_source_candidates(
    db: Session, *, sales_order_line_id: UUID, lock: bool = False
) -> list[SourceCandidate]:
    delivery_rows = list(
        db.execute(
            select(SalesDeliveryLine, SalesDelivery)
            .join(SalesDelivery, SalesDelivery.id == SalesDeliveryLine.sales_delivery_id)
            .where(
                SalesDeliveryLine.sales_order_line_id == sales_order_line_id,
                SalesDelivery.status == "posted",
            )
            .order_by(SalesDelivery.posted_at, SalesDelivery.id)
        )
    )
    delivery_by_transaction = {
        delivery_line.inventory_transaction_id: delivery
        for delivery_line, delivery in delivery_rows
    }
    if not delivery_by_transaction:
        return []
    allocation_statement = (
        select(InventoryAllocation)
        .where(InventoryAllocation.outbound_transaction_id.in_(list(delivery_by_transaction)))
        .order_by(InventoryAllocation.id)
    )
    if lock:
        allocation_statement = allocation_statement.with_for_update()
    allocations = list(db.scalars(allocation_statement))
    result: list[SourceCandidate] = []
    for index, allocation in enumerate(allocations, start=1):
        layer_statement = select(InventoryLayer).where(
            InventoryLayer.id == allocation.source_layer_id
        )
        if lock:
            layer_statement = layer_statement.with_for_update()
        layer = db.scalar(layer_statement)
        transaction = db.get(InventoryTransaction, allocation.outbound_transaction_id)
        if layer is None or transaction is None:
            raise ReturnsConflict("تعذر تحميل مصدر طبقة تسليم المبيعات")
        warehouse = db.get(Warehouse, layer.warehouse_id)
        if warehouse is None:
            raise ReturnsConflict("تعذر تحميل مخزن مصدر التسليم")
        lot = db.get(InventoryLot, layer.lot_id) if layer.lot_id else None
        returned_quantity, returned_weight = _returned_source_amounts(
            db, original_allocation_id=allocation.id
        )
        remaining_quantity = quantity(allocation.quantity - returned_quantity)
        remaining_weight = quantity(allocation.weight_kg - returned_weight)
        if remaining_quantity < 0 or remaining_weight < 0:
            raise ReturnsConflict("سجل مرتجع المبيعات تجاوز توزيع التسليم الأصلي")
        delivery = delivery_by_transaction[allocation.outbound_transaction_id]
        result.append(
            SourceCandidate(
                source_id=allocation.id,
                source_kind="sales_delivery_allocation",
                product_id=transaction.product_id,
                warehouse_id=transaction.warehouse_id,
                warehouse_name_ar=warehouse.name_ar,
                lot_number=lot.lot_number if lot else "",
                source_reference=delivery.delivery_number,
                source_date=transaction.posted_at,
                stable_label=f"مصدر التسليم {index}",
                cost_basis=cast(Literal["quantity", "weight"], transaction.cost_basis),
                original_quantity=allocation.quantity,
                original_weight_kg=allocation.weight_kg,
                already_returned_quantity=returned_quantity,
                already_returned_weight_kg=returned_weight,
                remaining_quantity=remaining_quantity,
                remaining_weight_kg=remaining_weight,
                unit_cost=allocation.unit_cost,
                root_layer_id=layer.provenance_root_layer_id or layer.id,
                original_allocation_id=allocation.id,
            )
        )
    return result


def _purchase_receipt_root_layer(
    db: Session,
    *,
    receipt: PurchaseReceipt,
    receipt_line: PurchaseReceiptLine,
    lock: bool,
) -> InventoryLayer:
    transaction = db.get(InventoryTransaction, receipt_line.inventory_transaction_id)
    purchase_order_line = db.get(PurchaseOrderLine, receipt_line.purchase_order_line_id)
    if transaction is None or purchase_order_line is None:
        raise ReturnsBusinessConflict(
            "PURCHASE_RETURN_PROVENANCE_UNRESOLVED",
            "تعذر ربط استلام الشراء التاريخي بحركة المخزون. يحتاج السجل إلى مراجعة إدارية.",
        )
    transaction_was_reversed = db.scalar(
        select(InventoryTransaction.id).where(InventoryTransaction.reversal_of_id == transaction.id)
    )
    if (
        transaction.transaction_type != "receipt"
        or transaction.reference_type != "purchase_receipt"
        or transaction.product_id != purchase_order_line.product_id
        or transaction_was_reversed is not None
    ):
        raise ReturnsBusinessConflict(
            "PURCHASE_RETURN_PROVENANCE_UNRESOLVED",
            f"حركة المخزون المرتبطة بسند الاستلام {receipt.receipt_number} "
            "ليست حركة استلام شراء فعالة يمكن إثبات مصدرها. يحتاج السجل إلى مراجعة إدارية.",
        )
    statement = select(InventoryLayer).where(InventoryLayer.source_transaction_id == transaction.id)
    if lock:
        statement = statement.with_for_update()
    linked = db.scalar(statement)
    if linked is not None:
        return linked

    candidate_statement = select(InventoryLayer).where(
        InventoryLayer.product_id == transaction.product_id,
        InventoryLayer.warehouse_id == transaction.warehouse_id,
        InventoryLayer.source_type == "purchase_receipt",
        InventoryLayer.source_id == str(receipt.id),
        InventoryLayer.source_line_id == str(receipt_line.purchase_order_line_id),
        InventoryLayer.provenance_root_layer_id.is_(None),
    )
    if lock:
        candidate_statement = candidate_statement.with_for_update()
    candidates = list(db.scalars(candidate_statement))
    if len(candidates) != 1:
        raise ReturnsBusinessConflict(
            "PURCHASE_RETURN_PROVENANCE_UNRESOLVED",
            f"تعذر إثبات طبقة المخزون الخاصة بسند الاستلام {receipt.receipt_number}. "
            "يحتاج السجل إلى مراجعة إدارية قبل تنفيذ مرتجع الشراء.",
        )
    if lock:
        candidates[0].source_transaction_id = transaction.id
        db.flush()
    return candidates[0]


def _purchase_source_candidates(
    db: Session, *, purchase_order_line_id: UUID, lock: bool = False
) -> list[SourceCandidate]:
    receipt_rows = list(
        db.execute(
            select(PurchaseReceiptLine, PurchaseReceipt)
            .join(
                PurchaseReceipt,
                PurchaseReceipt.id == PurchaseReceiptLine.purchase_receipt_id,
            )
            .where(
                PurchaseReceiptLine.purchase_order_line_id == purchase_order_line_id,
                PurchaseReceipt.status == "posted",
            )
            .order_by(PurchaseReceipt.posted_at, PurchaseReceipt.id)
        )
    )
    result: list[SourceCandidate] = []
    sequence = 0
    for receipt_line, receipt in receipt_rows:
        root = _purchase_receipt_root_layer(
            db, receipt=receipt, receipt_line=receipt_line, lock=lock
        )
        layer_statement = (
            select(InventoryLayer)
            .where(
                InventoryLayer.product_id == root.product_id,
                InventoryLayer.warehouse_id == root.warehouse_id,
                or_(
                    InventoryLayer.id == root.id,
                    InventoryLayer.provenance_root_layer_id == root.id,
                ),
                or_(
                    InventoryLayer.quantity_remaining > 0,
                    InventoryLayer.weight_remaining_kg > 0,
                ),
            )
            .order_by(InventoryLayer.received_at, InventoryLayer.id)
        )
        if lock:
            layer_statement = layer_statement.with_for_update()
        for layer in db.scalars(layer_statement):
            sequence += 1
            warehouse = db.get(Warehouse, layer.warehouse_id)
            if warehouse is None:
                raise ReturnsConflict("تعذر تحميل مخزن استلام المشتريات")
            lot = db.get(InventoryLot, layer.lot_id) if layer.lot_id else None
            returned_quantity, returned_weight = _returned_source_amounts(
                db, consumed_layer_id=layer.id
            )
            result.append(
                SourceCandidate(
                    source_id=layer.id,
                    source_kind="purchase_receipt_layer",
                    product_id=layer.product_id,
                    warehouse_id=layer.warehouse_id,
                    warehouse_name_ar=warehouse.name_ar,
                    lot_number=(lot.lot_number if lot else receipt_line.lot_number),
                    source_reference=receipt.receipt_number,
                    source_date=layer.received_at,
                    stable_label=f"{receipt.receipt_number} · مصدر {sequence}",
                    cost_basis=cast(Literal["quantity", "weight"], layer.cost_basis),
                    original_quantity=layer.quantity_received,
                    original_weight_kg=layer.weight_received_kg,
                    already_returned_quantity=returned_quantity,
                    already_returned_weight_kg=returned_weight,
                    remaining_quantity=layer.quantity_remaining,
                    remaining_weight_kg=layer.weight_remaining_kg,
                    unit_cost=layer.unit_cost,
                    root_layer_id=root.id,
                    purchase_receipt_line_id=receipt_line.id,
                    consumed_layer_id=layer.id,
                )
            )
    return result


def get_returnable_lines(
    db: Session, *, return_type: str, invoice_id: UUID
) -> list[ReturnableLineView]:
    result: list[ReturnableLineView] = []
    if return_type == "sales":
        invoice = db.get(CustomerInvoice, invoice_id)
        if invoice is None or invoice.status != "posted":
            raise ReturnsNotFound("فاتورة المبيعات غير موجودة أو غير معتمدة")
        rows = db.execute(
            select(SalesOrderLine, Product)
            .join(Product, Product.id == SalesOrderLine.product_id)
            .where(SalesOrderLine.sales_order_id == invoice.sales_order_id)
            .order_by(SalesOrderLine.created_at, SalesOrderLine.id)
        )
        for sales_line, product in rows:
            delivery_totals = db.execute(
                select(
                    func.coalesce(func.sum(SalesDeliveryLine.quantity), 0),
                    func.coalesce(func.sum(SalesDeliveryLine.weight_kg), 0),
                )
                .join(
                    SalesDelivery,
                    SalesDelivery.id == SalesDeliveryLine.sales_delivery_id,
                )
                .where(
                    SalesDeliveryLine.sales_order_line_id == sales_line.id,
                    SalesDelivery.status == "posted",
                )
            ).one()
            original_quantity = quantity(Decimal(str(delivery_totals[0] or 0)))
            original_weight = quantity(Decimal(str(delivery_totals[1] or 0)))
            if original_quantity <= 0 and original_weight <= 0:
                continue
            returned_quantity, returned_weight = _returned_line_amounts(
                db, return_type="sales", source_line_id=sales_line.id
            )
            sources = _sales_source_candidates(db, sales_order_line_id=sales_line.id, lock=False)
            cost_basis: Literal["quantity", "weight"] = (
                sources[0].cost_basis if sources else "quantity"
            )
            commercial_unit_price = (
                sales_line.price_per_kg if cost_basis == "weight" else sales_line.unit_price
            )
            result.append(
                ReturnableLineView(
                    source_line_id=sales_line.id,
                    product_id=sales_line.product_id,
                    product_code=product.code,
                    product_name_ar=product.name_ar,
                    unit=sales_line.unit,
                    unit_price=commercial_unit_price,
                    cost_basis=cost_basis,
                    original_quantity=original_quantity,
                    returned_quantity=returned_quantity,
                    remaining_quantity=quantity(original_quantity - returned_quantity),
                    original_weight_kg=original_weight,
                    returned_weight_kg=returned_weight,
                    remaining_weight_kg=quantity(original_weight - returned_weight),
                    sources=[_source_view(item) for item in sources],
                )
            )
    elif return_type == "purchase":
        purchase_invoice = db.get(SupplierInvoice, invoice_id)
        if purchase_invoice is None or purchase_invoice.status != "posted":
            raise ReturnsNotFound("فاتورة المشتريات غير موجودة أو غير معتمدة")
        purchase_lines = list(
            db.scalars(
                select(PurchaseOrderLine)
                .where(PurchaseOrderLine.purchase_order_id == purchase_invoice.purchase_order_id)
                .order_by(PurchaseOrderLine.created_at, PurchaseOrderLine.id)
            )
        )
        products = {
            item.id: item
            for item in db.scalars(
                select(Product).where(
                    Product.id.in_({purchase_line.product_id for purchase_line in purchase_lines})
                )
            )
        }
        for purchase_line in purchase_lines:
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
                    PurchaseReceiptLine.purchase_order_line_id == purchase_line.id,
                    PurchaseReceipt.status == "posted",
                )
            ).one()
            original_quantity = quantity(Decimal(str(received[0] or 0)))
            original_weight = quantity(Decimal(str(received[1] or 0)))
            returned_quantity, returned_weight = _returned_line_amounts(
                db, return_type="purchase", source_line_id=purchase_line.id
            )
            product = products[purchase_line.product_id]
            sources = _purchase_source_candidates(
                db, purchase_order_line_id=purchase_line.id, lock=False
            )
            result.append(
                ReturnableLineView(
                    source_line_id=purchase_line.id,
                    product_id=purchase_line.product_id,
                    product_code=product.code,
                    product_name_ar=product.name_ar,
                    unit="كجم" if purchase_line.cost_basis == "weight" else "وحدة",
                    unit_price=purchase_line.unit_price,
                    cost_basis=cast(Literal["quantity", "weight"], purchase_line.cost_basis),
                    original_quantity=original_quantity,
                    returned_quantity=returned_quantity,
                    remaining_quantity=quantity(original_quantity - returned_quantity),
                    original_weight_kg=original_weight,
                    returned_weight_kg=returned_weight,
                    remaining_weight_kg=quantity(original_weight - returned_weight),
                    sources=[_source_view(item) for item in sources],
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
        valuation_method=cast(Literal["legacy_aggregate", "source_layer"], item.valuation_method),
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


def _candidate_basis_amount(candidate: SourceCandidate) -> Decimal:
    return (
        candidate.remaining_weight_kg
        if candidate.cost_basis == "weight"
        else candidate.remaining_quantity
    )


def _requested_source_amounts(
    candidate: SourceCandidate, *, requested_quantity: Decimal, requested_weight: Decimal
) -> tuple[Decimal, Decimal]:
    if candidate.cost_basis == "weight":
        weight = quantity(requested_weight)
        if weight <= 0:
            raise ReturnsConflict("أدخل الوزن المرتجع من مصدر المخزون المحدد")
        if weight > candidate.remaining_weight_kg:
            raise ReturnsConflict("الوزن المطلوب يتجاوز المتاح من مصدر المخزون المحدد")
        if weight == candidate.remaining_weight_kg:
            return candidate.remaining_quantity, candidate.remaining_weight_kg
        paired_quantity = (
            quantity(candidate.remaining_quantity * weight / candidate.remaining_weight_kg)
            if candidate.remaining_weight_kg > 0
            else ZERO
        )
        return paired_quantity, weight

    returned_quantity = quantity(requested_quantity)
    if returned_quantity <= 0:
        raise ReturnsConflict("أدخل الكمية المرتجعة من مصدر المخزون المحدد")
    if returned_quantity > candidate.remaining_quantity:
        raise ReturnsConflict("الكمية المطلوبة تتجاوز المتاح من مصدر المخزون المحدد")
    if returned_quantity == candidate.remaining_quantity:
        return candidate.remaining_quantity, candidate.remaining_weight_kg
    paired_weight = (
        quantity(candidate.remaining_weight_kg * returned_quantity / candidate.remaining_quantity)
        if candidate.remaining_quantity > 0
        else ZERO
    )
    return returned_quantity, paired_weight


def _purchase_attributable_error(
    *,
    source: ReturnableLineView,
    requested: Decimal,
    available: Decimal,
    candidates: list[SourceCandidate],
) -> ReturnsBusinessConflict:
    unit_label = "كجم" if source.cost_basis == "weight" else source.unit
    references = "، ".join(
        dict.fromkeys(item.source_reference for item in candidates if item.source_reference)
    )
    reference_text = f" من استلام الشراء {references}" if references else " من نفس استلام الشراء"
    return ReturnsBusinessConflict(
        "PURCHASE_RETURN_ATTRIBUTABLE_STOCK_INSUFFICIENT",
        f"لا يمكن إتمام مرتجع الشراء بهذه الكمية. المطلوب إرجاعه: {requested} {unit_label}، "
        f"والمتاح فعليًا{reference_text}: {available} {unit_label}. "
        f"برجاء تقليل المرتجع إلى {available} {unit_label} أو أقل؛ "
        "ولا يمكن استخدام مخزون غير مرتبط بهذا الاستلام.",
    )


def _prepare_sources_for_line(
    *,
    return_type: str,
    request_line: ReturnLineRequest,
    source: ReturnableLineView,
    candidates: list[SourceCandidate],
) -> list[PreparedSource]:
    request = request_line
    available_candidates = [item for item in candidates if _candidate_basis_amount(item) > 0]
    target_remaining = (
        source.remaining_weight_kg if source.cost_basis == "weight" else source.remaining_quantity
    )
    available_total = quantity(
        sum((_candidate_basis_amount(item) for item in available_candidates), ZERO)
    )

    if request.mode == "full_remaining":
        requested_total = target_remaining
        if return_type == "purchase" and requested_total > available_total:
            raise _purchase_attributable_error(
                source=source,
                requested=requested_total,
                available=available_total,
                candidates=candidates,
            )
        prepared: list[PreparedSource] = []
        remaining_target = requested_total
        for candidate in available_candidates:
            if remaining_target <= 0:
                break
            available = _candidate_basis_amount(candidate)
            take = min(available, remaining_target)
            returned_quantity, returned_weight = _requested_source_amounts(
                candidate,
                requested_quantity=take if candidate.cost_basis == "quantity" else ZERO,
                requested_weight=take if candidate.cost_basis == "weight" else ZERO,
            )
            basis_amount = (
                returned_weight if candidate.cost_basis == "weight" else returned_quantity
            )
            prepared.append(
                PreparedSource(
                    candidate=candidate,
                    quantity=returned_quantity,
                    weight_kg=returned_weight,
                    total_cost=quantity(basis_amount * candidate.unit_cost),
                )
            )
            remaining_target = quantity(remaining_target - take)
        if remaining_target != 0:
            if return_type == "purchase":
                raise _purchase_attributable_error(
                    source=source,
                    requested=requested_total,
                    available=available_total,
                    candidates=candidates,
                )
            raise ReturnsConflict("مصادر تسليم المبيعات لا تغطي كامل الكمية المتبقية")
        return prepared

    candidate_by_id = {item.source_id: item for item in available_candidates}
    requested_sources = request.sources
    if not requested_sources:
        if len(available_candidates) != 1:
            raise ReturnsConflict(
                "اختر الدفعة أو مصدر التسليم المطلوب إرجاعه؛ "
                "لا يمكن اختيار مصدر تلقائيًا عند تعدد المصادر"
            )
        requested_sources = [
            ReturnSourceRequest(
                source_id=available_candidates[0].source_id,
                quantity=request.quantity,
                weight_kg=request.weight_kg,
            )
        ]

    requested_total = quantity(
        sum(
            (
                item.weight_kg if source.cost_basis == "weight" else item.quantity
                for item in requested_sources
            ),
            ZERO,
        )
    )
    if return_type == "purchase" and requested_total > available_total:
        raise _purchase_attributable_error(
            source=source,
            requested=requested_total,
            available=available_total,
            candidates=candidates,
        )
    prepared = []
    for requested_source in requested_sources:
        selected_candidate = candidate_by_id.get(requested_source.source_id)
        if selected_candidate is None:
            raise ReturnsConflict("مصدر المخزون المحدد لا يخص بند الفاتورة أو لم يعد متاحًا")
        try:
            returned_quantity, returned_weight = _requested_source_amounts(
                selected_candidate,
                requested_quantity=requested_source.quantity,
                requested_weight=requested_source.weight_kg,
            )
        except ReturnsConflict as exc:
            if return_type == "purchase":
                raise _purchase_attributable_error(
                    source=source,
                    requested=requested_total,
                    available=available_total,
                    candidates=candidates,
                ) from exc
            raise
        basis_amount = (
            returned_weight if selected_candidate.cost_basis == "weight" else returned_quantity
        )
        prepared.append(
            PreparedSource(
                candidate=selected_candidate,
                quantity=returned_quantity,
                weight_kg=returned_weight,
                total_cost=quantity(basis_amount * selected_candidate.unit_cost),
            )
        )
    return prepared


def _existing_return(db: Session, *, idempotency_key: str, digest: str) -> InvoiceReturn | None:
    existing = db.scalar(
        select(InvoiceReturn).where(InvoiceReturn.idempotency_key == idempotency_key)
    )
    if existing is not None and existing.request_hash != digest:
        raise ReturnsConflict("مفتاح منع التكرار مستخدم لمرتجع مختلف")
    return existing


def _lock_return_context(db: Session, payload: CreateInvoiceReturnRequest) -> ReturnContext:
    if payload.return_type == "sales":
        sales_invoice = db.scalar(
            select(CustomerInvoice)
            .where(CustomerInvoice.id == payload.invoice_id)
            .with_for_update()
        )
        if sales_invoice is None or sales_invoice.status != "posted":
            raise ReturnsNotFound("فاتورة المبيعات غير موجودة أو غير معتمدة")
        sales_order = db.get(SalesOrder, sales_invoice.sales_order_id)
        context = (
            ReturnContext(
                order=sales_order,
                partner_id=sales_invoice.customer_id,
                customer_invoice_id=sales_invoice.id,
                supplier_invoice_id=None,
                number_prefix="sales_return",
            )
            if sales_order is not None
            else None
        )
    else:
        supplier_invoice = db.scalar(
            select(SupplierInvoice)
            .where(SupplierInvoice.id == payload.invoice_id)
            .with_for_update()
        )
        if supplier_invoice is None or supplier_invoice.status != "posted":
            raise ReturnsNotFound("فاتورة المشتريات غير موجودة أو غير معتمدة")
        purchase_order = db.get(PurchaseOrder, supplier_invoice.purchase_order_id)
        context = (
            ReturnContext(
                order=purchase_order,
                partner_id=supplier_invoice.supplier_id,
                customer_invoice_id=None,
                supplier_invoice_id=supplier_invoice.id,
                number_prefix="purchase_return",
            )
            if purchase_order is not None
            else None
        )
    if context is None:
        raise ReturnsNotFound("أمر الفاتورة غير موجود")
    return context


def _locked_source_candidates(
    db: Session,
    *,
    return_type: Literal["sales", "purchase"],
    source_line_id: UUID,
) -> list[SourceCandidate]:
    if return_type == "sales":
        return _sales_source_candidates(db, sales_order_line_id=source_line_id, lock=True)
    return _purchase_source_candidates(db, purchase_order_line_id=source_line_id, lock=True)


def _prepare_return_lines(
    db: Session,
    *,
    payload: CreateInvoiceReturnRequest,
    order: SalesOrder | PurchaseOrder,
) -> tuple[list[PreparedReturnLine], Decimal]:
    available = {
        item.source_line_id: item
        for item in get_returnable_lines(
            db, return_type=payload.return_type, invoice_id=payload.invoice_id
        )
    }
    requested_lines = [available.get(request_line.source_line_id) for request_line in payload.lines]
    lock_inventory_contexts(
        db,
        {
            (source.product_id, order.warehouse_id)
            for source in requested_lines
            if source is not None
        },
    )
    prepared_lines: list[PreparedReturnLine] = []
    total = ZERO
    for request_line in payload.lines:
        source = available.get(request_line.source_line_id)
        if source is None:
            raise ReturnsConflict("أحد بنود المرتجع لا يخص الفاتورة")
        prepared_sources = _prepare_sources_for_line(
            return_type=payload.return_type,
            request_line=request_line,
            source=source,
            candidates=_locked_source_candidates(
                db,
                return_type=payload.return_type,
                source_line_id=source.source_line_id,
            ),
        )
        returned_quantity = quantity(sum((item.quantity for item in prepared_sources), ZERO))
        returned_weight = quantity(sum((item.weight_kg for item in prepared_sources), ZERO))
        if returned_quantity > source.remaining_quantity:
            raise ReturnsConflict(f"كمية مرتجع {source.product_name_ar} تتجاوز المتاح")
        if returned_weight > source.remaining_weight_kg:
            raise ReturnsConflict(f"وزن مرتجع {source.product_name_ar} يتجاوز المتاح")
        basis_amount = returned_weight if source.cost_basis == "weight" else returned_quantity
        line_total = money(basis_amount * source.unit_price)
        if line_total <= 0:
            raise ReturnsConflict("قيمة بند المرتجع يجب أن تكون أكبر من صفر")
        total += line_total
        prepared_lines.append(
            PreparedReturnLine(
                source=source,
                quantity=returned_quantity,
                weight_kg=returned_weight,
                line_total=line_total,
                sources=prepared_sources,
            )
        )
    total = money(total)
    if total <= 0:
        raise ReturnsConflict("إجمالي المرتجع يجب أن يكون أكبر من صفر")
    return prepared_lines, total


def _post_source_inventory(
    db: Session,
    *,
    return_type: Literal["sales", "purchase"],
    prepared_line: PreparedReturnLine,
    prepared_source: PreparedSource,
    document: InvoiceReturn,
    line: InvoiceReturnLine,
    warehouse_id: UUID,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> tuple[UUID, UUID | None, UUID | None, UUID | None]:
    candidate = prepared_source.candidate
    child_key = _derived_key(
        idempotency_key,
        candidate.source_id,
        "source-in" if return_type == "sales" else "source-out",
    )
    if return_type == "sales":
        transaction = post_receipt(
            db,
            payload=ReceiptRequest(
                product_id=prepared_line.source.product_id,
                warehouse_id=warehouse_id,
                quantity=prepared_source.quantity,
                weight_kg=prepared_source.weight_kg,
                cost_basis=candidate.cost_basis,
                unit_cost=candidate.unit_cost,
                lot_number=candidate.lot_number,
                reference_type="sales_return",
                reference_id=str(document.id),
                reference_line_id=str(line.id),
                notes=f"{document.return_number} — {document.reason}",
            ),
            idempotency_key=child_key,
            actor_user_id=actor.user.id,
            client=client,
            transaction_type="return_in",
            provenance_root_layer_id=candidate.root_layer_id,
        )
        return_layer = receipt_layer_for_transaction(db, transaction.id)
        return transaction.id, None, None, return_layer.id

    if candidate.consumed_layer_id is None:
        raise ReturnsConflict("مصدر طبقة مرتجع الشراء غير مكتمل")
    transaction, allocation = post_exact_layer_issue(
        db,
        source_layer_id=candidate.consumed_layer_id,
        product_id=prepared_line.source.product_id,
        warehouse_id=warehouse_id,
        requested_quantity=prepared_source.quantity,
        requested_weight_kg=prepared_source.weight_kg,
        cost_basis=candidate.cost_basis,
        idempotency_key=child_key,
        reference_type="purchase_return",
        reference_id=str(document.id),
        reference_line_id=str(line.id),
        notes=f"{document.return_number} — {document.reason}",
        actor_user_id=actor.user.id,
        client=client,
    )
    return transaction.id, allocation.id, candidate.consumed_layer_id, None


def _assert_source_totals_match(db: Session, line: InvoiceReturnLine) -> None:
    totals = db.execute(
        select(
            func.coalesce(func.sum(InvoiceReturnSource.quantity), 0),
            func.coalesce(func.sum(InvoiceReturnSource.weight_kg), 0),
        ).where(InvoiceReturnSource.invoice_return_line_id == line.id)
    ).one()
    recorded_quantity = quantity(Decimal(str(totals[0] or 0)))
    recorded_weight = quantity(Decimal(str(totals[1] or 0)))
    if recorded_quantity != line.quantity or recorded_weight != line.weight_kg:
        raise ReturnsConflict("تعذر تسجيل المرتجع: الكمية التجارية لا تطابق مصادر المخزون")


def _persist_return_line(
    db: Session,
    *,
    prepared_line: PreparedReturnLine,
    document: InvoiceReturn,
    return_type: Literal["sales", "purchase"],
    warehouse_id: UUID,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> None:
    source = prepared_line.source
    line = InvoiceReturnLine(
        invoice_return_id=document.id,
        sales_order_line_id=source.source_line_id if return_type == "sales" else None,
        purchase_order_line_id=(source.source_line_id if return_type == "purchase" else None),
        product_id=source.product_id,
        inventory_transaction_id=None,
        quantity=prepared_line.quantity,
        weight_kg=prepared_line.weight_kg,
        cost_basis=source.cost_basis,
        unit=source.unit,
        unit_price=source.unit_price,
        line_total=prepared_line.line_total,
        inventory_cost=quantity(sum((item.total_cost for item in prepared_line.sources), ZERO)),
    )
    db.add(line)
    db.flush()
    for prepared_source in prepared_line.sources:
        transaction_id, allocation_id, consumed_layer_id, return_layer_id = _post_source_inventory(
            db,
            return_type=return_type,
            prepared_line=prepared_line,
            prepared_source=prepared_source,
            document=document,
            line=line,
            warehouse_id=warehouse_id,
            idempotency_key=idempotency_key,
            actor=actor,
            client=client,
        )
        candidate = prepared_source.candidate
        db.add(
            InvoiceReturnSource(
                invoice_return_line_id=line.id,
                source_kind=candidate.source_kind,
                original_inventory_allocation_id=candidate.original_allocation_id,
                purchase_receipt_line_id=candidate.purchase_receipt_line_id,
                root_inventory_layer_id=candidate.root_layer_id,
                consumed_inventory_layer_id=consumed_layer_id,
                return_inventory_transaction_id=transaction_id,
                return_inventory_allocation_id=allocation_id,
                return_inventory_layer_id=return_layer_id,
                quantity=prepared_source.quantity,
                weight_kg=prepared_source.weight_kg,
                cost_basis=candidate.cost_basis,
                unit_cost=candidate.unit_cost,
                total_cost=prepared_source.total_cost,
            )
        )
    db.flush()
    _assert_source_totals_match(db, line)


def create_return(
    db: Session,
    *,
    payload: CreateInvoiceReturnRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> InvoiceReturnView:
    digest = _hash(payload)
    existing = _existing_return(db, idempotency_key=idempotency_key, digest=digest)
    if existing is not None:
        return _return_view(db, existing)

    context = _lock_return_context(db, payload)
    existing = _existing_return(db, idempotency_key=idempotency_key, digest=digest)
    if existing is not None:
        return _return_view(db, existing)

    prepared_lines, total = _prepare_return_lines(db, payload=payload, order=context.order)
    document = InvoiceReturn(
        return_number=allocate_document_number(db, context.number_prefix),
        return_type=payload.return_type,
        valuation_method="source_layer",
        customer_invoice_id=context.customer_invoice_id,
        supplier_invoice_id=context.supplier_invoice_id,
        partner_id=context.partner_id,
        warehouse_id=context.order.warehouse_id,
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
    for prepared_line in prepared_lines:
        _persist_return_line(
            db,
            prepared_line=prepared_line,
            document=document,
            return_type=payload.return_type,
            warehouse_id=context.order.warehouse_id,
            idempotency_key=idempotency_key,
            actor=actor,
            client=client,
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
    if (
        _refunded_total(
            db,
            return_type=document.return_type,
            invoice_id=cast(UUID, document.customer_invoice_id or document.supplier_invoice_id),
        )
        > 0
    ):
        raise ReturnsConflict("اعكس استردادات الفاتورة أولًا قبل عكس المرتجع")
    lines = list(
        db.scalars(
            select(InvoiceReturnLine)
            .where(InvoiceReturnLine.invoice_return_id == document.id)
            .order_by(InvoiceReturnLine.id)
            .with_for_update()
        )
    )
    if document.valuation_method == "legacy_aggregate":
        for line in lines:
            if line.inventory_transaction_id is None:
                raise ReturnsConflict("مستند المرتجع التاريخي يفتقد حركة المخزون")
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
    else:
        sources_by_line: dict[UUID, list[InvoiceReturnSource]] = {}
        for line in lines:
            sources = list(
                db.scalars(
                    select(InvoiceReturnSource)
                    .where(InvoiceReturnSource.invoice_return_line_id == line.id)
                    .order_by(InvoiceReturnSource.id)
                    .with_for_update()
                )
            )
            source_quantity = quantity(sum((item.quantity for item in sources), ZERO))
            source_weight = quantity(sum((item.weight_kg for item in sources), ZERO))
            if source_quantity != line.quantity or source_weight != line.weight_kg:
                raise ReturnsConflict("تعذر عكس المرتجع: الكمية التجارية لا تطابق مصادر المخزون")
            sources_by_line[line.id] = sources

        lock_inventory_contexts(
            db,
            {(line.product_id, document.warehouse_id) for line in lines},
        )

        if document.return_type == "sales":
            return_layer_ids = sorted(
                [
                    source.return_inventory_layer_id
                    for sources in sources_by_line.values()
                    for source in sources
                    if source.return_inventory_layer_id is not None
                ],
                key=str,
            )
            locked_layers = {
                layer.id: layer
                for layer in db.scalars(
                    select(InventoryLayer)
                    .where(InventoryLayer.id.in_(return_layer_ids))
                    .order_by(InventoryLayer.id)
                    .with_for_update()
                )
            }
            for sources in sources_by_line.values():
                for source in sources:
                    layer = locked_layers.get(cast(UUID, source.return_inventory_layer_id))
                    if layer is None:
                        raise ReturnsConflict("تعذر العثور على طبقة مرتجع المبيعات")
                    if (
                        layer.quantity_remaining != source.quantity
                        or layer.weight_remaining_kg != source.weight_kg
                    ):
                        raise ReturnsConflict(
                            "لا يمكن عكس مرتجع المبيعات بعد استهلاك جزء من مخزونه"
                        )

        for line in lines:
            first_reversal_id: UUID | None = None
            for source in sources_by_line[line.id]:
                child_key = _derived_key(idempotency_key, source.id, "source-reverse")
                if document.return_type == "sales":
                    return_layer_id = cast(UUID, source.return_inventory_layer_id)
                    return_layer = db.get(InventoryLayer, return_layer_id)
                    if return_layer is None:
                        raise ReturnsConflict("تعذر العثور على طبقة مرتجع المبيعات")
                    reversal, _ = post_exact_layer_issue(
                        db,
                        source_layer_id=return_layer_id,
                        product_id=line.product_id,
                        warehouse_id=document.warehouse_id,
                        requested_quantity=source.quantity,
                        requested_weight_kg=source.weight_kg,
                        cost_basis=source.cost_basis,
                        idempotency_key=child_key,
                        reference_type="sales_return_reversal",
                        reference_id=str(document.id),
                        reference_line_id=str(line.id),
                        notes=payload.reason,
                        actor_user_id=actor.user.id,
                        client=client,
                        transaction_type="reversal_out",
                        reversal_of_id=source.return_inventory_transaction_id,
                    )
                    source.reversal_inventory_layer_id = None
                else:
                    consumed_layer = db.get(
                        InventoryLayer, cast(UUID, source.consumed_inventory_layer_id)
                    )
                    if consumed_layer is None:
                        raise ReturnsConflict("تعذر تحميل مصدر مرتجع المشتريات")
                    lot = (
                        db.get(InventoryLot, consumed_layer.lot_id)
                        if consumed_layer.lot_id
                        else None
                    )
                    reversal = post_receipt(
                        db,
                        payload=ReceiptRequest(
                            product_id=line.product_id,
                            warehouse_id=document.warehouse_id,
                            quantity=source.quantity,
                            weight_kg=source.weight_kg,
                            cost_basis=cast(Literal["quantity", "weight"], source.cost_basis),
                            unit_cost=source.unit_cost,
                            lot_number=lot.lot_number if lot else "",
                            reference_type="purchase_return_reversal",
                            reference_id=str(document.id),
                            reference_line_id=str(line.id),
                            notes=payload.reason,
                        ),
                        idempotency_key=child_key,
                        actor_user_id=actor.user.id,
                        client=client,
                        transaction_type="reversal_in",
                        reversal_of_id=source.return_inventory_transaction_id,
                        provenance_root_layer_id=source.root_inventory_layer_id,
                    )
                    reversal_layer = receipt_layer_for_transaction(db, reversal.id)
                    source.reversal_inventory_layer_id = reversal_layer.id
                source.reversal_inventory_transaction_id = reversal.id
                if first_reversal_id is None:
                    first_reversal_id = reversal.id
            line.reversal_inventory_transaction_id = first_reversal_id
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
        refund_type=cast(Literal["customer_refund", "supplier_refund"], item.refund_type),
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


def _existing_refund(db: Session, *, idempotency_key: str, digest: str) -> ReturnRefund | None:
    existing = db.scalar(
        select(ReturnRefund).where(ReturnRefund.idempotency_key == idempotency_key)
    )
    if existing is not None and existing.request_hash != digest:
        raise ReturnsConflict("مفتاح منع التكرار مستخدم لاسترداد مختلف")
    return existing


def _lock_refund_invoice(db: Session, payload: CreateRefundRequest) -> RefundInvoiceContext:
    if payload.refund_type == "customer_refund":
        customer_invoice = db.scalar(
            select(CustomerInvoice)
            .where(CustomerInvoice.id == payload.invoice_id)
            .with_for_update()
        )
        if customer_invoice is None or customer_invoice.status != "posted":
            raise ReturnsNotFound("فاتورة المبيعات غير موجودة أو غير معتمدة")
        return RefundInvoiceContext(
            return_type="sales",
            invoice_id=customer_invoice.id,
            partner_id=customer_invoice.customer_id,
            customer_invoice_id=customer_invoice.id,
            supplier_invoice_id=None,
            original_total=customer_invoice.total,
        )

    supplier_invoice = db.scalar(
        select(SupplierInvoice).where(SupplierInvoice.id == payload.invoice_id).with_for_update()
    )
    if supplier_invoice is None or supplier_invoice.status != "posted":
        raise ReturnsNotFound("فاتورة المشتريات غير موجودة أو غير معتمدة")
    return RefundInvoiceContext(
        return_type="purchase",
        invoice_id=supplier_invoice.id,
        partner_id=supplier_invoice.supplier_id,
        customer_invoice_id=None,
        supplier_invoice_id=supplier_invoice.id,
        original_total=supplier_invoice.total,
    )


def create_refund(
    db: Session,
    *,
    payload: CreateRefundRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> RefundView:
    digest = _hash(payload)
    existing = _existing_refund(db, idempotency_key=idempotency_key, digest=digest)
    if existing is not None:
        return _refund_view(db, existing)
    invoice = _lock_refund_invoice(db, payload)
    _, _, _, _, refundable = invoice_net_amounts(
        db,
        return_type=invoice.return_type,
        invoice_id=invoice.invoice_id,
        original_total=invoice.original_total,
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
        customer_invoice_id=invoice.customer_invoice_id,
        supplier_invoice_id=invoice.supplier_invoice_id,
        partner_id=invoice.partner_id,
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
