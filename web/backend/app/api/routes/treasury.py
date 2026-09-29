from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import (
    CurrentPrincipal,
    DatabaseSession,
    client_context,
    enforce_csrf,
    enforce_permission,
)
from app.modules.identity.permissions import PermissionCode
from app.modules.master_data.models import Partner
from app.modules.returns.schemas import ReturnableInvoiceView
from app.modules.returns.service import list_returnable_invoices
from app.modules.treasury.models import PaymentAllocation, PaymentTransaction
from app.modules.treasury.schemas import (
    CustomerAdjustmentView,
    FinancialAccountRequest,
    FinancialAccountView,
    FinancialAdjustmentRequest,
    FinancialAdjustmentView,
    OpeningBalanceRequest,
    OpeningBalanceView,
    OpenInvoiceView,
    OpenOrderView,
    PartnerBalanceView,
    PartnerStatementView,
    PaymentView,
    PostPaymentRequest,
    ReverseRequest,
    TransferRequest,
    TransferView,
    TreasuryOptionsView,
    TreasurySummaryView,
    UpdateFinancialAccountRequest,
)
from app.modules.treasury.service import (
    TreasuryConflict,
    TreasuryNotFound,
    create_account,
    list_accounts,
    list_customer_adjustments,
    list_open_invoices,
    list_open_orders,
    list_opening_balances,
    list_partner_balances,
    list_payments,
    list_transfers,
    partner_statement,
    post_financial_adjustment,
    post_opening_balance,
    post_payment,
    post_transfer,
    reverse_customer_adjustment,
    reverse_financial_adjustment,
    reverse_opening_balance,
    reverse_payment,
    reverse_transfer,
    treasury_options,
    treasury_summary,
    update_account,
)

router = APIRouter(prefix="/accounts")


def _payment_status(*, remaining: Decimal, net_total: Decimal, effective_paid: Decimal) -> str:
    if remaining == 0 and net_total > 0:
        return "paid"
    if effective_paid > 0:
        return "partial"
    return "unpaid"
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=12, max_length=120)]


class AccountInvoiceView(ReturnableInvoiceView):
    partner_phone: str
    payment_methods: list[str]
    invoice_status: str
    delivery_return_status: str
    payment_status: str


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TreasuryNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, (TreasuryConflict, IntegrityError)):
        detail = str(exc) if isinstance(exc, TreasuryConflict) else "تعارضت العملية مع بيانات مسجلة"
        return HTTPException(status.HTTP_409_CONFLICT, detail)
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


def _read(request: Request, db: DatabaseSession, principal: CurrentPrincipal) -> None:
    enforce_permission(request, db, principal, PermissionCode.ACCOUNTS_READ)


def _manage(request: Request, db: DatabaseSession, principal: CurrentPrincipal) -> None:
    enforce_permission(request, db, principal, PermissionCode.ACCOUNTS_MANAGE)
    enforce_csrf(request, db, principal)


@router.get("/options")
def options(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> TreasuryOptionsView:
    _read(request, db, principal)
    return treasury_options(db)


@router.get("/financial-accounts")
def accounts(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    include_inactive: bool = False,
) -> list[FinancialAccountView]:
    _read(request, db, principal)
    return list_accounts(db, include_inactive=include_inactive)


@router.post(
    "/financial-accounts",
    status_code=status.HTTP_201_CREATED,
)
def add_account(
    payload: FinancialAccountRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> FinancialAccountView:
    _manage(request, db, principal)
    try:
        result = create_account(
            db, payload=payload, actor=principal, client=client_context(request)
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.put("/financial-accounts/{account_id}")
def edit_account(
    account_id: UUID,
    payload: UpdateFinancialAccountRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> FinancialAccountView:
    _manage(request, db, principal)
    try:
        result = update_account(
            db,
            account_id=account_id,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.get("/payments")
def payments(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[PaymentView]:
    _read(request, db, principal)
    return list_payments(db, limit=limit)


@router.post("/payments", status_code=status.HTTP_201_CREATED)
def add_payment(
    payload: PostPaymentRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> PaymentView:
    _manage(request, db, principal)
    try:
        result = post_payment(
            db,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post("/payments/{payment_id}/reversal")
def undo_payment(
    payment_id: UUID,
    payload: ReverseRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> PaymentView:
    _manage(request, db, principal)
    try:
        result = reverse_payment(
            db,
            payment_id=payment_id,
            reason=payload.reason,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.get("/open-invoices")
def open_invoices(
    transaction_type: Annotated[str, Query(pattern="^customer_receipt$")],
    partner_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[OpenInvoiceView]:
    _read(request, db, principal)
    try:
        return list_open_invoices(db, transaction_type=transaction_type, partner_id=partner_id)
    except (TreasuryNotFound, ValueError) as exc:
        raise _translate_error(exc) from exc


def _invoice_payment_methods(
    db: DatabaseSession, *, invoice_type: str, invoice_id: UUID
) -> list[str]:
    direct_column = (
        PaymentTransaction.customer_invoice_id
        if invoice_type == "sales"
        else PaymentTransaction.supplier_invoice_id
    )
    allocation_column = (
        PaymentAllocation.customer_invoice_id
        if invoice_type == "sales"
        else PaymentAllocation.supplier_invoice_id
    )
    return list(
        db.scalars(
            select(PaymentTransaction.payment_method)
            .outerjoin(
                PaymentAllocation,
                PaymentAllocation.payment_transaction_id == PaymentTransaction.id,
            )
            .where(
                PaymentTransaction.status == "posted",
                or_(direct_column == invoice_id, allocation_column == invoice_id),
            )
            .distinct()
            .order_by(PaymentTransaction.payment_method)
        )
    )


def _delivery_return_status(*, return_status: str, invoice_type: str) -> str:
    labels = {"full": "مرتجع كلي", "partial": "مرتجع جزئي"}
    return labels.get(return_status, "مُسلَّمة" if invoice_type == "sales" else "مستلمة")


@router.get("/invoices")
def all_invoices(
    invoice_type: Annotated[str, Query(pattern="^(sales|purchase)$")],
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[AccountInvoiceView]:
    _read(request, db, principal)
    rows = list_returnable_invoices(db, return_type=invoice_type)
    result: list[AccountInvoiceView] = []
    for row in rows:
        partner = db.get(Partner, row.partner_id)
        effective_paid = max(Decimal("0"), row.paid - row.refunded)
        payment_status = _payment_status(
            remaining=row.remaining,
            net_total=row.net_total,
            effective_paid=effective_paid,
        )
        result.append(
            AccountInvoiceView(
                **row.model_dump(),
                partner_phone=partner.phone if partner is not None else "",
                payment_methods=_invoice_payment_methods(
                    db,
                    invoice_type=invoice_type,
                    invoice_id=row.id,
                ),
                invoice_status="posted",
                delivery_return_status=_delivery_return_status(
                    return_status=row.return_status,
                    invoice_type=invoice_type,
                ),
                payment_status=payment_status,
            )
        )
    return result


@router.get("/open-orders")
def open_orders(
    transaction_type: Annotated[str, Query(pattern="^(customer_receipt|supplier_payment)$")],
    partner_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[OpenOrderView]:
    _read(request, db, principal)
    try:
        return list_open_orders(db, transaction_type=transaction_type, partner_id=partner_id)
    except (TreasuryNotFound, ValueError) as exc:
        raise _translate_error(exc) from exc


@router.get("/transfers")
def transfers(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[TransferView]:
    _read(request, db, principal)
    return list_transfers(db)


@router.post("/transfers", status_code=status.HTTP_201_CREATED)
def add_transfer(
    payload: TransferRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> TransferView:
    _manage(request, db, principal)
    try:
        result = post_transfer(
            db,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post("/transfers/{transfer_id}/reversal")
def undo_transfer(
    transfer_id: UUID,
    payload: ReverseRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> TransferView:
    _manage(request, db, principal)
    try:
        result = reverse_transfer(
            db,
            transfer_id=transfer_id,
            reason=payload.reason,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post(
    "/financial-adjustments",
    status_code=status.HTTP_201_CREATED,
)
def add_financial_adjustment(
    payload: FinancialAdjustmentRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> FinancialAdjustmentView:
    _manage(request, db, principal)
    try:
        result = post_financial_adjustment(
            db,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post(
    "/financial-adjustments/{adjustment_id}/reversal",
)
def undo_financial_adjustment(
    adjustment_id: UUID,
    payload: ReverseRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> FinancialAdjustmentView:
    _manage(request, db, principal)
    try:
        result = reverse_financial_adjustment(
            db,
            adjustment_id=adjustment_id,
            reason=payload.reason,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.get("/opening-balances")
def opening_balances(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[OpeningBalanceView]:
    _read(request, db, principal)
    return list_opening_balances(db)


@router.post(
    "/opening-balances",
    status_code=status.HTTP_201_CREATED,
)
def add_opening_balance(
    payload: OpeningBalanceRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> OpeningBalanceView:
    _manage(request, db, principal)
    try:
        result = post_opening_balance(
            db,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post("/opening-balances/{entry_id}/reversal")
def undo_opening_balance(
    entry_id: UUID,
    payload: ReverseRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> OpeningBalanceView:
    _manage(request, db, principal)
    try:
        result = reverse_opening_balance(
            db,
            entry_id=entry_id,
            reason=payload.reason,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.get("/customer-adjustments")
def customer_adjustments(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[CustomerAdjustmentView]:
    _read(request, db, principal)
    return list_customer_adjustments(db)


@router.post(
    "/customer-adjustments/{adjustment_id}/reversal",
)
def undo_customer_adjustment(
    adjustment_id: UUID,
    payload: ReverseRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> CustomerAdjustmentView:
    _manage(request, db, principal)
    try:
        result = reverse_customer_adjustment(
            db,
            adjustment_id=adjustment_id,
            reason=payload.reason,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.get("/summary")
def summary(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> TreasurySummaryView:
    _read(request, db, principal)
    return treasury_summary(db)


@router.get("/partner-balances")
def partner_balances(
    partner_type: Annotated[str, Query(pattern="^(customer|supplier)$")],
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[PartnerBalanceView]:
    _read(request, db, principal)
    return list_partner_balances(db, partner_type=partner_type)


@router.get("/partners/{partner_id}/statement")
def statement(
    partner_id: UUID,
    date_from: date,
    date_to: date,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    partner_type: Annotated[str | None, Query(pattern="^customer$")] = "customer",
) -> PartnerStatementView:
    _read(request, db, principal)
    try:
        return partner_statement(
            db,
            partner_id=partner_id,
            date_from=date_from,
            date_to=date_to,
            partner_type=partner_type,
        )
    except (TreasuryNotFound, TreasuryConflict, ValueError) as exc:
        raise _translate_error(exc) from exc
