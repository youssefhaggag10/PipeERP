from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin


class SalesOrder(TimestampMixin, Base):
    __tablename__ = "sales_orders"
    __table_args__ = (
        UniqueConstraint("order_number"),
        CheckConstraint(
            "status IN ('draft', 'delivered', 'reversed', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint("billing_method IN ('piece', 'weight')", name="billing_method_valid"),
        CheckConstraint("subtotal >= 0", name="subtotal_nonnegative"),
        CheckConstraint("discount_amount >= 0", name="discount_nonnegative"),
        CheckConstraint("transport_amount >= 0", name="transport_nonnegative"),
        CheckConstraint("tax_amount >= 0", name="tax_nonnegative"),
        CheckConstraint("total >= 0", name="total_nonnegative"),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_sales_orders_customer_status", "customer_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    order_number: Mapped[str] = mapped_column(String(40), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    billing_method: Mapped[str] = mapped_column(String(16), nullable=False, default="piece")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    transport_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class SalesOrderLine(TimestampMixin, Base):
    __tablename__ = "sales_order_lines"
    __table_args__ = (
        UniqueConstraint("sales_order_id", "product_id"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_nonnegative"),
        CheckConstraint("line_total >= 0", name="line_total_nonnegative"),
        CheckConstraint("standard_weight_kg >= 0", name="standard_weight_nonnegative"),
        CheckConstraint("billing_weight_kg >= 0", name="billing_weight_nonnegative"),
        CheckConstraint("price_per_kg >= 0", name="price_per_kg_nonnegative"),
        Index("ix_sales_order_lines_order", "sales_order_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    sales_order_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    standard_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    billing_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    price_per_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class SalesWeightCard(TimestampMixin, Base):
    __tablename__ = "sales_weight_cards"
    __table_args__ = (
        UniqueConstraint("card_number"),
        CheckConstraint("status IN ('draft', 'posted', 'cancelled')", name="status_valid"),
        CheckConstraint("weight_mode IN ('total_card', 'per_line')", name="weight_mode_valid"),
        CheckConstraint("pricing_mode IN ('uniform', 'per_line')", name="pricing_mode_valid"),
        CheckConstraint("gross_weight_kg >= 0", name="gross_nonnegative"),
        CheckConstraint("tare_weight_kg >= 0", name="tare_nonnegative"),
        CheckConstraint("net_weight_kg > 0", name="net_positive"),
        CheckConstraint("uniform_price_per_kg >= 0", name="uniform_price_nonnegative"),
        CheckConstraint("subtotal >= 0", name="subtotal_nonnegative"),
        Index("ix_sales_weight_cards_order", "sales_order_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    sales_order_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False
    )
    card_number: Mapped[str] = mapped_column(String(40), nullable=False)
    card_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    vehicle_number: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    gross_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    tare_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    net_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    weight_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    pricing_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    uniform_price_per_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    use_vehicle_scale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class SalesWeightCardLine(TimestampMixin, Base):
    __tablename__ = "sales_weight_card_lines"
    __table_args__ = (
        UniqueConstraint("weight_card_id", "sales_order_line_id"),
        CheckConstraint("quantity_pieces > 0", name="pieces_positive"),
        CheckConstraint("standard_weight_kg >= 0", name="standard_weight_nonnegative"),
        CheckConstraint("theoretical_weight_kg >= 0", name="theoretical_weight_nonnegative"),
        CheckConstraint("actual_weight_kg > 0", name="actual_weight_positive"),
        CheckConstraint("price_per_kg >= 0", name="price_nonnegative"),
        CheckConstraint("line_total >= 0", name="line_total_nonnegative"),
        Index("ix_sales_weight_card_lines_card", "weight_card_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    weight_card_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sales_weight_cards.id", ondelete="CASCADE"), nullable=False
    )
    sales_order_line_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sales_order_lines.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity_pieces: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    standard_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    theoretical_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    actual_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    price_per_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")


class SalesDelivery(Base):
    __tablename__ = "sales_deliveries"
    __table_args__ = (
        UniqueConstraint("delivery_number"),
        UniqueConstraint("sales_order_id"),
        UniqueConstraint("idempotency_key"),
        UniqueConstraint("reversal_idempotency_key"),
        CheckConstraint("status IN ('posted', 'reversed')", name="status_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    delivery_number: Mapped[str] = mapped_column(String(40), nullable=False)
    sales_order_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sales_orders.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="posted")
    posted_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reversal_idempotency_key: Mapped[str | None] = mapped_column(String(120))
    reversed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")


class SalesDeliveryLine(TimestampMixin, Base):
    __tablename__ = "sales_delivery_lines"
    __table_args__ = (
        UniqueConstraint("sales_delivery_id", "sales_order_line_id"),
        UniqueConstraint("inventory_transaction_id"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("weight_kg >= 0", name="weight_nonnegative"),
        CheckConstraint("cost_amount >= 0", name="cost_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    sales_delivery_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sales_deliveries.id", ondelete="CASCADE"), nullable=False
    )
    sales_order_line_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sales_order_lines.id", ondelete="RESTRICT"), nullable=False
    )
    inventory_transaction_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    cost_amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)


class CustomerInvoice(TimestampMixin, Base):
    __tablename__ = "customer_invoices"
    __table_args__ = (
        UniqueConstraint("invoice_number"),
        UniqueConstraint("sales_order_id"),
        CheckConstraint("invoice_type IN ('standard', 'weight')", name="invoice_type_valid"),
        CheckConstraint("status IN ('posted', 'reversed')", name="status_valid"),
        CheckConstraint("subtotal >= 0", name="subtotal_nonnegative"),
        CheckConstraint("discount_amount >= 0", name="discount_nonnegative"),
        CheckConstraint("transport_amount >= 0", name="transport_nonnegative"),
        CheckConstraint("tax_amount >= 0", name="tax_nonnegative"),
        CheckConstraint("total >= 0", name="total_nonnegative"),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_customer_invoices_customer_status", "customer_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False)
    sales_order_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sales_orders.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="posted")
    invoice_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    transport_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SalesQuotation(TimestampMixin, Base):
    __tablename__ = "sales_quotations"
    __table_args__ = (
        UniqueConstraint("quotation_number"),
        CheckConstraint(
            "status IN ('draft', 'sent', 'accepted', 'rejected', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint("total >= 0", name="total_nonnegative"),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_sales_quotations_customer_date", "customer_id", "quotation_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    quotation_number: Mapped[str] = mapped_column(String(40), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    quotation_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    total: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class SalesQuotationLine(TimestampMixin, Base):
    __tablename__ = "sales_quotation_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_nonnegative"),
        CheckConstraint("line_total >= 0", name="line_total_nonnegative"),
        Index("ix_sales_quotation_lines_quotation", "quotation_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    quotation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sales_quotations.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT")
    )
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
