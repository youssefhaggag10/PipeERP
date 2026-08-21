import re
import unicodedata
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.identity.service import ClientContext, Principal, add_audit
from app.modules.master_data.models import (
    CompanySettings,
    DocumentSequence,
    Partner,
    Product,
    ProductCategory,
    UnitOfMeasure,
    Warehouse,
)
from app.modules.master_data.schemas import (
    CreateCategoryRequest,
    CreatePartnerRequest,
    CreateProductRequest,
    CreateUnitRequest,
    CreateWarehouseRequest,
    UpdateCategoryRequest,
    UpdateCompanySettingsRequest,
    UpdatePartnerRequest,
    UpdateProductRequest,
    UpdateUnitRequest,
    UpdateWarehouseRequest,
)

CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._/-]{0,79}$")


class MasterDataError(Exception):
    pass


class MasterDataNotFound(MasterDataError):
    pass


class MasterDataConflict(MasterDataError):
    pass


def normalize_code(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().upper()
    if not CODE_PATTERN.fullmatch(normalized):
        raise ValueError("الكود يجب أن يبدأ بحرف أو رقم ويحتوي حروفًا وأرقامًا و . _ / - فقط")
    return normalized


def _ensure_code_available(
    db: Session,
    model: type[UnitOfMeasure]
    | type[ProductCategory]
    | type[Product]
    | type[Partner]
    | type[Warehouse],
    normalized_code: str,
    *,
    excluding_id: UUID | None = None,
) -> None:
    statement = select(model.id).where(model.normalized_code == normalized_code)
    if excluding_id is not None:
        statement = statement.where(model.id != excluding_id)
    if db.scalar(statement) is not None:
        raise MasterDataConflict("الكود مستخدم بالفعل")


def list_units(db: Session, *, include_inactive: bool = False) -> list[UnitOfMeasure]:
    statement = select(UnitOfMeasure).order_by(UnitOfMeasure.name_ar)
    if not include_inactive:
        statement = statement.where(UnitOfMeasure.is_active.is_(True))
    return list(db.scalars(statement))


def create_unit(
    db: Session,
    *,
    payload: CreateUnitRequest,
    actor: Principal,
    client: ClientContext,
) -> UnitOfMeasure:
    normalized_code = normalize_code(payload.code)
    _ensure_code_available(db, UnitOfMeasure, normalized_code)
    unit = UnitOfMeasure(
        code=payload.code.strip(),
        normalized_code=normalized_code,
        name_ar=payload.name_ar.strip(),
        symbol=payload.symbol.strip(),
        decimal_places=payload.decimal_places,
        is_active=True,
        version=1,
    )
    db.add(unit)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="master_data.unit.create",
        entity_type="unit_of_measure",
        entity_id=str(unit.id),
        outcome="success",
        client=client,
        after_state={"code": unit.code, "name_ar": unit.name_ar},
    )
    return unit


def update_unit(
    db: Session,
    *,
    unit_id: UUID,
    payload: UpdateUnitRequest,
    actor: Principal,
    client: ClientContext,
) -> UnitOfMeasure:
    unit = db.get(UnitOfMeasure, unit_id)
    if unit is None:
        raise MasterDataNotFound("وحدة القياس غير موجودة")
    if unit.version != payload.version:
        raise MasterDataConflict("عدّل مستخدم آخر وحدة القياس؛ حدّث الصفحة ثم أعد المحاولة")
    normalized_code = normalize_code(payload.code)
    _ensure_code_available(db, UnitOfMeasure, normalized_code, excluding_id=unit.id)
    before = {"code": unit.code, "name_ar": unit.name_ar, "version": unit.version}
    unit.code = payload.code.strip()
    unit.normalized_code = normalized_code
    unit.name_ar = payload.name_ar.strip()
    unit.symbol = payload.symbol.strip()
    unit.decimal_places = payload.decimal_places
    unit.is_active = payload.is_active
    unit.version += 1
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="master_data.unit.update",
        entity_type="unit_of_measure",
        entity_id=str(unit.id),
        outcome="success",
        client=client,
        before_state=before,
        after_state={"code": unit.code, "name_ar": unit.name_ar, "version": unit.version},
    )
    return unit


def list_categories(db: Session, *, include_inactive: bool = False) -> list[ProductCategory]:
    statement = select(ProductCategory).order_by(ProductCategory.name_ar)
    if not include_inactive:
        statement = statement.where(ProductCategory.is_active.is_(True))
    return list(db.scalars(statement))


def _validate_category_parent(
    db: Session,
    *,
    category_id: UUID | None,
    parent_id: UUID | None,
) -> None:
    if parent_id is None:
        return
    if category_id == parent_id:
        raise MasterDataConflict("لا يمكن أن يكون التصنيف أبًا لنفسه")
    parent = db.get(ProductCategory, parent_id)
    if parent is None or not parent.is_active:
        raise MasterDataNotFound("التصنيف الأب غير موجود أو غير نشط")
    visited: set[UUID] = set()
    current: ProductCategory | None = parent
    while current is not None and current.id not in visited:
        if current.id == category_id:
            raise MasterDataConflict("اختيار التصنيف الأب سيُنشئ دورة غير صالحة")
        visited.add(current.id)
        current = db.get(ProductCategory, current.parent_id) if current.parent_id else None


def create_category(
    db: Session,
    *,
    payload: CreateCategoryRequest,
    actor: Principal,
    client: ClientContext,
) -> ProductCategory:
    normalized_code = normalize_code(payload.code)
    _ensure_code_available(db, ProductCategory, normalized_code)
    _validate_category_parent(db, category_id=None, parent_id=payload.parent_id)
    category = ProductCategory(
        code=payload.code.strip(),
        normalized_code=normalized_code,
        name_ar=payload.name_ar.strip(),
        parent_id=payload.parent_id,
        is_active=True,
        version=1,
    )
    db.add(category)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="master_data.category.create",
        entity_type="product_category",
        entity_id=str(category.id),
        outcome="success",
        client=client,
        after_state={"code": category.code, "name_ar": category.name_ar},
    )
    return category


def update_category(
    db: Session,
    *,
    category_id: UUID,
    payload: UpdateCategoryRequest,
    actor: Principal,
    client: ClientContext,
) -> ProductCategory:
    category = db.get(ProductCategory, category_id)
    if category is None:
        raise MasterDataNotFound("التصنيف غير موجود")
    if category.version != payload.version:
        raise MasterDataConflict("عدّل مستخدم آخر التصنيف؛ حدّث الصفحة ثم أعد المحاولة")
    normalized_code = normalize_code(payload.code)
    _ensure_code_available(db, ProductCategory, normalized_code, excluding_id=category.id)
    _validate_category_parent(db, category_id=category.id, parent_id=payload.parent_id)
    before = {"code": category.code, "name_ar": category.name_ar, "version": category.version}
    category.code = payload.code.strip()
    category.normalized_code = normalized_code
    category.name_ar = payload.name_ar.strip()
    category.parent_id = payload.parent_id
    category.is_active = payload.is_active
    category.version += 1
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="master_data.category.update",
        entity_type="product_category",
        entity_id=str(category.id),
        outcome="success",
        client=client,
        before_state=before,
        after_state={
            "code": category.code,
            "name_ar": category.name_ar,
            "version": category.version,
        },
    )
    return category


def list_products(db: Session, *, include_inactive: bool = False) -> list[Product]:
    statement = select(Product).order_by(Product.created_at.desc())
    if not include_inactive:
        statement = statement.where(Product.is_active.is_(True))
    return list(db.scalars(statement))


def _validate_product_references(
    db: Session,
    *,
    unit_id: UUID,
    category_id: UUID | None,
) -> None:
    unit = db.get(UnitOfMeasure, unit_id)
    if unit is None or not unit.is_active:
        raise MasterDataNotFound("وحدة القياس غير موجودة أو غير نشطة")
    if category_id is not None:
        category = db.get(ProductCategory, category_id)
        if category is None or not category.is_active:
            raise MasterDataNotFound("التصنيف غير موجود أو غير نشط")


def create_product(
    db: Session,
    *,
    payload: CreateProductRequest,
    actor: Principal,
    client: ClientContext,
) -> Product:
    normalized_code = normalize_code(payload.code)
    _ensure_code_available(db, Product, normalized_code)
    _validate_product_references(db, unit_id=payload.unit_id, category_id=payload.category_id)
    product = Product(
        code=payload.code.strip(),
        normalized_code=normalized_code,
        name_ar=payload.name_ar.strip(),
        product_type=payload.product_type,
        unit_id=payload.unit_id,
        category_id=payload.category_id,
        min_stock=payload.min_stock,
        track_lots=payload.track_lots,
        standard_weight_kg=(
            payload.standard_weight_kg if payload.product_type == "finished_good" else Decimal("0")
        ),
        weight_tolerance_percent=Decimal("0"),
        is_active=True,
        version=1,
    )
    db.add(product)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="master_data.product.create",
        entity_type="product",
        entity_id=str(product.id),
        outcome="success",
        client=client,
        after_state={"code": product.code, "name_ar": product.name_ar},
    )
    return product


def update_product(
    db: Session,
    *,
    product_id: UUID,
    payload: UpdateProductRequest,
    actor: Principal,
    client: ClientContext,
) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise MasterDataNotFound("المنتج غير موجود")
    if product.version != payload.version:
        raise MasterDataConflict("عدّل مستخدم آخر هذا المنتج؛ حدّث الصفحة ثم أعد المحاولة")
    before = {"code": product.code, "name_ar": product.name_ar, "version": product.version}
    if payload.code is not None:
        normalized_code = normalize_code(payload.code)
        _ensure_code_available(db, Product, normalized_code, excluding_id=product.id)
        product.code = payload.code.strip()
        product.normalized_code = normalized_code
    if payload.name_ar is not None:
        product.name_ar = payload.name_ar.strip()
    if payload.product_type is not None:
        product.product_type = payload.product_type
    unit_id = payload.unit_id or product.unit_id
    category_id = None if payload.clear_category else (payload.category_id or product.category_id)
    _validate_product_references(db, unit_id=unit_id, category_id=category_id)
    product.unit_id = unit_id
    product.category_id = category_id
    for field in (
        "min_stock",
        "track_lots",
        "standard_weight_kg",
        "weight_tolerance_percent",
        "is_active",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(product, field, value)
    if product.product_type != "finished_good":
        product.standard_weight_kg = Decimal("0")
    product.weight_tolerance_percent = Decimal("0")
    product.version += 1
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="master_data.product.update",
        entity_type="product",
        entity_id=str(product.id),
        outcome="success",
        client=client,
        before_state=before,
        after_state={"code": product.code, "name_ar": product.name_ar, "version": product.version},
    )
    return product


def list_partners(db: Session, *, include_inactive: bool = False) -> list[Partner]:
    statement = select(Partner).order_by(Partner.created_at.desc())
    if not include_inactive:
        statement = statement.where(Partner.is_active.is_(True))
    return list(db.scalars(statement))


def create_partner(
    db: Session,
    *,
    payload: CreatePartnerRequest,
    actor: Principal,
    client: ClientContext,
) -> Partner:
    normalized_code = normalize_code(payload.code)
    _ensure_code_available(db, Partner, normalized_code)
    partner = Partner(
        code=payload.code.strip(),
        normalized_code=normalized_code,
        name_ar=payload.name_ar.strip(),
        phone=payload.phone.strip(),
        address=payload.address.strip(),
        tax_number=payload.tax_number.strip(),
        is_customer=payload.is_customer,
        is_supplier=payload.is_supplier,
        is_active=True,
        version=1,
    )
    db.add(partner)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="master_data.partner.create",
        entity_type="partner",
        entity_id=str(partner.id),
        outcome="success",
        client=client,
        after_state={"code": partner.code, "name_ar": partner.name_ar},
    )
    return partner


def update_partner(
    db: Session,
    *,
    partner_id: UUID,
    payload: UpdatePartnerRequest,
    actor: Principal,
    client: ClientContext,
) -> Partner:
    partner = db.get(Partner, partner_id)
    if partner is None:
        raise MasterDataNotFound("العميل أو المورد غير موجود")
    if partner.version != payload.version:
        raise MasterDataConflict("عدّل مستخدم آخر هذا السجل؛ حدّث الصفحة ثم أعد المحاولة")
    normalized_code = normalize_code(payload.code)
    _ensure_code_available(db, Partner, normalized_code, excluding_id=partner.id)
    before = {"code": partner.code, "name_ar": partner.name_ar, "version": partner.version}
    partner.code = payload.code.strip()
    partner.normalized_code = normalized_code
    partner.name_ar = payload.name_ar.strip()
    partner.phone = payload.phone.strip()
    partner.address = payload.address.strip()
    partner.tax_number = payload.tax_number.strip()
    partner.is_customer = payload.is_customer
    partner.is_supplier = payload.is_supplier
    partner.is_active = payload.is_active
    partner.version += 1
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="master_data.partner.update",
        entity_type="partner",
        entity_id=str(partner.id),
        outcome="success",
        client=client,
        before_state=before,
        after_state={"code": partner.code, "name_ar": partner.name_ar, "version": partner.version},
    )
    return partner


def list_warehouses(db: Session, *, include_inactive: bool = False) -> list[Warehouse]:
    statement = select(Warehouse).order_by(Warehouse.is_default.desc(), Warehouse.name_ar)
    if not include_inactive:
        statement = statement.where(Warehouse.is_active.is_(True))
    return list(db.scalars(statement))


def _make_default_warehouse(db: Session, warehouse: Warehouse) -> None:
    for current in db.scalars(
        select(Warehouse).where(Warehouse.is_default.is_(True), Warehouse.id != warehouse.id)
    ):
        current.is_default = False
        current.version += 1
    db.flush()
    warehouse.is_default = True
    settings = db.get(CompanySettings, 1)
    if settings is not None:
        settings.default_warehouse_id = warehouse.id
        settings.version += 1


def create_warehouse(
    db: Session,
    *,
    payload: CreateWarehouseRequest,
    actor: Principal,
    client: ClientContext,
) -> Warehouse:
    normalized_code = normalize_code(payload.code)
    _ensure_code_available(db, Warehouse, normalized_code)
    warehouse = Warehouse(
        code=payload.code.strip(),
        normalized_code=normalized_code,
        name_ar=payload.name_ar.strip(),
        is_default=False,
        is_active=True,
        version=1,
    )
    db.add(warehouse)
    db.flush()
    if payload.is_default:
        _make_default_warehouse(db, warehouse)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="master_data.warehouse.create",
        entity_type="warehouse",
        entity_id=str(warehouse.id),
        outcome="success",
        client=client,
        after_state={
            "code": warehouse.code,
            "name_ar": warehouse.name_ar,
            "is_default": warehouse.is_default,
        },
    )
    return warehouse


def update_warehouse(
    db: Session,
    *,
    warehouse_id: UUID,
    payload: UpdateWarehouseRequest,
    actor: Principal,
    client: ClientContext,
) -> Warehouse:
    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise MasterDataNotFound("المخزن غير موجود")
    if warehouse.version != payload.version:
        raise MasterDataConflict("عدّل مستخدم آخر المخزن؛ حدّث الصفحة ثم أعد المحاولة")
    if warehouse.is_default and (not payload.is_default or not payload.is_active):
        raise MasterDataConflict("عيّن مخزنًا افتراضيًا آخر قبل تعطيل المخزن الافتراضي")
    normalized_code = normalize_code(payload.code)
    _ensure_code_available(db, Warehouse, normalized_code, excluding_id=warehouse.id)
    before = {
        "code": warehouse.code,
        "name_ar": warehouse.name_ar,
        "is_default": warehouse.is_default,
        "version": warehouse.version,
    }
    warehouse.code = payload.code.strip()
    warehouse.normalized_code = normalized_code
    warehouse.name_ar = payload.name_ar.strip()
    warehouse.is_active = payload.is_active
    warehouse.version += 1
    if payload.is_default:
        _make_default_warehouse(db, warehouse)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="master_data.warehouse.update",
        entity_type="warehouse",
        entity_id=str(warehouse.id),
        outcome="success",
        client=client,
        before_state=before,
        after_state={
            "code": warehouse.code,
            "name_ar": warehouse.name_ar,
            "is_default": warehouse.is_default,
            "version": warehouse.version,
        },
    )
    return warehouse


def get_company_settings(db: Session) -> CompanySettings:
    settings = db.get(CompanySettings, 1)
    if settings is None:
        raise MasterDataNotFound("إعدادات الشركة غير مهيأة")
    return settings


def update_company_settings(
    db: Session,
    *,
    payload: UpdateCompanySettingsRequest,
    actor: Principal,
    client: ClientContext,
) -> CompanySettings:
    settings = get_company_settings(db)
    if settings.version != payload.version:
        raise MasterDataConflict("عدّل مستخدم آخر إعدادات الشركة؛ حدّث الصفحة ثم أعد المحاولة")
    if payload.default_warehouse_id is not None:
        warehouse = db.get(Warehouse, payload.default_warehouse_id)
        if warehouse is None or not warehouse.is_active:
            raise MasterDataNotFound("المخزن الافتراضي غير موجود أو غير نشط")
    before: dict[str, object] = {
        "company_name_ar": settings.company_name_ar,
        "currency_code": settings.currency_code,
    }
    for field, value in payload.model_dump(exclude={"version"}).items():
        setattr(settings, field, value.strip() if isinstance(value, str) else value)
    settings.version += 1
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="master_data.settings.update",
        entity_type="company_settings",
        entity_id="1",
        outcome="success",
        client=client,
        before_state=before,
        after_state={
            "company_name_ar": settings.company_name_ar,
            "currency_code": settings.currency_code,
        },
    )
    return settings


def allocate_document_number(db: Session, document_type: str) -> str:
    sequence = db.scalar(
        select(DocumentSequence)
        .where(DocumentSequence.document_type == document_type)
        .with_for_update()
    )
    if sequence is None:
        raise MasterDataNotFound("تسلسل المستند غير مهيأ")
    number = f"{sequence.prefix}{sequence.next_value:0{sequence.padding}d}"
    sequence.next_value += 1
    sequence.version += 1
    db.flush()
    return number
