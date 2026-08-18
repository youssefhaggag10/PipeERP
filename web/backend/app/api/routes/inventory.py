from typing import Annotated

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
from app.modules.inventory.schemas import (
    BalanceView,
    IssueRequest,
    ReceiptRequest,
    TransactionView,
)
from app.modules.inventory.service import (
    InsufficientStock,
    InventoryNotFound,
    list_balances,
    list_transactions,
    post_issue,
    post_receipt,
)

router = APIRouter(prefix="/inventory")


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InventoryNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, (InsufficientStock, IntegrityError)):
        detail = str(exc) if isinstance(exc, InsufficientStock) else "تعارضت الحركة مع عملية أخرى"
        return HTTPException(status.HTTP_409_CONFLICT, detail)
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("/balances", response_model=list[BalanceView])
def balances(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[BalanceView]:
    enforce_permission(request, db, principal, PermissionCode.INVENTORY_READ)
    return [BalanceView.model_validate(item) for item in list_balances(db)]


@router.get("/transactions", response_model=list[TransactionView])
def transactions(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[TransactionView]:
    enforce_permission(request, db, principal, PermissionCode.INVENTORY_READ)
    return [TransactionView.model_validate(item) for item in list_transactions(db, limit=limit)]


@router.post("/receipts", response_model=TransactionView, status_code=status.HTTP_201_CREATED)
def receipt(
    payload: ReceiptRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=12, max_length=120)],
) -> TransactionView:
    enforce_permission(request, db, principal, PermissionCode.INVENTORY_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        item = post_receipt(
            db,
            payload=payload,
            idempotency_key=idempotency_key,
            actor_user_id=principal.user.id,
            client=client_context(request),
        )
    except (InventoryNotFound, InsufficientStock, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = TransactionView.model_validate(item)
    db.commit()
    return view


@router.post("/issues", response_model=TransactionView, status_code=status.HTTP_201_CREATED)
def issue(
    payload: IssueRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=12, max_length=120)],
) -> TransactionView:
    enforce_permission(request, db, principal, PermissionCode.INVENTORY_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        item = post_issue(
            db,
            payload=payload,
            idempotency_key=idempotency_key,
            actor_user_id=principal.user.id,
            client=client_context(request),
        )
    except (InventoryNotFound, InsufficientStock, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = TransactionView.model_validate(item)
    db.commit()
    return view
