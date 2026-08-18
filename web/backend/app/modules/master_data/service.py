import re
import unicodedata
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
    CreatePartnerRequest,
    CreateProductRequest,
    UpdateCompanySettingsRequest,
    UpdatePartnerRequest,
    UpdateProductRequest,
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
    model: type[Product] | type[Partner],
    normalized_code: str,
    *,
    excluding_id: UUID | None = None,
) -> None:
    statement = select(model.id).where(model.normalized_code == normalized_code)
    if excluding_id is not None:
        statement = statement.where(model.id != excluding_id)
    if db.scalar(statement) is not None:
        raise MasterDataConflict("الكود مستخدم بالفعل")


def list_units(db: Session) -> list[UnitOfMeasure]:
    return list(
        db.scalars(
            select(UnitOfMeasure)
            .where(UnitOfMeasure.is_active.is_(True))
            .order_by(UnitOfMeasure.name_ar)
        )
    )


def list_categories(db: Session) -> list[ProductCategory]:
    return list(
        db.scalars(
            select(ProductCategory)
            .where(ProductCategory.is_active.is_(True))
            .order_by(ProductCategory.name_ar)
        )
    )


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
        standard_weight_kg=payload.standard_weight_kg,
        weight_tolerance_percent=payload.weight_tolerance_percent,
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


def list_warehouses(db: Session) -> list[Warehouse]:
    return list(
        db.scalars(select(Warehouse).order_by(Warehouse.is_default.desc(), Warehouse.name_ar))
    )


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
    if payload.default_warehouse_id is not None:
        warehouse = db.get(Warehouse, payload.default_warehouse_id)
        if warehouse is None or not warehouse.is_active:
            raise MasterDataNotFound("المخزن الافتراضي غير موجود أو غير نشط")
    before: dict[str, object] = {
        "company_name_ar": settings.company_name_ar,
        "currency_code": settings.currency_code,
    }
    for field, value in payload.model_dump().items():
        setattr(settings, field, value.strip() if isinstance(value, str) else value)
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
