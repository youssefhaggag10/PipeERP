from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import (
    CurrentPrincipal,
    DatabaseSession,
    client_context,
    enforce_csrf,
    enforce_permission,
)
from app.modules.identity.permissions import PermissionCode
from app.modules.treasury.schemas import (
    CustomerAdjustmentRequest,
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
    post_customer_adjustment,
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
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=12, max_length=120)]


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


@router.get("/options", response_model=TreasuryOptionsView)
def options(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> TreasuryOptionsView:
    _read(request, db, principal)
    return treasury_options(db)


@router.get("/financial-accounts", response_model=list[FinancialAccountView])
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
    response_model=FinancialAccountView,
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


@router.put("/financial-accounts/{account_id}", response_model=FinancialAccountView)
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


@router.get("/payments", response_model=list[PaymentView])
def payments(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[PaymentView]:
    _read(request, db, principal)
    return list_payments(db, limit=limit)


@router.post("/payments", response_model=PaymentView, status_code=status.HTTP_201_CREATED)
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


@router.post("/payments/{payment_id}/reversal", response_model=PaymentView)
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


@router.get("/open-invoices", response_model=list[OpenInvoiceView])
def open_invoices(
    transaction_type: Annotated[str, Query(pattern="^(customer_receipt|supplier_payment)$")],
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


@router.get("/open-orders", response_model=list[OpenOrderView])
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


@router.get("/transfers", response_model=list[TransferView])
def transfers(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[TransferView]:
    _read(request, db, principal)
    return list_transfers(db)


@router.post("/transfers", response_model=TransferView, status_code=status.HTTP_201_CREATED)
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


@router.post("/transfers/{transfer_id}/reversal", response_model=TransferView)
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
    response_model=FinancialAdjustmentView,
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
    response_model=FinancialAdjustmentView,
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


@router.get("/opening-balances", response_model=list[OpeningBalanceView])
def opening_balances(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[OpeningBalanceView]:
    _read(request, db, principal)
    return list_opening_balances(db)


@router.post(
    "/opening-balances",
    response_model=OpeningBalanceView,
    status_code=status.HTTP_201_CREATED,
)
def add_opening_balance(
    payload: OpeningBalanceRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> OpeningBalanceView:
    _manage(request, db, principal)
    try:
        result = post_opening_balance(
            db, payload=payload, actor=principal, client=client_context(request)
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post("/opening-balances/{entry_id}/reversal", response_model=OpeningBalanceView)
def undo_opening_balance(
    entry_id: UUID,
    payload: ReverseRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> OpeningBalanceView:
    _manage(request, db, principal)
    try:
        result = reverse_opening_balance(
            db,
            entry_id=entry_id,
            reason=payload.reason,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.get("/customer-adjustments", response_model=list[CustomerAdjustmentView])
def customer_adjustments(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[CustomerAdjustmentView]:
    _read(request, db, principal)
    return list_customer_adjustments(db)


@router.post(
    "/customer-adjustments",
    response_model=CustomerAdjustmentView,
    status_code=status.HTTP_201_CREATED,
)
def add_customer_adjustment(
    payload: CustomerAdjustmentRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> CustomerAdjustmentView:
    _manage(request, db, principal)
    try:
        result = post_customer_adjustment(
            db, payload=payload, actor=principal, client=client_context(request)
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post(
    "/customer-adjustments/{adjustment_id}/reversal",
    response_model=CustomerAdjustmentView,
)
def undo_customer_adjustment(
    adjustment_id: UUID,
    payload: ReverseRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> CustomerAdjustmentView:
    _manage(request, db, principal)
    try:
        result = reverse_customer_adjustment(
            db,
            adjustment_id=adjustment_id,
            reason=payload.reason,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (TreasuryNotFound, TreasuryConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.get("/summary", response_model=TreasurySummaryView)
def summary(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> TreasurySummaryView:
    _read(request, db, principal)
    return treasury_summary(db)


@router.get("/partner-balances", response_model=list[PartnerBalanceView])
def partner_balances(
    partner_type: Annotated[str, Query(pattern="^(customer|supplier)$")],
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[PartnerBalanceView]:
    _read(request, db, principal)
    return list_partner_balances(db, partner_type=partner_type)


@router.get("/partners/{partner_id}/statement", response_model=PartnerStatementView)
def statement(
    partner_id: UUID,
    date_from: date,
    date_to: date,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    partner_type: Annotated[str | None, Query(pattern="^(customer|supplier)$")] = None,
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
