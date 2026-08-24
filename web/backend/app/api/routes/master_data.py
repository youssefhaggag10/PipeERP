from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import (
    CurrentPrincipal,
    DatabaseSession,
    client_context,
    enforce_csrf,
    enforce_permission,
)
from app.modules.identity.permissions import PermissionCode
from app.modules.master_data.schemas import (
    CategoryView,
    CompanySettingsView,
    CreateCategoryRequest,
    CreatePartnerRequest,
    CreateProductRequest,
    CreateUnitRequest,
    CreateWarehouseRequest,
    PartnerView,
    ProductView,
    UnitView,
    UpdateCategoryRequest,
    UpdateCompanySettingsRequest,
    UpdatePartnerRequest,
    UpdateProductRequest,
    UpdateUnitRequest,
    UpdateWarehouseRequest,
    WarehouseView,
)
from app.modules.master_data.service import (
    MasterDataConflict,
    MasterDataNotFound,
    create_category,
    create_partner,
    create_product,
    create_unit,
    create_warehouse,
    delete_product,
    get_company_settings,
    list_categories,
    list_partners,
    list_products,
    list_units,
    list_warehouses,
    update_category,
    update_company_settings,
    update_partner,
    update_product,
    update_unit,
    update_warehouse,
)
from app.modules.treasury.schemas import PartnerStatementView
from app.modules.treasury.service import TreasuryNotFound, partner_statement

router = APIRouter(prefix="/master-data")


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MasterDataNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, MasterDataConflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, IntegrityError):
        return HTTPException(status.HTTP_409_CONFLICT, "يتعارض السجل مع بيانات موجودة بالفعل")
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("/units", response_model=list[UnitView])
def units(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    include_inactive: Annotated[bool, Query()] = False,
) -> list[UnitView]:
    enforce_permission(request, db, principal, PermissionCode.PRODUCTS_READ)
    return [
        UnitView.model_validate(item)
        for item in list_units(db, include_inactive=include_inactive)
    ]


@router.post("/units", response_model=UnitView, status_code=status.HTTP_201_CREATED)
def add_unit(
    payload: CreateUnitRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> UnitView:
    enforce_permission(request, db, principal, PermissionCode.PRODUCTS_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        item = create_unit(db, payload=payload, actor=principal, client=client_context(request))
    except (MasterDataConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = UnitView.model_validate(item)
    db.commit()
    return view


@router.put("/units/{unit_id}", response_model=UnitView)
def edit_unit(
    unit_id: UUID,
    payload: UpdateUnitRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> UnitView:
    enforce_permission(request, db, principal, PermissionCode.PRODUCTS_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        item = update_unit(
            db,
            unit_id=unit_id,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
    except (MasterDataConflict, MasterDataNotFound, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = UnitView.model_validate(item)
    db.commit()
    return view


@router.get("/categories", response_model=list[CategoryView])
def categories(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    include_inactive: Annotated[bool, Query()] = False,
) -> list[CategoryView]:
    enforce_permission(request, db, principal, PermissionCode.PRODUCTS_READ)
    return [
        CategoryView.model_validate(item)
        for item in list_categories(db, include_inactive=include_inactive)
    ]


@router.post("/categories", response_model=CategoryView, status_code=status.HTTP_201_CREATED)
def add_category(
    payload: CreateCategoryRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> CategoryView:
    enforce_permission(request, db, principal, PermissionCode.PRODUCTS_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        item = create_category(
            db,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
    except (MasterDataConflict, MasterDataNotFound, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = CategoryView.model_validate(item)
    db.commit()
    return view


@router.put("/categories/{category_id}", response_model=CategoryView)
def edit_category(
    category_id: UUID,
    payload: UpdateCategoryRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> CategoryView:
    enforce_permission(request, db, principal, PermissionCode.PRODUCTS_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        item = update_category(
            db,
            category_id=category_id,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
    except (MasterDataConflict, MasterDataNotFound, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = CategoryView.model_validate(item)
    db.commit()
    return view


@router.get("/products", response_model=list[ProductView])
def products(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    include_inactive: Annotated[bool, Query()] = False,
) -> list[ProductView]:
    enforce_permission(request, db, principal, PermissionCode.PRODUCTS_READ)
    return [
        ProductView.model_validate(item)
        for item in list_products(db, include_inactive=include_inactive)
    ]


@router.post("/products", response_model=ProductView, status_code=status.HTTP_201_CREATED)
def add_product(
    payload: CreateProductRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> ProductView:
    enforce_permission(request, db, principal, PermissionCode.PRODUCTS_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        product = create_product(
            db,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
    except (MasterDataConflict, MasterDataNotFound, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = ProductView.model_validate(product)
    db.commit()
    return view


@router.patch("/products/{product_id}", response_model=ProductView)
def edit_product(
    product_id: UUID,
    payload: UpdateProductRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> ProductView:
    enforce_permission(request, db, principal, PermissionCode.PRODUCTS_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        product = update_product(
            db,
            product_id=product_id,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
    except (MasterDataConflict, MasterDataNotFound, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = ProductView.model_validate(product)
    db.commit()
    return view


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_product(
    product_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> None:
    enforce_permission(request, db, principal, PermissionCode.PRODUCTS_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        delete_product(
            db,
            product_id=product_id,
            actor=principal,
            client=client_context(request),
        )
    except (MasterDataNotFound, IntegrityError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    db.commit()


@router.get("/partners", response_model=list[PartnerView])
def partners(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    include_inactive: Annotated[bool, Query()] = False,
) -> list[PartnerView]:
    enforce_permission(request, db, principal, PermissionCode.PARTNERS_READ)
    return [
        PartnerView.model_validate(item)
        for item in list_partners(db, include_inactive=include_inactive)
    ]


@router.post("/partners", response_model=PartnerView, status_code=status.HTTP_201_CREATED)
def add_partner(
    payload: CreatePartnerRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> PartnerView:
    enforce_permission(request, db, principal, PermissionCode.PARTNERS_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        partner = create_partner(
            db,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
    except (MasterDataConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = PartnerView.model_validate(partner)
    db.commit()
    return view


@router.put("/partners/{partner_id}", response_model=PartnerView)
def edit_partner(
    partner_id: UUID,
    payload: UpdatePartnerRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> PartnerView:
    enforce_permission(request, db, principal, PermissionCode.PARTNERS_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        partner = update_partner(
            db,
            partner_id=partner_id,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
    except (MasterDataConflict, MasterDataNotFound, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = PartnerView.model_validate(partner)
    db.commit()
    return view


@router.get("/partners/{partner_id}/linked-movements", response_model=PartnerStatementView)
def partner_linked_movements(
    partner_id: UUID,
    partner_type: Annotated[str, Query(pattern="^(customer|supplier)$")],
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> PartnerStatementView:
    enforce_permission(request, db, principal, PermissionCode.PARTNERS_READ)
    try:
        return partner_statement(
            db,
            partner_id=partner_id,
            date_from=date(1900, 1, 1),
            date_to=date.today(),
            partner_type=partner_type,
        )
    except TreasuryNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/warehouses", response_model=list[WarehouseView])
def warehouses(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    include_inactive: Annotated[bool, Query()] = False,
) -> list[WarehouseView]:
    enforce_permission(request, db, principal, PermissionCode.WAREHOUSES_READ)
    return [
        WarehouseView.model_validate(item)
        for item in list_warehouses(db, include_inactive=include_inactive)
    ]


@router.post("/warehouses", response_model=WarehouseView, status_code=status.HTTP_201_CREATED)
def add_warehouse(
    payload: CreateWarehouseRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> WarehouseView:
    enforce_permission(request, db, principal, PermissionCode.WAREHOUSES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        item = create_warehouse(
            db,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
    except (MasterDataConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = WarehouseView.model_validate(item)
    db.commit()
    return view


@router.put("/warehouses/{warehouse_id}", response_model=WarehouseView)
def edit_warehouse(
    warehouse_id: UUID,
    payload: UpdateWarehouseRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> WarehouseView:
    enforce_permission(request, db, principal, PermissionCode.WAREHOUSES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        item = update_warehouse(
            db,
            warehouse_id=warehouse_id,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
    except (MasterDataConflict, MasterDataNotFound, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = WarehouseView.model_validate(item)
    db.commit()
    return view


@router.get("/settings", response_model=CompanySettingsView)
def settings(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> CompanySettingsView:
    enforce_permission(request, db, principal, PermissionCode.SETTINGS_READ)
    try:
        item = get_company_settings(db)
    except MasterDataNotFound as exc:
        raise _translate_error(exc) from exc
    return CompanySettingsView.model_validate(item)


@router.put("/settings", response_model=CompanySettingsView)
def edit_settings(
    payload: UpdateCompanySettingsRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> CompanySettingsView:
    enforce_permission(request, db, principal, PermissionCode.SETTINGS_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        item = update_company_settings(
            db,
            payload=payload,
            actor=principal,
            client=client_context(request),
        )
    except (MasterDataConflict, MasterDataNotFound, IntegrityError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = CompanySettingsView.model_validate(item)
    db.commit()
    return view
