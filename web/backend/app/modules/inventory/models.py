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


class InventoryLot(TimestampMixin, Base):
    __tablename__ = "inventory_lots"
    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_id", "normalized_lot_number"),
        Index("ix_inventory_lots_product_warehouse", "product_id", "warehouse_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    lot_number: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_lot_number: Mapped[str] = mapped_column(String(80), nullable=False)


class InventoryLayer(TimestampMixin, Base):
    __tablename__ = "inventory_layers"
    __table_args__ = (
        CheckConstraint("quantity_received >= 0", name="quantity_received_nonnegative"),
        CheckConstraint("quantity_remaining >= 0", name="quantity_remaining_nonnegative"),
        CheckConstraint(
            "quantity_remaining <= quantity_received", name="quantity_remaining_within_received"
        ),
        CheckConstraint("weight_received_kg >= 0", name="weight_received_nonnegative"),
        CheckConstraint("weight_remaining_kg >= 0", name="weight_remaining_nonnegative"),
        CheckConstraint(
            "weight_remaining_kg <= weight_received_kg", name="weight_remaining_within_received"
        ),
        CheckConstraint("unit_cost >= 0", name="unit_cost_nonnegative"),
        CheckConstraint("cost_basis IN ('quantity', 'weight')", name="cost_basis_valid"),
        CheckConstraint(
            "quantity_received > 0 OR weight_received_kg > 0", name="received_amount_positive"
        ),
        Index(
            "ix_inventory_layers_fifo",
            "product_id",
            "warehouse_id",
            "received_at",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    lot_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_lots.id", ondelete="RESTRICT")
    )
    source_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(80))
    source_line_id: Mapped[str | None] = mapped_column(String(80))
    cost_basis: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    quantity_remaining: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    weight_received_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    weight_remaining_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        CheckConstraint(
            "quantity_delta <> 0 OR weight_delta_kg <> 0", name="movement_amount_nonzero"
        ),
        CheckConstraint("unit_cost >= 0", name="unit_cost_nonnegative"),
        CheckConstraint("total_cost >= 0", name="total_cost_nonnegative"),
        CheckConstraint(
            "transaction_type IN ('receipt', 'issue', 'transfer_out', 'transfer_in', "
            "'adjustment_in', 'adjustment_out', 'return_in', 'return_out', "
            "'production_issue', 'production_output')",
            name="transaction_type_valid",
        ),
        Index(
            "ix_inventory_transactions_stock_card",
            "product_id",
            "warehouse_id",
            "posted_at",
        ),
        Index("ix_inventory_transactions_reference", "reference_type", "reference_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    lot_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_lots.id", ondelete="RESTRICT")
    )
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    weight_delta_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(60), nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(80))
    reference_line_id: Mapped[str | None] = mapped_column(String(80))
    reversal_of_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT")
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    posted_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InventoryAllocation(TimestampMixin, Base):
    __tablename__ = "inventory_allocations"
    __table_args__ = (
        UniqueConstraint("outbound_transaction_id", "source_layer_id"),
        CheckConstraint("quantity >= 0", name="quantity_nonnegative"),
        CheckConstraint("weight_kg >= 0", name="weight_nonnegative"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_nonnegative"),
        CheckConstraint("total_cost >= 0", name="total_cost_nonnegative"),
        CheckConstraint("quantity > 0 OR weight_kg > 0", name="allocated_amount_positive"),
        Index("ix_inventory_allocations_layer", "source_layer_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    outbound_transaction_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT"), nullable=False
    )
    source_layer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("inventory_layers.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)


class InventoryBalance(TimestampMixin, Base):
    __tablename__ = "inventory_balances"
    __table_args__ = (
        CheckConstraint("quantity_on_hand >= 0", name="quantity_nonnegative"),
        CheckConstraint("weight_on_hand_kg >= 0", name="weight_nonnegative"),
        CheckConstraint("version > 0", name="version_positive"),
    )

    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), primary_key=True
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="RESTRICT"), primary_key=True
    )
    quantity_on_hand: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    weight_on_hand_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
