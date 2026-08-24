from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
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
from app.modules.manufacturing.schemas import (
    CancelManufacturingOrderRequest,
    CompleteManufacturingOrderRequest,
    CreateManufacturingOrderRequest,
    CreateRecipeRequest,
    ManufacturingOptionsView,
    ManufacturingOrderView,
    MaterialAvailabilityView,
    RecipeView,
    ReplanView,
    TransitionRequest,
    UpdateManufacturingOrderRequest,
    UpdateRecipeRequest,
)
from app.modules.manufacturing.service import (
    ManufacturingConflict,
    ManufacturingNotFound,
    apply_replan,
    cancel_order,
    complete_order,
    create_order,
    create_recipe,
    delete_draft_order,
    get_order,
    get_recipe,
    list_orders,
    list_recipes,
    manufacturing_options,
    preview_material_availability,
    preview_replan,
    start_order,
    update_order,
    update_recipe,
)

router = APIRouter(prefix="/manufacturing")
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=12, max_length=120)]


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ManufacturingNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(
        exc,
        (ManufacturingConflict, InventoryConflict, InsufficientStock, IntegrityError),
    ):
        detail = (
            str(exc)
            if not isinstance(exc, IntegrityError)
            else "تعارضت العملية مع بيانات مسجلة"
        )
        return HTTPException(status.HTTP_409_CONFLICT, detail)
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


def _read(request: Request, db: DatabaseSession, principal: CurrentPrincipal) -> None:
    enforce_permission(request, db, principal, PermissionCode.MANUFACTURING_READ)


def _manage(request: Request, db: DatabaseSession, principal: CurrentPrincipal) -> None:
    enforce_permission(request, db, principal, PermissionCode.MANUFACTURING_MANAGE)
    enforce_csrf(request, db, principal)


@router.get("/options", response_model=ManufacturingOptionsView)
def options(
    request: Request, principal: CurrentPrincipal, db: DatabaseSession
) -> ManufacturingOptionsView:
    _read(request, db, principal)
    return manufacturing_options(db)


@router.get("/recipes", response_model=list[RecipeView])
def recipes(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    include_inactive: bool = False,
) -> list[RecipeView]:
    _read(request, db, principal)
    return list_recipes(db, include_inactive=include_inactive)


@router.get("/recipes/{recipe_id}", response_model=RecipeView)
def recipe(
    recipe_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> RecipeView:
    _read(request, db, principal)
    try:
        return get_recipe(db, recipe_id)
    except ManufacturingNotFound as exc:
        raise _translate_error(exc) from exc


@router.post("/recipes", response_model=RecipeView, status_code=status.HTTP_201_CREATED)
def add_recipe(
    payload: CreateRecipeRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> RecipeView:
    _manage(request, db, principal)
    try:
        result = create_recipe(
            db, payload=payload, actor=principal, client=client_context(request)
        )
        db.commit()
        return result
    except (ManufacturingNotFound, ManufacturingConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.put("/recipes/{recipe_id}", response_model=RecipeView)
def edit_recipe(
    recipe_id: UUID,
    payload: UpdateRecipeRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> RecipeView:
    _manage(request, db, principal)
    try:
        result = update_recipe(
            db,
            recipe_id=recipe_id,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (ManufacturingNotFound, ManufacturingConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.get("/orders", response_model=list[ManufacturingOrderView])
def orders(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[ManufacturingOrderView]:
    _read(request, db, principal)
    return list_orders(db, limit=limit)


@router.get("/orders/{order_id}", response_model=ManufacturingOrderView)
def order(
    order_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> ManufacturingOrderView:
    _read(request, db, principal)
    try:
        return get_order(db, order_id)
    except ManufacturingNotFound as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/orders", response_model=ManufacturingOrderView, status_code=status.HTTP_201_CREATED
)
def add_order(
    payload: CreateManufacturingOrderRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> ManufacturingOrderView:
    _manage(request, db, principal)
    try:
        result = create_order(
            db,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (ManufacturingNotFound, ManufacturingConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.put("/orders/{order_id}", response_model=ManufacturingOrderView)
def edit_order(
    order_id: UUID,
    payload: UpdateManufacturingOrderRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> ManufacturingOrderView:
    _manage(request, db, principal)
    try:
        result = update_order(
            db,
            order_id=order_id,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (ManufacturingNotFound, ManufacturingConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_order(
    order_id: UUID,
    version: Annotated[int, Query(gt=0)],
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> Response:
    _manage(request, db, principal)
    try:
        delete_draft_order(
            db,
            order_id=order_id,
            version=version,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (ManufacturingNotFound, ManufacturingConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.get("/orders/{order_id}/replan-preview", response_model=ReplanView)
def replan_preview(
    order_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> ReplanView:
    _read(request, db, principal)
    try:
        return preview_replan(db, order_id)
    except (ManufacturingNotFound, ManufacturingConflict, ValueError) as exc:
        raise _translate_error(exc) from exc


@router.get(
    "/orders/{order_id}/material-availability",
    response_model=MaterialAvailabilityView,
)
def material_availability_preview(
    order_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> MaterialAvailabilityView:
    _read(request, db, principal)
    try:
        return preview_material_availability(db, order_id)
    except (ManufacturingNotFound, ManufacturingConflict, ValueError) as exc:
        raise _translate_error(exc) from exc


@router.post("/orders/{order_id}/replan", response_model=ManufacturingOrderView)
def replan_order(
    order_id: UUID,
    payload: TransitionRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> ManufacturingOrderView:
    _manage(request, db, principal)
    try:
        result = apply_replan(
            db,
            order_id=order_id,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (ManufacturingNotFound, ManufacturingConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post("/orders/{order_id}/start", response_model=ManufacturingOrderView)
def begin_order(
    order_id: UUID,
    payload: TransitionRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> ManufacturingOrderView:
    _manage(request, db, principal)
    try:
        result = start_order(
            db,
            order_id=order_id,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (
        ManufacturingNotFound,
        ManufacturingConflict,
        InventoryConflict,
        InsufficientStock,
        IntegrityError,
        ValueError,
    ) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post("/orders/{order_id}/complete", response_model=ManufacturingOrderView)
def finish_order(
    order_id: UUID,
    payload: CompleteManufacturingOrderRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> ManufacturingOrderView:
    _manage(request, db, principal)
    try:
        result = complete_order(
            db,
            order_id=order_id,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (
        ManufacturingNotFound,
        ManufacturingConflict,
        InventoryConflict,
        InsufficientStock,
        IntegrityError,
        ValueError,
    ) as exc:
        db.rollback()
        raise _translate_error(exc) from exc


@router.post("/orders/{order_id}/cancel", response_model=ManufacturingOrderView)
def undo_order(
    order_id: UUID,
    payload: CancelManufacturingOrderRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> ManufacturingOrderView:
    _manage(request, db, principal)
    try:
        result = cancel_order(
            db,
            order_id=order_id,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (
        ManufacturingNotFound,
        ManufacturingConflict,
        InventoryConflict,
        InsufficientStock,
        IntegrityError,
        ValueError,
    ) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
