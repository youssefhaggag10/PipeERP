from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

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
    CreatePartnerRequest,
    CreateProductRequest,
    PartnerView,
    ProductView,
    UnitView,
    UpdateCompanySettingsRequest,
    UpdatePartnerRequest,
    UpdateProductRequest,
    WarehouseView,
)
from app.modules.master_data.service import (
    MasterDataConflict,
    MasterDataNotFound,
    create_partner,
    create_product,
    get_company_settings,
    list_categories,
    list_partners,
    list_products,
    list_units,
    list_warehouses,
    update_company_settings,
    update_partner,
    update_product,
)

router = APIRouter(prefix="/master-data")


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MasterDataNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, MasterDataConflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("/units", response_model=list[UnitView])
def units(request: Request, principal: CurrentPrincipal, db: DatabaseSession) -> list[UnitView]:
    enforce_permission(request, db, principal, PermissionCode.PRODUCTS_READ)
    return [UnitView.model_validate(item) for item in list_units(db)]


@router.get("/categories", response_model=list[CategoryView])
def categories(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[CategoryView]:
    enforce_permission(request, db, principal, PermissionCode.PRODUCTS_READ)
    return [CategoryView.model_validate(item) for item in list_categories(db)]


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
    except (MasterDataConflict, MasterDataNotFound, ValueError) as exc:
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
    except (MasterDataConflict, MasterDataNotFound, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = ProductView.model_validate(product)
    db.commit()
    return view


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
    except (MasterDataConflict, ValueError) as exc:
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
    except (MasterDataConflict, MasterDataNotFound, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = PartnerView.model_validate(partner)
    db.commit()
    return view


@router.get("/warehouses", response_model=list[WarehouseView])
def warehouses(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> list[WarehouseView]:
    enforce_permission(request, db, principal, PermissionCode.WAREHOUSES_READ)
    return [WarehouseView.model_validate(item) for item in list_warehouses(db)]


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
    except MasterDataNotFound as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = CompanySettingsView.model_validate(item)
    db.commit()
    return view
