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
from app.modules.purchasing.schemas import (
    ApprovePurchaseOrderRequest,
    CreatePurchaseOrderRequest,
    CreateSupplierInvoiceRequest,
    PostPurchaseReceiptRequest,
    PurchaseOptionsView,
    PurchaseOrderView,
    PurchaseReceiptView,
    ReceivePurchaseOrderRequest,
    ReversePurchaseReceiptRequest,
    ReverseSupplierInvoiceRequest,
    SupplierInvoiceView,
)
from app.modules.purchasing.service import (
    PurchasingConflict,
    PurchasingNotFound,
    approve_purchase_order,
    create_purchase_order,
    create_supplier_invoice,
    get_purchase_order,
    list_purchase_orders,
    list_purchase_receipts,
    post_purchase_receipt,
    purchase_options,
    receive_purchase_order,
    reverse_purchase_receipt,
    reverse_supplier_invoice,
)

router = APIRouter(prefix="/purchases")


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PurchasingNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, (PurchasingConflict, IntegrityError)):
        detail = (
            str(exc) if isinstance(exc, PurchasingConflict) else "تعارضت العملية مع بيانات مسجلة"
        )
        return HTTPException(status.HTTP_409_CONFLICT, detail)
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("/options", response_model=PurchaseOptionsView)
def options(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> PurchaseOptionsView:
    enforce_permission(request, db, principal, PermissionCode.PURCHASES_READ)
    return purchase_options(db)


@router.get("/orders", response_model=list[PurchaseOrderView])
def orders(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[PurchaseOrderView]:
    enforce_permission(request, db, principal, PermissionCode.PURCHASES_READ)
    return list_purchase_orders(db, limit=limit)


@router.get("/orders/{order_id}", response_model=PurchaseOrderView)
def order(
    order_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> PurchaseOrderView:
    enforce_permission(request, db, principal, PermissionCode.PURCHASES_READ)
    try:
        return get_purchase_order(db, order_id)
    except PurchasingNotFound as exc:
        raise _translate_error(exc) from exc


@router.get("/orders/{order_id}/receipts", response_model=list[PurchaseReceiptView])
def receipts(
    order_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[PurchaseReceiptView]:
    enforce_permission(request, db, principal, PermissionCode.PURCHASES_READ)
    try:
        return list_purchase_receipts(db, order_id=order_id)
    except PurchasingNotFound as exc:
        raise _translate_error(exc) from exc


@router.post("/orders", response_model=PurchaseOrderView, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: CreatePurchaseOrderRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> PurchaseOrderView:
    enforce_permission(request, db, principal, PermissionCode.PURCHASES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        view = create_purchase_order(
            db, payload=payload, actor=principal, client=client_context(request)
        )
        db.commit()
        return view
    except (PurchasingNotFound, PurchasingConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post("/orders/{order_id}/approval", response_model=PurchaseOrderView)
def approve_order(
    order_id: UUID,
    payload: ApprovePurchaseOrderRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> PurchaseOrderView:
    enforce_permission(request, db, principal, PermissionCode.PURCHASES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        view = approve_purchase_order(
            db,
            order_id=order_id,
            version=payload.version,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return view
    except (PurchasingNotFound, PurchasingConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post("/orders/{order_id}/receive", response_model=PurchaseOrderView)
def receive_full_order(
    order_id: UUID,
    payload: ReceivePurchaseOrderRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=12, max_length=120)],
) -> PurchaseOrderView:
    enforce_permission(request, db, principal, PermissionCode.PURCHASES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        view = receive_purchase_order(
            db,
            order_id=order_id,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return view
    except (PurchasingNotFound, PurchasingConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post(
    "/orders/{order_id}/receipts",
    response_model=PurchaseReceiptView,
    status_code=status.HTTP_201_CREATED,
)
def receive_order(
    order_id: UUID,
    payload: PostPurchaseReceiptRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=12, max_length=120)],
) -> PurchaseReceiptView:
    enforce_permission(request, db, principal, PermissionCode.PURCHASES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        view = post_purchase_receipt(
            db,
            order_id=order_id,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return view
    except (PurchasingNotFound, PurchasingConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post("/receipts/{receipt_id}/reversal", response_model=PurchaseReceiptView)
def reverse_receipt(
    receipt_id: UUID,
    payload: ReversePurchaseReceiptRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=12, max_length=120)],
) -> PurchaseReceiptView:
    enforce_permission(request, db, principal, PermissionCode.PURCHASES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        view = reverse_purchase_receipt(
            db,
            receipt_id=receipt_id,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return view
    except (PurchasingNotFound, PurchasingConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post(
    "/orders/{order_id}/supplier-invoice",
    response_model=SupplierInvoiceView,
    status_code=status.HTTP_201_CREATED,
)
def supplier_invoice(
    order_id: UUID,
    payload: CreateSupplierInvoiceRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> SupplierInvoiceView:
    enforce_permission(request, db, principal, PermissionCode.PURCHASES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        view = create_supplier_invoice(
            db,
            order_id=order_id,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return view
    except (PurchasingNotFound, PurchasingConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post(
    "/supplier-invoices/{invoice_id}/reversal",
    response_model=SupplierInvoiceView,
)
def supplier_invoice_reversal(
    invoice_id: UUID,
    payload: ReverseSupplierInvoiceRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> SupplierInvoiceView:
    enforce_permission(request, db, principal, PermissionCode.PURCHASES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        view = reverse_supplier_invoice(
            db,
            invoice_id=invoice_id,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return view
    except (PurchasingNotFound, PurchasingConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
