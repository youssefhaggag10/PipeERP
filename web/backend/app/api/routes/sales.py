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
from app.modules.sales.schemas import (
    CancelOrderRequest,
    CreatePieceOrderRequest,
    CreateQuotationRequest,
    CreateWeightSaleRequest,
    DeliverOrderRequest,
    QuotationView,
    ReverseDeliveryRequest,
    SalesOptionsView,
    SalesOrderView,
)
from app.modules.sales.service import (
    SalesConflict,
    SalesNotFound,
    cancel_sales_order,
    create_piece_order,
    create_quotation,
    create_weight_sale,
    deliver_sales_order,
    get_delivery_billing_method,
    get_sales_order,
    list_quotations,
    list_sales_orders,
    reverse_sales_delivery,
    sales_options,
)

router = APIRouter(prefix="/sales")


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, SalesNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, (SalesConflict, IntegrityError)):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            str(exc) if isinstance(exc, SalesConflict) else "تعارضت العملية مع بيانات مسجلة",
        )
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("/options", response_model=SalesOptionsView)
def options(request: Request, principal: CurrentPrincipal, db: DatabaseSession) -> SalesOptionsView:
    if not (
        PermissionCode.SALES_READ in principal.permissions
        or PermissionCode.WEIGHT_SALES_READ in principal.permissions
    ):
        enforce_permission(request, db, principal, PermissionCode.SALES_READ)
    return sales_options(db)


@router.get("/orders", response_model=list[SalesOrderView])
def orders(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[SalesOrderView]:
    if not (
        PermissionCode.SALES_READ in principal.permissions
        or PermissionCode.WEIGHT_SALES_READ in principal.permissions
    ):
        enforce_permission(request, db, principal, PermissionCode.SALES_READ)
    values = list_sales_orders(db, limit=limit)
    can_piece = PermissionCode.SALES_READ in principal.permissions
    can_weight = PermissionCode.WEIGHT_SALES_READ in principal.permissions
    return [
        item
        for item in values
        if (item.billing_method == "piece" and can_piece)
        or (item.billing_method == "weight" and can_weight)
    ]


@router.get("/orders/{order_id}", response_model=SalesOrderView)
def order(
    order_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> SalesOrderView:
    if not (
        PermissionCode.SALES_READ in principal.permissions
        or PermissionCode.WEIGHT_SALES_READ in principal.permissions
    ):
        enforce_permission(request, db, principal, PermissionCode.SALES_READ)
    try:
        view = get_sales_order(db, order_id)
        permission = (
            PermissionCode.WEIGHT_SALES_READ
            if view.billing_method == "weight"
            else PermissionCode.SALES_READ
        )
        enforce_permission(request, db, principal, permission)
        return view
    except SalesNotFound as exc:
        raise _translate(exc) from exc


@router.post("/orders", response_model=SalesOrderView, status_code=status.HTTP_201_CREATED)
def create_piece(
    payload: CreatePieceOrderRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> SalesOrderView:
    enforce_permission(request, db, principal, PermissionCode.SALES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        view = create_piece_order(
            db, payload=payload, actor=principal, client=client_context(request)
        )
        db.commit()
        return view
    except (SalesNotFound, SalesConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate(exc) from exc


@router.post("/weight-orders", response_model=SalesOrderView, status_code=status.HTTP_201_CREATED)
def create_weight(
    payload: CreateWeightSaleRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> SalesOrderView:
    enforce_permission(request, db, principal, PermissionCode.WEIGHT_SALES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        view = create_weight_sale(
            db, payload=payload, actor=principal, client=client_context(request)
        )
        db.commit()
        return view
    except (SalesNotFound, SalesConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate(exc) from exc


@router.post("/orders/{order_id}/delivery", response_model=SalesOrderView)
def deliver(
    order_id: UUID,
    payload: DeliverOrderRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=12, max_length=120)],
) -> SalesOrderView:
    try:
        order_view = get_sales_order(db, order_id)
        permission = (
            PermissionCode.WEIGHT_SALES_MANAGE
            if order_view.billing_method == "weight"
            else PermissionCode.SALES_MANAGE
        )
        enforce_permission(request, db, principal, permission)
        enforce_csrf(request, db, principal)
        view = deliver_sales_order(
            db,
            order_id=order_id,
            version=payload.version,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return view
    except (SalesNotFound, SalesConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate(exc) from exc


@router.post("/orders/{order_id}/cancellation", response_model=SalesOrderView)
def cancel_order(
    order_id: UUID,
    payload: CancelOrderRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> SalesOrderView:
    try:
        order_view = get_sales_order(db, order_id)
        permission = (
            PermissionCode.WEIGHT_SALES_MANAGE
            if order_view.billing_method == "weight"
            else PermissionCode.SALES_MANAGE
        )
        enforce_permission(request, db, principal, permission)
        enforce_csrf(request, db, principal)
        view = cancel_sales_order(
            db,
            order_id=order_id,
            version=payload.version,
            reason=payload.reason,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return view
    except (SalesNotFound, SalesConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate(exc) from exc


@router.post("/deliveries/{delivery_id}/reversal", response_model=SalesOrderView)
def reverse_delivery(
    delivery_id: UUID,
    payload: ReverseDeliveryRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=12, max_length=120)],
) -> SalesOrderView:
    try:
        billing_method = get_delivery_billing_method(db, delivery_id)
        permission = (
            PermissionCode.WEIGHT_SALES_MANAGE
            if billing_method == "weight"
            else PermissionCode.SALES_MANAGE
        )
        enforce_permission(request, db, principal, permission)
        enforce_csrf(request, db, principal)
        view = reverse_sales_delivery(
            db,
            delivery_id=delivery_id,
            reason=payload.reason,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return view
    except (SalesNotFound, SalesConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate(exc) from exc


@router.get("/quotations", response_model=list[QuotationView])
def quotations(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[QuotationView]:
    enforce_permission(request, db, principal, PermissionCode.SALES_READ)
    return list_quotations(db, limit=limit)


@router.post("/quotations", response_model=QuotationView, status_code=status.HTTP_201_CREATED)
def quotation(
    payload: CreateQuotationRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> QuotationView:
    enforce_permission(request, db, principal, PermissionCode.SALES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        view = create_quotation(
            db, payload=payload, actor=principal, client=client_context(request)
        )
        db.commit()
        return view
    except (SalesNotFound, SalesConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate(exc) from exc
