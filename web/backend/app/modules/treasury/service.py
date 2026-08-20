from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.common.decimal import money
from app.modules.identity.service import ClientContext, Principal, add_audit
from app.modules.master_data.models import Partner
from app.modules.master_data.service import allocate_document_number, normalize_code
from app.modules.purchasing.models import PurchaseOrder, SupplierInvoice
from app.modules.sales.models import CustomerInvoice, SalesOrder
from app.modules.treasury.models import (
    CustomerAccountAdjustment,
    FinancialAccount,
    FinancialAdjustment,
    FinancialTransfer,
    PartnerOpeningBalance,
    PaymentAllocation,
    PaymentTransaction,
)
from app.modules.treasury.schemas import (
    CustomerAdjustmentRequest,
    CustomerAdjustmentView,
    FinancialAccountRequest,
    FinancialAccountView,
    FinancialAdjustmentRequest,
    FinancialAdjustmentView,
    InvoiceAllocationRequest,
    OpeningBalanceRequest,
    OpeningBalanceView,
    OpenInvoiceView,
    OpenOrderView,
    PartnerBalanceView,
    PartnerStatementView,
    PaymentAllocationView,
    PaymentView,
    PostPaymentRequest,
    StatementLineView,
    TransferRequest,
    TransferView,
    TreasuryOptionsView,
    TreasuryPartnerOption,
    TreasurySummaryView,
    UpdateFinancialAccountRequest,
)

ZERO = Decimal("0.00")
PAYMENT_ACCOUNT_TYPES = {
    "cash": "cash",
    "bank_transfer": "bank",
    "cheque": "bank",
    "wallet": "wallet",
}


class TreasuryError(Exception):
    pass


class TreasuryNotFound(TreasuryError):
    pass


class TreasuryConflict(TreasuryError):
    pass


def _hash_payload(payload: BaseModel) -> str:
    return sha256(payload.model_dump_json().encode()).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _sum(db: Session, statement: Any) -> Decimal:
    value = db.scalar(statement)
    return money(Decimal(str(value or 0)))


def _account_balance(db: Session, account_id: UUID) -> Decimal:
    receipts = _sum(
        db,
        select(func.coalesce(func.sum(PaymentTransaction.amount), 0)).where(
            PaymentTransaction.financial_account_id == account_id,
            PaymentTransaction.transaction_type == "customer_receipt",
            PaymentTransaction.status == "posted",
        ),
    )
    payments = _sum(
        db,
        select(func.coalesce(func.sum(PaymentTransaction.amount), 0)).where(
            PaymentTransaction.financial_account_id == account_id,
            PaymentTransaction.transaction_type == "supplier_payment",
            PaymentTransaction.status == "posted",
        ),
    )
    transfers_in = _sum(
        db,
        select(func.coalesce(func.sum(FinancialTransfer.amount), 0)).where(
            FinancialTransfer.to_account_id == account_id,
            FinancialTransfer.status == "posted",
        ),
    )
    transfers_out = _sum(
        db,
        select(func.coalesce(func.sum(FinancialTransfer.amount), 0)).where(
            FinancialTransfer.from_account_id == account_id,
            FinancialTransfer.status == "posted",
        ),
    )
    adjustments = _sum(
        db,
        select(func.coalesce(func.sum(FinancialAdjustment.amount), 0)).where(
            FinancialAdjustment.financial_account_id == account_id,
            FinancialAdjustment.status == "posted",
        ),
    )
    account = db.get(FinancialAccount, account_id)
    if account is None:
        raise TreasuryNotFound("الحساب المالي غير موجود")
    return money(
        account.opening_balance + receipts - payments + transfers_in - transfers_out + adjustments
    )


def _account_view(db: Session, account: FinancialAccount) -> FinancialAccountView:
    return FinancialAccountView(
        id=account.id,
        code=account.code,
        name_ar=account.name_ar,
        account_type=account.account_type,  # type: ignore[arg-type]
        opening_balance=account.opening_balance,
        current_balance=_account_balance(db, account.id),
        is_default=account.is_default,
        is_active=account.is_active,
        notes=account.notes,
        version=account.version,
    )


def list_accounts(db: Session, *, include_inactive: bool = False) -> list[FinancialAccountView]:
    statement = select(FinancialAccount).order_by(
        FinancialAccount.is_default.desc(), FinancialAccount.name_ar
    )
    if not include_inactive:
        statement = statement.where(FinancialAccount.is_active.is_(True))
    return [_account_view(db, item) for item in db.scalars(statement)]


def treasury_options(db: Session) -> TreasuryOptionsView:
    partners = db.scalars(
        select(Partner)
        .where(
            Partner.is_active.is_(True),
            (Partner.is_customer.is_(True) | Partner.is_supplier.is_(True)),
        )
        .order_by(Partner.name_ar, Partner.code)
    )
    return TreasuryOptionsView(
        accounts=list_accounts(db),
        partners=[
            TreasuryPartnerOption(
                id=partner.id,
                code=partner.code,
                name_ar=partner.name_ar,
                is_customer=partner.is_customer,
                is_supplier=partner.is_supplier,
            )
            for partner in partners
        ],
    )


def create_account(
    db: Session,
    *,
    payload: FinancialAccountRequest,
    actor: Principal,
    client: ClientContext,
) -> FinancialAccountView:
    normalized = normalize_code(payload.code)
    if db.scalar(select(FinancialAccount.id).where(FinancialAccount.normalized_code == normalized)):
        raise TreasuryConflict("كود الحساب مستخدم بالفعل")
    if payload.is_default:
        for current in db.scalars(select(FinancialAccount).where(FinancialAccount.is_default)):
            current.is_default = False
            current.version += 1
    account = FinancialAccount(
        code=payload.code.strip(),
        normalized_code=normalized,
        name_ar=payload.name_ar.strip(),
        account_type=payload.account_type,
        opening_balance=money(payload.opening_balance),
        is_default=payload.is_default,
        is_active=True,
        notes=payload.notes.strip(),
        version=1,
    )
    db.add(account)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="treasury.account.create",
        entity_type="financial_account",
        entity_id=str(account.id),
        outcome="success",
        client=client,
        after_state={"code": account.code, "account_type": account.account_type},
    )
    return _account_view(db, account)


def update_account(
    db: Session,
    *,
    account_id: UUID,
    payload: UpdateFinancialAccountRequest,
    actor: Principal,
    client: ClientContext,
) -> FinancialAccountView:
    account = db.scalar(
        select(FinancialAccount).where(FinancialAccount.id == account_id).with_for_update()
    )
    if account is None:
        raise TreasuryNotFound("الحساب المالي غير موجود")
    if account.version != payload.version:
        raise TreasuryConflict("تم تعديل الحساب بواسطة مستخدم آخر؛ حدّث الصفحة")
    normalized = normalize_code(payload.code)
    duplicate = db.scalar(
        select(FinancialAccount.id).where(
            FinancialAccount.normalized_code == normalized,
            FinancialAccount.id != account.id,
        )
    )
    if duplicate is not None:
        raise TreasuryConflict("كود الحساب مستخدم بالفعل")
    if account.is_default and not payload.is_default:
        raise TreasuryConflict("عيّن حسابًا افتراضيًا آخر قبل إلغاء الافتراضي الحالي")
    if payload.is_default:
        for current in db.scalars(
            select(FinancialAccount)
            .where(FinancialAccount.is_default, FinancialAccount.id != account.id)
            .with_for_update()
        ):
            current.is_default = False
            current.version += 1
    if not payload.is_active and account.is_default:
        raise TreasuryConflict("لا يمكن تعطيل الحساب المالي الافتراضي")
    account.code = payload.code.strip()
    account.normalized_code = normalized
    account.name_ar = payload.name_ar.strip()
    account.account_type = payload.account_type
    account.is_default = payload.is_default
    account.is_active = payload.is_active
    account.notes = payload.notes.strip()
    account.version += 1
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="treasury.account.update",
        entity_type="financial_account",
        entity_id=str(account.id),
        outcome="success",
        client=client,
    )
    return _account_view(db, account)


def _allocation_rows(db: Session, payment: PaymentTransaction) -> list[PaymentAllocationView]:
    rows = list(
        db.scalars(
            select(PaymentAllocation)
            .where(PaymentAllocation.payment_transaction_id == payment.id)
            .order_by(PaymentAllocation.created_at, PaymentAllocation.id)
        )
    )
    result: list[PaymentAllocationView] = []
    for row in rows:
        invoice: CustomerInvoice | SupplierInvoice | None
        if row.customer_invoice_id is not None:
            invoice = db.get(CustomerInvoice, row.customer_invoice_id)
        else:
            invoice = db.get(SupplierInvoice, row.supplier_invoice_id)
        if invoice is None:
            raise TreasuryNotFound("الفاتورة المرتبطة بالحركة المالية غير موجودة")
        result.append(
            PaymentAllocationView(
                invoice_id=invoice.id,
                invoice_number=invoice.invoice_number,
                amount=row.amount,
            )
        )
    return result


def _payment_view(db: Session, payment: PaymentTransaction) -> PaymentView:
    partner = db.get(Partner, payment.partner_id)
    account = db.get(FinancialAccount, payment.financial_account_id)
    if partner is None or account is None:
        raise TreasuryNotFound("بيانات الطرف أو الحساب المرتبطة بالحركة غير موجودة")
    allocations = _allocation_rows(db, payment)
    allocated = money(sum((row.amount for row in allocations), ZERO))
    return PaymentView(
        id=payment.id,
        transaction_number=payment.transaction_number,
        transaction_date=payment.transaction_date,
        transaction_type=payment.transaction_type,  # type: ignore[arg-type]
        partner_id=payment.partner_id,
        partner_name_ar=partner.name_ar,
        financial_account_id=payment.financial_account_id,
        financial_account_name_ar=account.name_ar,
        amount=payment.amount,
        payment_method=payment.payment_method,  # type: ignore[arg-type]
        reference_type=payment.reference_type,  # type: ignore[arg-type]
        reference_id=payment.reference_id,
        allocated_amount=allocated,
        unallocated_amount=money(payment.amount - allocated),
        status=payment.status,  # type: ignore[arg-type]
        notes=payment.notes,
        reversal_reason=payment.reversal_reason,
        allocations=allocations,
    )


def list_payments(db: Session, *, limit: int = 200) -> list[PaymentView]:
    rows = db.scalars(
        select(PaymentTransaction)
        .order_by(PaymentTransaction.transaction_date.desc(), PaymentTransaction.id.desc())
        .limit(limit)
    )
    return [_payment_view(db, item) for item in rows]


def _allocated_to_customer_invoice(db: Session, invoice_id: UUID) -> Decimal:
    return _sum(
        db,
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .join(
            PaymentTransaction,
            PaymentTransaction.id == PaymentAllocation.payment_transaction_id,
        )
        .where(
            PaymentAllocation.customer_invoice_id == invoice_id,
            PaymentTransaction.status == "posted",
        ),
    )


def _allocated_to_supplier_invoice(db: Session, invoice_id: UUID) -> Decimal:
    return _sum(
        db,
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .join(
            PaymentTransaction,
            PaymentTransaction.id == PaymentAllocation.payment_transaction_id,
        )
        .where(
            PaymentAllocation.supplier_invoice_id == invoice_id,
            PaymentTransaction.status == "posted",
        ),
    )


def list_open_invoices(
    db: Session, *, transaction_type: str, partner_id: UUID
) -> list[OpenInvoiceView]:
    partner = db.get(Partner, partner_id)
    if partner is None:
        raise TreasuryNotFound("العميل أو المورد غير موجود")
    result: list[OpenInvoiceView] = []
    if transaction_type == "customer_receipt":
        invoices = db.scalars(
            select(CustomerInvoice)
            .where(CustomerInvoice.customer_id == partner_id, CustomerInvoice.status == "posted")
            .order_by(CustomerInvoice.invoice_date, CustomerInvoice.id)
        )
        for invoice in invoices:
            paid = _allocated_to_customer_invoice(db, invoice.id)
            remaining = money(invoice.total - paid)
            if remaining > ZERO:
                result.append(
                    OpenInvoiceView(
                        id=invoice.id,
                        invoice_number=invoice.invoice_number,
                        invoice_date=invoice.invoice_date,
                        partner_id=partner.id,
                        partner_name_ar=partner.name_ar,
                        invoice_kind="sales",
                        invoice_total=invoice.total,
                        paid=paid,
                        remaining=remaining,
                    )
                )
    elif transaction_type == "supplier_payment":
        invoices = db.scalars(
            select(SupplierInvoice)
            .where(SupplierInvoice.supplier_id == partner_id, SupplierInvoice.status == "posted")
            .order_by(SupplierInvoice.posted_at, SupplierInvoice.id)
        )
        for invoice in invoices:
            paid = _allocated_to_supplier_invoice(db, invoice.id)
            remaining = money(invoice.total - paid)
            if remaining > ZERO:
                result.append(
                    OpenInvoiceView(
                        id=invoice.id,
                        invoice_number=invoice.invoice_number,
                        invoice_date=invoice.posted_at or invoice.created_at,
                        partner_id=partner.id,
                        partner_name_ar=partner.name_ar,
                        invoice_kind="purchase",
                        invoice_total=invoice.total,
                        paid=paid,
                        remaining=remaining,
                    )
                )
    else:
        raise ValueError("نوع الحركة المالية غير صحيح")
    return result


def list_open_orders(
    db: Session, *, transaction_type: str, partner_id: UUID
) -> list[OpenOrderView]:
    partner = db.get(Partner, partner_id)
    if partner is None:
        raise TreasuryNotFound("العميل أو المورد غير موجود")
    result: list[OpenOrderView] = []
    if transaction_type == "customer_receipt":
        orders = db.scalars(
            select(SalesOrder)
            .where(
                SalesOrder.customer_id == partner_id,
                SalesOrder.status.notin_({"cancelled", "reversed"}),
            )
            .order_by(SalesOrder.order_date, SalesOrder.id)
        )
        reference_type = "sale"
    elif transaction_type == "supplier_payment":
        orders = db.scalars(
            select(PurchaseOrder)
            .where(
                PurchaseOrder.supplier_id == partner_id,
                PurchaseOrder.status != "cancelled",
            )
            .order_by(PurchaseOrder.order_date, PurchaseOrder.id)
        )
        reference_type = "purchase"
    else:
        raise ValueError("نوع الحركة المالية غير صحيح")
    for order in orders:
        paid = _sum(
            db,
            select(func.coalesce(func.sum(PaymentTransaction.amount), 0)).where(
                PaymentTransaction.reference_type == reference_type,
                PaymentTransaction.reference_id == order.id,
                PaymentTransaction.status == "posted",
            ),
        )
        remaining = money(order.total - paid)
        if remaining > ZERO:
            result.append(
                OpenOrderView(
                    id=order.id,
                    order_number=order.order_number,
                    order_date=order.order_date,
                    partner_id=partner.id,
                    partner_name_ar=partner.name_ar,
                    reference_type=reference_type,  # type: ignore[arg-type]
                    status=order.status,
                    total=order.total,
                    paid=paid,
                    remaining=remaining,
                )
            )
    return result


def _lock_payment_invoices(
    db: Session,
    *,
    transaction_type: str,
    partner_id: UUID,
    allocations: list[InvoiceAllocationRequest],
) -> tuple[dict[UUID, CustomerInvoice | SupplierInvoice], Decimal]:
    ids = {item.invoice_id for item in allocations}
    if not ids:
        return {}, ZERO
    if transaction_type == "customer_receipt":
        invoices = list(
            db.scalars(
                select(CustomerInvoice)
                .where(CustomerInvoice.id.in_(ids))
                .order_by(CustomerInvoice.id)
                .with_for_update()
            )
        )
    else:
        invoices = list(
            db.scalars(
                select(SupplierInvoice)
                .where(SupplierInvoice.id.in_(ids))
                .order_by(SupplierInvoice.id)
                .with_for_update()
            )
        )
    if len(invoices) != len(ids):
        raise TreasuryNotFound("إحدى الفواتير المحددة غير موجودة")
    invoice_map: dict[UUID, CustomerInvoice | SupplierInvoice] = {
        item.id: item for item in invoices
    }
    allocated_total = ZERO
    for allocation in allocations:
        invoice = invoice_map[allocation.invoice_id]
        expected_partner_id = (
            invoice.customer_id if isinstance(invoice, CustomerInvoice) else invoice.supplier_id
        )
        if expected_partner_id != partner_id or invoice.status != "posted":
            raise TreasuryConflict("إحدى الفواتير لا تخص الطرف المحدد أو غير معتمدة")
        paid = (
            _allocated_to_customer_invoice(db, invoice.id)
            if isinstance(invoice, CustomerInvoice)
            else _allocated_to_supplier_invoice(db, invoice.id)
        )
        if money(allocation.amount) > money(invoice.total - paid):
            raise TreasuryConflict(f"التوزيع على الفاتورة {invoice.invoice_number} أكبر من المتبقي")
        allocated_total += money(allocation.amount)
    return invoice_map, money(allocated_total)


def _lock_order_reference(
    db: Session,
    *,
    transaction_type: str,
    partner_id: UUID,
    reference_type: str | None,
    reference_id: UUID | None,
    amount: Decimal,
) -> CustomerInvoice | SupplierInvoice | None:
    if reference_type is None or reference_id is None:
        return None
    if reference_type == "sale":
        sales_order = db.scalar(
            select(SalesOrder).where(SalesOrder.id == reference_id).with_for_update()
        )
        if (
            sales_order is None
            or sales_order.customer_id != partner_id
            or transaction_type != "customer_receipt"
            or sales_order.status in {"cancelled", "reversed"}
        ):
            raise TreasuryConflict("أمر البيع لا يخص العميل أو لا يقبل تحصيلًا")
        invoice: CustomerInvoice | SupplierInvoice | None = db.scalar(
            select(CustomerInvoice).where(
                CustomerInvoice.sales_order_id == sales_order.id,
                CustomerInvoice.status == "posted",
            )
        )
        total = sales_order.total
    elif reference_type == "purchase":
        purchase_order = db.scalar(
            select(PurchaseOrder).where(PurchaseOrder.id == reference_id).with_for_update()
        )
        if (
            purchase_order is None
            or purchase_order.supplier_id != partner_id
            or transaction_type != "supplier_payment"
            or purchase_order.status == "cancelled"
        ):
            raise TreasuryConflict("أمر الشراء لا يخص المورد أو لا يقبل سدادًا")
        invoice = db.scalar(
            select(SupplierInvoice).where(
                SupplierInvoice.purchase_order_id == purchase_order.id,
                SupplierInvoice.status == "posted",
            )
        )
        total = purchase_order.total
    else:
        raise ValueError("نوع المستند المالي غير صحيح")
    already_paid = _sum(
        db,
        select(func.coalesce(func.sum(PaymentTransaction.amount), 0)).where(
            PaymentTransaction.reference_type == reference_type,
            PaymentTransaction.reference_id == reference_id,
            PaymentTransaction.status == "posted",
        ),
    )
    if amount > money(total - already_paid):
        raise TreasuryConflict("المبلغ أكبر من المتبقي على أمر البيع أو الشراء")
    return invoice


def apply_order_advances_to_invoice(
    db: Session,
    *,
    reference_type: str,
    reference_id: UUID,
    invoice: CustomerInvoice | SupplierInvoice,
) -> None:
    """Attach draft-order advances once the operational invoice is posted."""
    payments = list(
        db.scalars(
            select(PaymentTransaction)
            .where(
                PaymentTransaction.reference_type == reference_type,
                PaymentTransaction.reference_id == reference_id,
                PaymentTransaction.status == "posted",
            )
            .order_by(PaymentTransaction.transaction_date, PaymentTransaction.id)
            .with_for_update()
        )
    )
    for payment in payments:
        existing = db.scalar(
            select(PaymentAllocation.id).where(
                PaymentAllocation.payment_transaction_id == payment.id
            )
        )
        if existing is not None:
            continue
        is_customer = isinstance(invoice, CustomerInvoice)
        db.add(
            PaymentAllocation(
                payment_transaction_id=payment.id,
                customer_invoice_id=invoice.id if is_customer else None,
                supplier_invoice_id=invoice.id if not is_customer else None,
                amount=payment.amount,
            )
        )
        if is_customer:
            payment.customer_invoice_id = invoice.id
        else:
            payment.supplier_invoice_id = invoice.id
    db.flush()


def post_payment(
    db: Session,
    *,
    payload: PostPaymentRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> PaymentView:
    request_hash = _hash_payload(payload)
    previous = db.scalar(
        select(PaymentTransaction).where(PaymentTransaction.idempotency_key == idempotency_key)
    )
    if previous is not None:
        if previous.request_hash != request_hash:
            raise TreasuryConflict("مفتاح تكرار الحركة مستخدم بطلب مختلف")
        return _payment_view(db, previous)
    partner = db.scalar(select(Partner).where(Partner.id == payload.partner_id).with_for_update())
    if partner is None or not partner.is_active:
        raise TreasuryNotFound("العميل أو المورد غير موجود أو غير نشط")
    is_customer = payload.transaction_type == "customer_receipt"
    if (is_customer and not partner.is_customer) or (not is_customer and not partner.is_supplier):
        raise TreasuryConflict("نوع الطرف لا يطابق نوع الحركة")
    account = db.scalar(
        select(FinancialAccount)
        .where(FinancialAccount.id == payload.financial_account_id)
        .with_for_update()
    )
    if account is None or not account.is_active:
        raise TreasuryNotFound("الحساب المالي غير موجود أو غير نشط")
    if PAYMENT_ACCOUNT_TYPES[payload.payment_method] != account.account_type:
        raise TreasuryConflict("طريقة الدفع لا تتوافق مع نوع الحساب المالي")
    invoice_map, allocated_total = _lock_payment_invoices(
        db,
        transaction_type=payload.transaction_type,
        partner_id=payload.partner_id,
        allocations=payload.allocations,
    )
    amount = money(payload.amount)
    if allocated_total > amount:
        raise TreasuryConflict("إجمالي توزيع الفواتير أكبر من مبلغ الحركة")
    order_invoice = _lock_order_reference(
        db,
        transaction_type=payload.transaction_type,
        partner_id=payload.partner_id,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        amount=amount,
    )
    only_invoice = invoice_map[payload.allocations[0].invoice_id] if len(invoice_map) == 1 else None
    fully_linked = only_invoice is not None and allocated_total == amount
    payment = PaymentTransaction(
        transaction_number=allocate_document_number(
            db, "customer_receipt" if is_customer else "supplier_payment"
        ),
        transaction_type=payload.transaction_type,
        partner_id=partner.id,
        financial_account_id=account.id,
        amount=amount,
        payment_method=payload.payment_method,
        reference_type=(
            payload.reference_type
            if payload.reference_id is not None
            else ("sale" if is_customer else "purchase")
            if fully_linked
            else None
        ),
        reference_id=(
            payload.reference_id
            if payload.reference_id is not None
            else only_invoice.sales_order_id
            if isinstance(only_invoice, CustomerInvoice)
            else only_invoice.purchase_order_id
            if isinstance(only_invoice, SupplierInvoice)
            else None
        ),
        customer_invoice_id=(
            order_invoice.id
            if isinstance(order_invoice, CustomerInvoice)
            else only_invoice.id
            if isinstance(only_invoice, CustomerInvoice) and fully_linked
            else None
        ),
        supplier_invoice_id=(
            order_invoice.id
            if isinstance(order_invoice, SupplierInvoice)
            else only_invoice.id
            if isinstance(only_invoice, SupplierInvoice) and fully_linked
            else None
        ),
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status="posted",
        notes=payload.notes.strip(),
        posted_by_id=actor.user.id,
        reversal_reason="",
    )
    db.add(payment)
    db.flush()
    for allocation in payload.allocations:
        db.add(
            PaymentAllocation(
                payment_transaction_id=payment.id,
                customer_invoice_id=(allocation.invoice_id if is_customer else None),
                supplier_invoice_id=(allocation.invoice_id if not is_customer else None),
                amount=money(allocation.amount),
            )
        )
    if order_invoice is not None:
        db.add(
            PaymentAllocation(
                payment_transaction_id=payment.id,
                customer_invoice_id=(order_invoice.id if is_customer else None),
                supplier_invoice_id=(order_invoice.id if not is_customer else None),
                amount=amount,
            )
        )
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="treasury.payment.post",
        entity_type="payment_transaction",
        entity_id=str(payment.id),
        outcome="success",
        client=client,
        after_state={"number": payment.transaction_number, "amount": str(payment.amount)},
    )
    return _payment_view(db, payment)


def reverse_payment(
    db: Session,
    *,
    payment_id: UUID,
    reason: str,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> PaymentView:
    payment = db.scalar(
        select(PaymentTransaction).where(PaymentTransaction.id == payment_id).with_for_update()
    )
    if payment is None:
        raise TreasuryNotFound("الحركة المالية غير موجودة")
    if payment.status == "reversed":
        if payment.reversal_idempotency_key != idempotency_key:
            raise TreasuryConflict("تم عكس الحركة بالفعل")
        return _payment_view(db, payment)
    payment.status = "reversed"
    payment.reversal_idempotency_key = idempotency_key
    payment.reversed_by_id = actor.user.id
    payment.reversed_at = datetime.now(UTC)
    payment.reversal_reason = reason.strip()
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="treasury.payment.reverse",
        entity_type="payment_transaction",
        entity_id=str(payment.id),
        outcome="success",
        client=client,
        after_state={"reason": payment.reversal_reason},
    )
    return _payment_view(db, payment)


def _transfer_view(db: Session, transfer: FinancialTransfer) -> TransferView:
    source = db.get(FinancialAccount, transfer.from_account_id)
    destination = db.get(FinancialAccount, transfer.to_account_id)
    if source is None or destination is None:
        raise TreasuryNotFound("أحد حسابات التحويل غير موجود")
    return TransferView(
        id=transfer.id,
        transfer_number=transfer.transfer_number,
        transfer_date=transfer.transfer_date,
        from_account_id=source.id,
        from_account_name_ar=source.name_ar,
        to_account_id=destination.id,
        to_account_name_ar=destination.name_ar,
        amount=transfer.amount,
        status=transfer.status,  # type: ignore[arg-type]
        notes=transfer.notes,
        reversal_reason=transfer.reversal_reason,
    )


def list_transfers(db: Session, *, limit: int = 200) -> list[TransferView]:
    rows = db.scalars(
        select(FinancialTransfer)
        .order_by(FinancialTransfer.transfer_date.desc(), FinancialTransfer.id.desc())
        .limit(limit)
    )
    return [_transfer_view(db, item) for item in rows]


def post_transfer(
    db: Session,
    *,
    payload: TransferRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> TransferView:
    request_hash = _hash_payload(payload)
    previous = db.scalar(
        select(FinancialTransfer).where(FinancialTransfer.idempotency_key == idempotency_key)
    )
    if previous is not None:
        if previous.request_hash != request_hash:
            raise TreasuryConflict("مفتاح تكرار التحويل مستخدم بطلب مختلف")
        return _transfer_view(db, previous)
    accounts = list(
        db.scalars(
            select(FinancialAccount)
            .where(FinancialAccount.id.in_({payload.from_account_id, payload.to_account_id}))
            .order_by(FinancialAccount.id)
            .with_for_update()
        )
    )
    if len(accounts) != 2 or any(not account.is_active for account in accounts):
        raise TreasuryNotFound("أحد الحسابات غير موجود أو غير نشط")
    amount = money(payload.amount)
    if _account_balance(db, payload.from_account_id) < amount:
        raise TreasuryConflict("رصيد الحساب المحول منه غير كافٍ")
    transfer = FinancialTransfer(
        transfer_number=allocate_document_number(db, "financial_transfer"),
        from_account_id=payload.from_account_id,
        to_account_id=payload.to_account_id,
        amount=amount,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status="posted",
        notes=payload.notes.strip(),
        posted_by_id=actor.user.id,
        reversal_reason="",
    )
    db.add(transfer)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="treasury.transfer.post",
        entity_type="financial_transfer",
        entity_id=str(transfer.id),
        outcome="success",
        client=client,
    )
    return _transfer_view(db, transfer)


def reverse_transfer(
    db: Session,
    *,
    transfer_id: UUID,
    reason: str,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> TransferView:
    transfer = db.scalar(
        select(FinancialTransfer).where(FinancialTransfer.id == transfer_id).with_for_update()
    )
    if transfer is None:
        raise TreasuryNotFound("التحويل غير موجود")
    if transfer.status == "reversed":
        if transfer.reversal_idempotency_key != idempotency_key:
            raise TreasuryConflict("تم عكس التحويل بالفعل")
        return _transfer_view(db, transfer)
    list(
        db.scalars(
            select(FinancialAccount)
            .where(FinancialAccount.id.in_({transfer.from_account_id, transfer.to_account_id}))
            .order_by(FinancialAccount.id)
            .with_for_update()
        )
    )
    if _account_balance(db, transfer.to_account_id) < transfer.amount:
        raise TreasuryConflict("لا يمكن العكس لأن رصيد الحساب المستلم لم يعد كافيًا")
    transfer.status = "reversed"
    transfer.reversal_idempotency_key = idempotency_key
    transfer.reversed_by_id = actor.user.id
    transfer.reversed_at = datetime.now(UTC)
    transfer.reversal_reason = reason.strip()
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="treasury.transfer.reverse",
        entity_type="financial_transfer",
        entity_id=str(transfer.id),
        outcome="success",
        client=client,
    )
    return _transfer_view(db, transfer)


def _adjustment_view(db: Session, item: FinancialAdjustment) -> FinancialAdjustmentView:
    account = db.get(FinancialAccount, item.financial_account_id)
    if account is None:
        raise TreasuryNotFound("الحساب المرتبط بالتسوية غير موجود")
    return FinancialAdjustmentView(
        id=item.id,
        adjustment_number=item.adjustment_number,
        adjustment_date=item.adjustment_date,
        financial_account_id=account.id,
        financial_account_name_ar=account.name_ar,
        amount=item.amount,
        target_balance=item.target_balance,
        status=item.status,  # type: ignore[arg-type]
        notes=item.notes,
        reversal_reason=item.reversal_reason,
    )


def post_financial_adjustment(
    db: Session,
    *,
    payload: FinancialAdjustmentRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> FinancialAdjustmentView:
    request_hash = _hash_payload(payload)
    previous = db.scalar(
        select(FinancialAdjustment).where(FinancialAdjustment.idempotency_key == idempotency_key)
    )
    if previous is not None:
        if previous.request_hash != request_hash:
            raise TreasuryConflict("مفتاح تكرار التسوية مستخدم بطلب مختلف")
        return _adjustment_view(db, previous)
    account = db.scalar(
        select(FinancialAccount)
        .where(FinancialAccount.id == payload.financial_account_id)
        .with_for_update()
    )
    if account is None or not account.is_active:
        raise TreasuryNotFound("الحساب المالي غير موجود أو غير نشط")
    current = _account_balance(db, account.id)
    target = money(payload.target_balance)
    difference = money(target - current)
    if difference == ZERO:
        raise TreasuryConflict("الرصيد الحالي يساوي الرصيد المطلوب؛ لا توجد تسوية")
    item = FinancialAdjustment(
        adjustment_number=allocate_document_number(db, "financial_adjustment"),
        financial_account_id=account.id,
        amount=difference,
        target_balance=target,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status="posted",
        notes=payload.notes.strip(),
        posted_by_id=actor.user.id,
        reversal_reason="",
    )
    db.add(item)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="treasury.adjustment.post",
        entity_type="financial_adjustment",
        entity_id=str(item.id),
        outcome="success",
        client=client,
    )
    return _adjustment_view(db, item)


def reverse_financial_adjustment(
    db: Session,
    *,
    adjustment_id: UUID,
    reason: str,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> FinancialAdjustmentView:
    item = db.scalar(
        select(FinancialAdjustment).where(FinancialAdjustment.id == adjustment_id).with_for_update()
    )
    if item is None:
        raise TreasuryNotFound("التسوية غير موجودة")
    if item.status == "reversed":
        if item.reversal_idempotency_key != idempotency_key:
            raise TreasuryConflict("تم عكس التسوية بالفعل")
        return _adjustment_view(db, item)
    item.status = "reversed"
    item.reversal_idempotency_key = idempotency_key
    item.reversed_by_id = actor.user.id
    item.reversed_at = datetime.now(UTC)
    item.reversal_reason = reason.strip()
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="treasury.adjustment.reverse",
        entity_type="financial_adjustment",
        entity_id=str(item.id),
        outcome="success",
        client=client,
    )
    return _adjustment_view(db, item)


def _opening_view(db: Session, item: PartnerOpeningBalance) -> OpeningBalanceView:
    partner = db.get(Partner, item.partner_id)
    if partner is None:
        raise TreasuryNotFound("الطرف المرتبط بالرصيد الافتتاحي غير موجود")
    reversed_entry = db.scalar(
        select(PartnerOpeningBalance.id).where(PartnerOpeningBalance.reversal_of_id == item.id)
    )
    status = "reversal" if item.reversal_of_id else "reversed" if reversed_entry else "posted"
    return OpeningBalanceView(
        id=item.id,
        entry_number=item.entry_number,
        entry_date=item.entry_date,
        partner_id=item.partner_id,
        partner_name_ar=partner.name_ar,
        nature=item.nature,  # type: ignore[arg-type]
        amount=item.amount,
        source=item.source,  # type: ignore[arg-type]
        reversal_of_id=item.reversal_of_id,
        status=status,  # type: ignore[arg-type]
        notes=item.notes,
    )


def list_opening_balances(db: Session) -> list[OpeningBalanceView]:
    rows = db.scalars(
        select(PartnerOpeningBalance).order_by(
            PartnerOpeningBalance.entry_date.desc(), PartnerOpeningBalance.id.desc()
        )
    )
    return [_opening_view(db, item) for item in rows]


def post_opening_balance(
    db: Session,
    *,
    payload: OpeningBalanceRequest,
    actor: Principal,
    client: ClientContext,
) -> OpeningBalanceView:
    partner = db.scalar(select(Partner).where(Partner.id == payload.partner_id).with_for_update())
    if partner is None or not partner.is_active:
        raise TreasuryNotFound("العميل أو المورد غير موجود أو غير نشط")
    originals = list(
        db.scalars(
            select(PartnerOpeningBalance).where(
                PartnerOpeningBalance.partner_id == partner.id,
                PartnerOpeningBalance.reversal_of_id.is_(None),
            )
        )
    )
    if any(
        db.scalar(
            select(PartnerOpeningBalance.id).where(PartnerOpeningBalance.reversal_of_id == row.id)
        )
        is None
        for row in originals
    ):
        raise TreasuryConflict("يوجد رصيد افتتاحي معتمد؛ اعكسه أولًا")
    item = PartnerOpeningBalance(
        entry_number=allocate_document_number(db, "opening_balance"),
        entry_date=payload.entry_date,
        partner_id=partner.id,
        nature=payload.nature,
        amount=money(payload.amount),
        source="manual",
        notes=payload.notes.strip(),
        created_by_id=actor.user.id,
    )
    db.add(item)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="accounts.opening_balance.post",
        entity_type="partner_opening_balance",
        entity_id=str(item.id),
        outcome="success",
        client=client,
    )
    return _opening_view(db, item)


def reverse_opening_balance(
    db: Session,
    *,
    entry_id: UUID,
    reason: str,
    actor: Principal,
    client: ClientContext,
) -> OpeningBalanceView:
    original = db.scalar(
        select(PartnerOpeningBalance)
        .where(
            PartnerOpeningBalance.id == entry_id,
            PartnerOpeningBalance.reversal_of_id.is_(None),
        )
        .with_for_update()
    )
    if original is None:
        raise TreasuryNotFound("قيد الرصيد الافتتاحي غير موجود أو هو قيد عكسي")
    if db.scalar(
        select(PartnerOpeningBalance.id).where(PartnerOpeningBalance.reversal_of_id == original.id)
    ):
        raise TreasuryConflict("تم عكس هذا القيد بالفعل")
    reversal = PartnerOpeningBalance(
        entry_number=allocate_document_number(db, "opening_balance_reversal"),
        entry_date=date.today(),
        partner_id=original.partner_id,
        nature="credit" if original.nature == "debit" else "debit",
        amount=original.amount,
        source="reversal",
        reversal_of_id=original.id,
        notes=f"عكس القيد {original.entry_number} — {reason.strip()}",
        created_by_id=actor.user.id,
    )
    db.add(reversal)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="accounts.opening_balance.reverse",
        entity_type="partner_opening_balance",
        entity_id=str(reversal.id),
        outcome="success",
        client=client,
    )
    return _opening_view(db, reversal)


def _customer_adjustment_view(
    db: Session, item: CustomerAccountAdjustment
) -> CustomerAdjustmentView:
    customer = db.get(Partner, item.customer_id)
    if customer is None:
        raise TreasuryNotFound("العميل المرتبط بالتسوية غير موجود")
    return CustomerAdjustmentView(
        id=item.id,
        adjustment_number=item.adjustment_number,
        adjustment_date=item.adjustment_date,
        customer_id=item.customer_id,
        customer_name_ar=customer.name_ar,
        adjustment_type=item.adjustment_type,  # type: ignore[arg-type]
        amount=item.amount,
        status=item.status,  # type: ignore[arg-type]
        notes=item.notes,
        reversal_reason=item.reversal_reason,
    )


def list_customer_adjustments(db: Session, *, limit: int = 200) -> list[CustomerAdjustmentView]:
    rows = db.scalars(
        select(CustomerAccountAdjustment)
        .order_by(
            CustomerAccountAdjustment.adjustment_date.desc(),
            CustomerAccountAdjustment.id.desc(),
        )
        .limit(limit)
    )
    return [_customer_adjustment_view(db, item) for item in rows]


def post_customer_adjustment(
    db: Session,
    *,
    payload: CustomerAdjustmentRequest,
    actor: Principal,
    client: ClientContext,
) -> CustomerAdjustmentView:
    customer = db.scalar(select(Partner).where(Partner.id == payload.customer_id).with_for_update())
    if customer is None or not customer.is_active or not customer.is_customer:
        raise TreasuryNotFound("العميل غير موجود أو غير نشط")
    item = CustomerAccountAdjustment(
        adjustment_number=allocate_document_number(db, "customer_adjustment"),
        customer_id=customer.id,
        adjustment_type=payload.adjustment_type,
        amount=money(payload.amount),
        status="posted",
        notes=payload.notes.strip(),
        created_by_id=actor.user.id,
        reversal_reason="",
    )
    db.add(item)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="accounts.customer_adjustment.post",
        entity_type="customer_account_adjustment",
        entity_id=str(item.id),
        outcome="success",
        client=client,
    )
    return _customer_adjustment_view(db, item)


def reverse_customer_adjustment(
    db: Session,
    *,
    adjustment_id: UUID,
    reason: str,
    actor: Principal,
    client: ClientContext,
) -> CustomerAdjustmentView:
    item = db.scalar(
        select(CustomerAccountAdjustment)
        .where(CustomerAccountAdjustment.id == adjustment_id)
        .with_for_update()
    )
    if item is None:
        raise TreasuryNotFound("تسوية حساب العميل غير موجودة")
    if item.status == "reversed":
        raise TreasuryConflict("تم عكس تسوية حساب العميل بالفعل")
    item.status = "reversed"
    item.reversed_by_id = actor.user.id
    item.reversed_at = datetime.now(UTC)
    item.reversal_reason = reason.strip()
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="accounts.customer_adjustment.reverse",
        entity_type="customer_account_adjustment",
        entity_id=str(item.id),
        outcome="success",
        client=client,
    )
    return _customer_adjustment_view(db, item)


def _opening_total(db: Session, partner: Partner, partner_type: str) -> Decimal:
    debit = _sum(
        db,
        select(func.coalesce(func.sum(PartnerOpeningBalance.amount), 0)).where(
            PartnerOpeningBalance.partner_id == partner.id,
            PartnerOpeningBalance.nature == "debit",
        ),
    )
    credit = _sum(
        db,
        select(func.coalesce(func.sum(PartnerOpeningBalance.amount), 0)).where(
            PartnerOpeningBalance.partner_id == partner.id,
            PartnerOpeningBalance.nature == "credit",
        ),
    )
    return money(debit - credit if partner_type == "customer" else credit - debit)


def _customer_adjustment_total(db: Session, customer_id: UUID) -> Decimal:
    debit = _sum(
        db,
        select(func.coalesce(func.sum(CustomerAccountAdjustment.amount), 0)).where(
            CustomerAccountAdjustment.customer_id == customer_id,
            CustomerAccountAdjustment.adjustment_type == "debit",
            CustomerAccountAdjustment.status == "posted",
        ),
    )
    credit = _sum(
        db,
        select(func.coalesce(func.sum(CustomerAccountAdjustment.amount), 0)).where(
            CustomerAccountAdjustment.customer_id == customer_id,
            CustomerAccountAdjustment.adjustment_type == "credit",
            CustomerAccountAdjustment.status == "posted",
        ),
    )
    return money(debit - credit)


def list_partner_balances(db: Session, *, partner_type: str) -> list[PartnerBalanceView]:
    if partner_type not in {"customer", "supplier"}:
        raise ValueError("نوع الطرف غير صحيح")
    partner_filter = Partner.is_customer if partner_type == "customer" else Partner.is_supplier
    partners = db.scalars(
        select(Partner).where(partner_filter, Partner.is_active.is_(True)).order_by(Partner.name_ar)
    )
    result: list[PartnerBalanceView] = []
    for partner in partners:
        if partner_type == "customer":
            invoices_total = _sum(
                db,
                select(func.coalesce(func.sum(CustomerInvoice.total), 0)).where(
                    CustomerInvoice.customer_id == partner.id,
                    CustomerInvoice.status == "posted",
                ),
            )
            transaction_type = "customer_receipt"
            adjustments = _customer_adjustment_total(db, partner.id)
        else:
            invoices_total = _sum(
                db,
                select(func.coalesce(func.sum(SupplierInvoice.total), 0)).where(
                    SupplierInvoice.supplier_id == partner.id,
                    SupplierInvoice.status == "posted",
                ),
            )
            transaction_type = "supplier_payment"
            adjustments = ZERO
        payments = list(
            db.scalars(
                select(PaymentTransaction).where(
                    PaymentTransaction.partner_id == partner.id,
                    PaymentTransaction.transaction_type == transaction_type,
                    PaymentTransaction.status == "posted",
                )
            )
        )
        movement_total = money(sum((item.amount for item in payments), ZERO))
        allocated_total = ZERO
        for payment in payments:
            allocated_total += _sum(
                db,
                select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
                    PaymentAllocation.payment_transaction_id == payment.id
                ),
            )
        allocated_total = money(allocated_total)
        paid_total = allocated_total
        advances = money(movement_total - allocated_total)
        opening = _opening_total(db, partner, partner_type)
        result.append(
            PartnerBalanceView(
                partner_id=partner.id,
                partner_code=partner.code,
                partner_name_ar=partner.name_ar,
                partner_type=partner_type,  # type: ignore[arg-type]
                opening_balance=opening,
                invoices_total=invoices_total,
                paid_total=paid_total,
                advances=advances,
                adjustments_total=adjustments,
                balance=money(
                    opening + invoices_total + adjustments - paid_total - advances
                ),
            )
        )
    return result


def treasury_summary(db: Session) -> TreasurySummaryView:
    accounts = list_accounts(db)
    customer_balances = list_partner_balances(db, partner_type="customer")
    supplier_balances = list_partner_balances(db, partner_type="supplier")
    payments = list(
        db.scalars(select(PaymentTransaction).where(PaymentTransaction.status == "posted"))
    )
    customer_receipts = money(
        sum(
            (item.amount for item in payments if item.transaction_type == "customer_receipt"),
            ZERO,
        )
    )
    supplier_payments = money(
        sum(
            (item.amount for item in payments if item.transaction_type == "supplier_payment"),
            ZERO,
        )
    )
    return TreasurySummaryView(
        financial_balance=money(sum((item.current_balance for item in accounts), ZERO)),
        receivables=money(sum((item.balance for item in customer_balances), ZERO)),
        payables=money(sum((item.balance for item in supplier_balances), ZERO)),
        customer_receipts=customer_receipts,
        supplier_payments=supplier_payments,
        customer_advances=money(sum((item.advances for item in customer_balances), ZERO)),
        supplier_advances=money(sum((item.advances for item in supplier_balances), ZERO)),
    )


def partner_statement(
    db: Session,
    *,
    partner_id: UUID,
    date_from: date,
    date_to: date,
    partner_type: str | None = None,
) -> PartnerStatementView:
    if date_from > date_to:
        raise ValueError("تاريخ البداية يجب ألا يكون بعد تاريخ النهاية")
    partner = db.get(Partner, partner_id)
    if partner is None:
        raise TreasuryNotFound("العميل أو المورد غير موجود")
    if partner_type is None:
        if partner.is_customer and partner.is_supplier:
            raise TreasuryConflict("حدد هل المطلوب كشف حساب عميل أم مورد")
        partner_type = "customer" if partner.is_customer else "supplier"
    if partner_type not in {"customer", "supplier"}:
        raise ValueError("نوع كشف الحساب غير صحيح")
    if (partner_type == "customer" and not partner.is_customer) or (
        partner_type == "supplier" and not partner.is_supplier
    ):
        raise TreasuryConflict("نوع كشف الحساب لا يطابق بيانات الطرف")
    start = datetime.combine(date_from, time.min, tzinfo=UTC)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
    movements: list[tuple[datetime, str, str, Decimal, Decimal, str]] = []
    opening_entries = db.scalars(
        select(PartnerOpeningBalance).where(PartnerOpeningBalance.partner_id == partner.id)
    )
    for opening_entry in opening_entries:
        at = datetime.combine(opening_entry.entry_date, time.min, tzinfo=UTC)
        debit = opening_entry.amount if opening_entry.nature == "debit" else ZERO
        credit = opening_entry.amount if opening_entry.nature == "credit" else ZERO
        movements.append(
            (
                at,
                opening_entry.entry_number,
                "رصيد افتتاحي",
                debit,
                credit,
                opening_entry.notes,
            )
        )
    if partner_type == "customer":
        invoices = db.scalars(
            select(CustomerInvoice).where(
                CustomerInvoice.customer_id == partner.id,
                CustomerInvoice.status == "posted",
            )
        )
        for sales_invoice in invoices:
            movements.append(
                (
                    _as_utc(sales_invoice.invoice_date),
                    sales_invoice.invoice_number,
                    "فاتورة مبيعات",
                    sales_invoice.total,
                    ZERO,
                    sales_invoice.notes,
                )
            )
        adjustments = db.scalars(
            select(CustomerAccountAdjustment).where(
                CustomerAccountAdjustment.customer_id == partner.id,
                CustomerAccountAdjustment.status == "posted",
            )
        )
        for customer_adjustment in adjustments:
            movements.append(
                (
                    _as_utc(customer_adjustment.adjustment_date),
                    customer_adjustment.adjustment_number,
                    "تسوية حساب عميل",
                    customer_adjustment.amount
                    if customer_adjustment.adjustment_type == "debit"
                    else ZERO,
                    customer_adjustment.amount
                    if customer_adjustment.adjustment_type == "credit"
                    else ZERO,
                    customer_adjustment.notes,
                )
            )
        payment_type = "customer_receipt"
    else:
        invoices = db.scalars(
            select(SupplierInvoice).where(
                SupplierInvoice.supplier_id == partner.id,
                SupplierInvoice.status == "posted",
            )
        )
        for supplier_invoice in invoices:
            at = _as_utc(supplier_invoice.posted_at or supplier_invoice.created_at)
            movements.append(
                (
                    at,
                    supplier_invoice.invoice_number,
                    "فاتورة مشتريات",
                    ZERO,
                    supplier_invoice.total,
                    "",
                )
            )
        payment_type = "supplier_payment"
    payments = db.scalars(
        select(PaymentTransaction).where(
            PaymentTransaction.partner_id == partner.id,
            PaymentTransaction.transaction_type == payment_type,
            PaymentTransaction.status == "posted",
        )
    )
    for payment in payments:
        movements.append(
            (
                _as_utc(payment.transaction_date),
                payment.transaction_number,
                "تحصيل عميل" if partner_type == "customer" else "سداد مورد",
                ZERO if partner_type == "customer" else payment.amount,
                payment.amount if partner_type == "customer" else ZERO,
                payment.notes,
            )
        )
    movements.sort(key=lambda row: (row[0], row[1]))

    def delta(row: tuple[datetime, str, str, Decimal, Decimal, str]) -> Decimal:
        return row[3] - row[4] if partner_type == "customer" else row[4] - row[3]

    opening = money(sum((delta(row) for row in movements if row[0] < start), ZERO))
    running = opening
    lines: list[StatementLineView] = []
    for row in movements:
        if not start <= row[0] < end:
            continue
        running = money(running + delta(row))
        lines.append(
            StatementLineView(
                movement_date=row[0],
                document_number=row[1],
                movement_type=row[2],
                debit=row[3],
                credit=row[4],
                running_balance=running,
                notes=row[5],
            )
        )
    return PartnerStatementView(
        partner_id=partner.id,
        partner_code=partner.code,
        partner_name_ar=partner.name_ar,
        partner_type=partner_type,  # type: ignore[arg-type]
        date_from=date_from,
        date_to=date_to,
        opening_balance=opening,
        closing_balance=running,
        lines=lines,
    )
