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

USERS_ID = "users.id"


class InvoiceReturn(TimestampMixin, Base):
    __tablename__ = "invoice_returns"
    __table_args__ = (
        UniqueConstraint("return_number"),
        UniqueConstraint("idempotency_key"),
        UniqueConstraint("reversal_idempotency_key"),
        CheckConstraint("return_type IN ('sales','purchase')", name="return_type_valid"),
        CheckConstraint(
            "valuation_method IN ('legacy_aggregate','source_layer')",
            name="valuation_method_valid",
        ),
        CheckConstraint("status IN ('posted','reversed')", name="status_valid"),
        CheckConstraint("total > 0", name="total_positive"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(
            "(return_type = 'sales' AND customer_invoice_id IS NOT NULL "
            "AND supplier_invoice_id IS NULL) OR "
            "(return_type = 'purchase' AND supplier_invoice_id IS NOT NULL "
            "AND customer_invoice_id IS NULL)",
            name="invoice_matches_return_type",
        ),
        Index("ix_invoice_returns_customer_invoice", "customer_invoice_id", "status"),
        Index("ix_invoice_returns_supplier_invoice", "supplier_invoice_id", "status"),
        Index("ix_invoice_returns_partner_date", "partner_id", "return_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    return_number: Mapped[str] = mapped_column(String(40), nullable=False)
    return_type: Mapped[str] = mapped_column(String(16), nullable=False)
    valuation_method: Mapped[str] = mapped_column(
        String(24), nullable=False, default="source_layer"
    )
    customer_invoice_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("customer_invoices.id", ondelete="RESTRICT")
    )
    supplier_invoice_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("supplier_invoices.id", ondelete="RESTRICT")
    )
    partner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    return_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    total: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="posted")
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    posted_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(USERS_ID, ondelete="RESTRICT"), nullable=False
    )
    reversed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey(USERS_ID, ondelete="RESTRICT")
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reversal_idempotency_key: Mapped[str | None] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class InvoiceReturnLine(TimestampMixin, Base):
    __tablename__ = "invoice_return_lines"
    __table_args__ = (
        UniqueConstraint(
            "invoice_return_id",
            "sales_order_line_id",
            name="uq_invoice_return_lines_return_sales_line",
        ),
        UniqueConstraint(
            "invoice_return_id",
            "purchase_order_line_id",
            name="uq_invoice_return_lines_return_purchase_line",
        ),
        UniqueConstraint("inventory_transaction_id"),
        UniqueConstraint("reversal_inventory_transaction_id"),
        CheckConstraint(
            "(sales_order_line_id IS NOT NULL AND purchase_order_line_id IS NULL) OR "
            "(sales_order_line_id IS NULL AND purchase_order_line_id IS NOT NULL)",
            name="exactly_one_source_line",
        ),
        CheckConstraint("quantity >= 0", name="quantity_nonnegative"),
        CheckConstraint("weight_kg >= 0", name="weight_nonnegative"),
        CheckConstraint("quantity > 0 OR weight_kg > 0", name="amount_positive"),
        CheckConstraint("cost_basis IN ('quantity','weight')", name="cost_basis_valid"),
        CheckConstraint("unit_price >= 0", name="unit_price_nonnegative"),
        CheckConstraint("line_total >= 0", name="line_total_nonnegative"),
        CheckConstraint("inventory_cost >= 0", name="inventory_cost_nonnegative"),
        Index("ix_invoice_return_lines_return", "invoice_return_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    invoice_return_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("invoice_returns.id", ondelete="CASCADE"), nullable=False
    )
    sales_order_line_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("sales_order_lines.id", ondelete="RESTRICT")
    )
    purchase_order_line_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("purchase_order_lines.id", ondelete="RESTRICT")
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    inventory_transaction_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT")
    )
    reversal_inventory_transaction_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    cost_basis: Mapped[str] = mapped_column(String(16), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    inventory_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)


class InvoiceReturnSource(TimestampMixin, Base):
    __tablename__ = "invoice_return_sources"
    __table_args__ = (
        UniqueConstraint("return_inventory_transaction_id"),
        UniqueConstraint("return_inventory_allocation_id"),
        UniqueConstraint("return_inventory_layer_id"),
        UniqueConstraint("reversal_inventory_transaction_id"),
        UniqueConstraint("reversal_inventory_layer_id"),
        UniqueConstraint(
            "invoice_return_line_id",
            "original_inventory_allocation_id",
            name="uq_invoice_return_sources_sales_allocation",
        ),
        UniqueConstraint(
            "invoice_return_line_id",
            "consumed_inventory_layer_id",
            name="uq_invoice_return_sources_purchase_layer",
        ),
        CheckConstraint(
            "source_kind IN ('sales_delivery_allocation','purchase_receipt_layer')",
            name="source_kind_valid",
        ),
        CheckConstraint("quantity >= 0", name="quantity_nonnegative"),
        CheckConstraint("weight_kg >= 0", name="weight_nonnegative"),
        CheckConstraint("quantity > 0 OR weight_kg > 0", name="amount_positive"),
        CheckConstraint("cost_basis IN ('quantity','weight')", name="cost_basis_valid"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_nonnegative"),
        CheckConstraint("total_cost >= 0", name="total_cost_nonnegative"),
        CheckConstraint(
            "(source_kind = 'sales_delivery_allocation' "
            "AND original_inventory_allocation_id IS NOT NULL "
            "AND purchase_receipt_line_id IS NULL "
            "AND consumed_inventory_layer_id IS NULL "
            "AND return_inventory_allocation_id IS NULL "
            "AND return_inventory_layer_id IS NOT NULL) OR "
            "(source_kind = 'purchase_receipt_layer' "
            "AND original_inventory_allocation_id IS NULL "
            "AND purchase_receipt_line_id IS NOT NULL "
            "AND consumed_inventory_layer_id IS NOT NULL "
            "AND return_inventory_allocation_id IS NOT NULL "
            "AND return_inventory_layer_id IS NULL)",
            name="source_references_match_kind",
        ),
        Index("ix_invoice_return_sources_line", "invoice_return_line_id", "id"),
        Index(
            "ix_invoice_return_sources_original_allocation",
            "original_inventory_allocation_id",
        ),
        Index(
            "ix_invoice_return_sources_purchase_receipt_line",
            "purchase_receipt_line_id",
        ),
        Index("ix_invoice_return_sources_root_layer", "root_inventory_layer_id"),
        Index("ix_invoice_return_sources_consumed_layer", "consumed_inventory_layer_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    invoice_return_line_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("invoice_return_lines.id", ondelete="CASCADE"), nullable=False
    )
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    original_inventory_allocation_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_allocations.id", ondelete="RESTRICT")
    )
    purchase_receipt_line_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("purchase_receipt_lines.id", ondelete="RESTRICT")
    )
    root_inventory_layer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("inventory_layers.id", ondelete="RESTRICT"), nullable=False
    )
    consumed_inventory_layer_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_layers.id", ondelete="RESTRICT")
    )
    return_inventory_transaction_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT"), nullable=False
    )
    return_inventory_allocation_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_allocations.id", ondelete="RESTRICT")
    )
    return_inventory_layer_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_layers.id", ondelete="RESTRICT")
    )
    reversal_inventory_transaction_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT")
    )
    reversal_inventory_layer_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_layers.id", ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    cost_basis: Mapped[str] = mapped_column(String(16), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)


class ReturnRefund(TimestampMixin, Base):
    __tablename__ = "return_refunds"
    __table_args__ = (
        UniqueConstraint("refund_number"),
        UniqueConstraint("idempotency_key"),
        UniqueConstraint("reversal_idempotency_key"),
        CheckConstraint(
            "refund_type IN ('supplier_refund','customer_refund')",
            name="refund_type_valid",
        ),
        CheckConstraint("status IN ('posted','reversed')", name="status_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(
            "payment_method IN ('cash','bank_transfer','cheque','wallet')",
            name="payment_method_valid",
        ),
        CheckConstraint(
            "(refund_type = 'customer_refund' AND customer_invoice_id IS NOT NULL "
            "AND supplier_invoice_id IS NULL) OR "
            "(refund_type = 'supplier_refund' AND supplier_invoice_id IS NOT NULL "
            "AND customer_invoice_id IS NULL)",
            name="invoice_matches_refund_type",
        ),
        Index("ix_return_refunds_partner_date", "partner_id", "refund_date"),
        Index("ix_return_refunds_account_date", "financial_account_id", "refund_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    refund_number: Mapped[str] = mapped_column(String(40), nullable=False)
    refund_type: Mapped[str] = mapped_column(String(24), nullable=False)
    customer_invoice_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("customer_invoices.id", ondelete="RESTRICT")
    )
    supplier_invoice_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("supplier_invoices.id", ondelete="RESTRICT")
    )
    partner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    financial_account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    refund_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(24), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="posted")
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    posted_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey(USERS_ID, ondelete="RESTRICT"), nullable=False
    )
    reversed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey(USERS_ID, ondelete="RESTRICT")
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reversal_idempotency_key: Mapped[str | None] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
