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
from app.modules.inventory.service import InsufficientStock, InventoryConflict
from app.modules.returns.schemas import (
    CreateInvoiceReturnRequest,
    CreateRefundRequest,
    InvoiceReturnView,
    RefundView,
    ReturnableInvoiceView,
    ReturnableLineView,
    ReturnOptionsView,
    ReverseRequest,
)
from app.modules.returns.service import (
    ReturnsConflict,
    ReturnsNotFound,
    create_refund,
    create_return,
    get_returnable_lines,
    list_refunds,
    list_returnable_invoices,
    list_returns,
    return_options,
    reverse_refund,
    reverse_return,
)

router = APIRouter(prefix="/returns")
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=12, max_length=120)]


def _read(request: Request, db: DatabaseSession, principal: CurrentPrincipal) -> None:
    enforce_permission(request, db, principal, PermissionCode.RETURNS_READ)


def _manage(request: Request, db: DatabaseSession, principal: CurrentPrincipal) -> None:
    enforce_permission(request, db, principal, PermissionCode.RETURNS_MANAGE)
    enforce_csrf(request, db, principal)


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, ReturnsNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, (ReturnsConflict, InsufficientStock, InventoryConflict, IntegrityError)):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            str(exc) if not isinstance(exc, IntegrityError) else "تعارضت العملية مع بيانات مسجلة",
        )
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


HandledReturnsError = (
    ReturnsNotFound,
    ReturnsConflict,
    InsufficientStock,
    InventoryConflict,
    IntegrityError,
    ValueError,
)


@router.get("/options", response_model=ReturnOptionsView)
def options(
    request: Request, principal: CurrentPrincipal, db: DatabaseSession
) -> ReturnOptionsView:
    _read(request, db, principal)
    return return_options(db)


@router.get("/invoices", response_model=list[ReturnableInvoiceView])
def invoices(
    return_type: Annotated[str, Query(pattern="^(sales|purchase)$")],
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    partner_id: UUID | None = None,
) -> list[ReturnableInvoiceView]:
    _read(request, db, principal)
    return list_returnable_invoices(db, return_type=return_type, partner_id=partner_id)


@router.get(
    "/invoices/{return_type}/{invoice_id}/lines",
    response_model=list[ReturnableLineView],
)
def invoice_lines(
    return_type: str,
    invoice_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[ReturnableLineView]:
    _read(request, db, principal)
    try:
        return get_returnable_lines(db, return_type=return_type, invoice_id=invoice_id)
    except (ReturnsNotFound, ValueError) as exc:
        raise _translate(exc) from exc


@router.get("/documents", response_model=list[InvoiceReturnView])
def documents(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 250,
) -> list[InvoiceReturnView]:
    _read(request, db, principal)
    return list_returns(db, limit=limit)


@router.post("/documents", response_model=InvoiceReturnView, status_code=status.HTTP_201_CREATED)
def add_document(
    payload: CreateInvoiceReturnRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> InvoiceReturnView:
    _manage(request, db, principal)
    try:
        result = create_return(
            db,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except HandledReturnsError as exc:
        db.rollback()
        raise _translate(exc) from exc


@router.post("/documents/{return_id}/reverse", response_model=InvoiceReturnView)
def reverse_document(
    return_id: UUID,
    payload: ReverseRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> InvoiceReturnView:
    _manage(request, db, principal)
    try:
        result = reverse_return(
            db,
            return_id=return_id,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except HandledReturnsError as exc:
        db.rollback()
        raise _translate(exc) from exc


@router.get("/refunds", response_model=list[RefundView])
def refunds(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 250,
) -> list[RefundView]:
    _read(request, db, principal)
    return list_refunds(db, limit=limit)


@router.post("/refunds", response_model=RefundView, status_code=status.HTTP_201_CREATED)
def add_refund(
    payload: CreateRefundRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> RefundView:
    _manage(request, db, principal)
    try:
        result = create_refund(
            db,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except HandledReturnsError as exc:
        db.rollback()
        raise _translate(exc) from exc


@router.post("/refunds/{refund_id}/reverse", response_model=RefundView)
def reverse_refund_document(
    refund_id: UUID,
    payload: ReverseRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> RefundView:
    _manage(request, db, principal)
    try:
        result = reverse_refund(
            db,
            refund_id=refund_id,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except HandledReturnsError as exc:
        db.rollback()
        raise _translate(exc) from exc
