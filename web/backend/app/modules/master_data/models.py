from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin


class UnitOfMeasure(TimestampMixin, Base):
    __tablename__ = "units_of_measure"
    __table_args__ = (
        UniqueConstraint("normalized_code"),
        CheckConstraint("decimal_places BETWEEN 0 AND 6", name="decimal_places_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(24), nullable=False)
    normalized_code: Mapped[str] = mapped_column(String(24), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(120), nullable=False)
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    decimal_places: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProductCategory(TimestampMixin, Base):
    __tablename__ = "product_categories"
    __table_args__ = (UniqueConstraint("normalized_code"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    normalized_code: Mapped[str] = mapped_column(String(40), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(160), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("product_categories.id", ondelete="RESTRICT"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("normalized_code"),
        CheckConstraint(
            "product_type IN ('raw_material', 'finished_good', 'waste', 'service', 'spare_part')",
            name="product_type_valid",
        ),
        CheckConstraint("min_stock >= 0", name="min_stock_nonnegative"),
        CheckConstraint("standard_weight_kg >= 0", name="standard_weight_nonnegative"),
        CheckConstraint(
            "weight_tolerance_percent BETWEEN 0 AND 100",
            name="weight_tolerance_valid",
        ),
        Index("ix_products_type_active", "product_type", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    product_type: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=False,
    )
    category_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("product_categories.id", ondelete="RESTRICT"),
    )
    min_stock: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    track_lots: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    standard_weight_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    weight_tolerance_percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 3), nullable=False, default=5
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Partner(TimestampMixin, Base):
    __tablename__ = "partners"
    __table_args__ = (
        UniqueConstraint("normalized_code"),
        CheckConstraint("is_customer OR is_supplier", name="partner_type_required"),
        Index("ix_partners_customer_active", "is_customer", "is_active"),
        Index("ix_partners_supplier_active", "is_supplier", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    address: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tax_number: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    is_customer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_supplier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Warehouse(TimestampMixin, Base):
    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint("normalized_code"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    normalized_code: Mapped[str] = mapped_column(String(40), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(160), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CompanySettings(TimestampMixin, Base):
    __tablename__ = "company_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("currency_decimal_places BETWEEN 0 AND 4", name="currency_scale_valid"),
        CheckConstraint("default_tax_rate BETWEEN 0 AND 100", name="tax_rate_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    company_name_ar: Mapped[str] = mapped_column(String(200), nullable=False, default="PipeERP")
    phone: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    address: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tax_number: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="EGP")
    currency_decimal_places: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    tax_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_tax_rate: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False, default=0)
    default_warehouse_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
    )


class DocumentSequence(TimestampMixin, Base):
    __tablename__ = "document_sequences"
    __table_args__ = (
        CheckConstraint("next_value > 0", name="next_value_positive"),
        CheckConstraint("padding BETWEEN 1 AND 12", name="padding_valid"),
    )

    document_type: Mapped[str] = mapped_column(String(60), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    padding: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
