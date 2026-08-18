from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
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


class PurchaseOrder(TimestampMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("order_number"),
        CheckConstraint(
            "status IN ('draft', 'approved', 'partially_received', 'received', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint("total >= 0", name="total_nonnegative"),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_purchase_orders_supplier_status", "supplier_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    order_number: Mapped[str] = mapped_column(String(40), nullable=False)
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    total: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class PurchaseOrderLine(TimestampMixin, Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        CheckConstraint("cost_basis IN ('quantity', 'weight')", name="cost_basis_valid"),
        CheckConstraint(
            "ordered_quantity > 0 OR ordered_weight_kg > 0", name="ordered_amount_positive"
        ),
        CheckConstraint("ordered_quantity >= 0", name="ordered_quantity_nonnegative"),
        CheckConstraint("ordered_weight_kg >= 0", name="ordered_weight_nonnegative"),
        CheckConstraint("unit_price >= 0", name="unit_price_nonnegative"),
        CheckConstraint("additional_unit_cost >= 0", name="additional_cost_nonnegative"),
        CheckConstraint("line_total >= 0", name="line_total_nonnegative"),
        CheckConstraint("received_quantity >= 0", name="received_quantity_nonnegative"),
        CheckConstraint("received_weight_kg >= 0", name="received_weight_nonnegative"),
        CheckConstraint(
            "received_quantity <= ordered_quantity", name="received_quantity_within_order"
        ),
        CheckConstraint(
            "received_weight_kg <= ordered_weight_kg", name="received_weight_within_order"
        ),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_purchase_order_lines_order", "purchase_order_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    purchase_order_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    cost_basis: Mapped[str] = mapped_column(String(16), nullable=False)
    ordered_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    ordered_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    additional_unit_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    received_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PurchaseReceipt(Base):
    __tablename__ = "purchase_receipts"
    __table_args__ = (
        UniqueConstraint("receipt_number"),
        UniqueConstraint("idempotency_key"),
        CheckConstraint("status IN ('posted', 'reversed')", name="status_valid"),
        Index("ix_purchase_receipts_order", "purchase_order_id", "posted_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    receipt_number: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reversal_idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True)
    purchase_order_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="posted")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    posted_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reversed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")


class PurchaseReceiptLine(TimestampMixin, Base):
    __tablename__ = "purchase_receipt_lines"
    __table_args__ = (
        UniqueConstraint("purchase_receipt_id", "purchase_order_line_id"),
        UniqueConstraint("inventory_transaction_id"),
        CheckConstraint("gross_quantity >= 0", name="gross_quantity_nonnegative"),
        CheckConstraint("gross_weight_kg >= 0", name="gross_weight_nonnegative"),
        CheckConstraint("loss_quantity >= 0", name="loss_quantity_nonnegative"),
        CheckConstraint("loss_weight_kg >= 0", name="loss_weight_nonnegative"),
        CheckConstraint("net_quantity >= 0", name="net_quantity_nonnegative"),
        CheckConstraint("net_weight_kg >= 0", name="net_weight_nonnegative"),
        CheckConstraint("loss_quantity <= gross_quantity", name="loss_quantity_within_gross"),
        CheckConstraint("loss_weight_kg <= gross_weight_kg", name="loss_weight_within_gross"),
        CheckConstraint("capitalized_cost >= 0", name="capitalized_cost_nonnegative"),
        CheckConstraint("inventory_unit_cost >= 0", name="inventory_unit_cost_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    purchase_receipt_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("purchase_receipts.id", ondelete="CASCADE"), nullable=False
    )
    purchase_order_line_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"), nullable=False
    )
    inventory_transaction_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT"), nullable=False
    )
    lot_number: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    gross_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    gross_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    loss_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    loss_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    net_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    net_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    capitalized_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    inventory_unit_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)


class SupplierInvoice(TimestampMixin, Base):
    __tablename__ = "supplier_invoices"
    __table_args__ = (
        UniqueConstraint("invoice_number"),
        UniqueConstraint("purchase_order_id"),
        UniqueConstraint("supplier_id", "supplier_invoice_number"),
        CheckConstraint("status IN ('draft', 'posted', 'reversed')", name="status_valid"),
        CheckConstraint("total >= 0", name="total_nonnegative"),
        CheckConstraint("version > 0", name="version_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False)
    supplier_invoice_number: Mapped[str] = mapped_column(String(80), nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    total: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
