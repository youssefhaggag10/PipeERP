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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin


class ManufacturingRecipe(TimestampMixin, Base):
    __tablename__ = "manufacturing_recipes"
    __table_args__ = (
        UniqueConstraint("normalized_code"),
        UniqueConstraint("normalized_name"),
        UniqueConstraint("scrap_product_id"),
        CheckConstraint("suggested_scrap_per_batch >= 0", name="scrap_nonnegative"),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_manufacturing_recipes_active", "is_active", "normalized_code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    scrap_product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    suggested_scrap_per_batch: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class ManufacturingRecipeOutput(TimestampMixin, Base):
    __tablename__ = "manufacturing_recipe_outputs"
    __table_args__ = (
        UniqueConstraint("recipe_id", "product_id"),
        Index("ix_manufacturing_recipe_outputs_product", "product_id", "recipe_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    recipe_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("manufacturing_recipes.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )


class ManufacturingRecipeComponent(TimestampMixin, Base):
    __tablename__ = "manufacturing_recipe_components"
    __table_args__ = (
        UniqueConstraint("recipe_id", "product_id"),
        CheckConstraint("quantity_per_batch > 0", name="quantity_positive"),
        CheckConstraint("display_order > 0", name="display_order_positive"),
        Index("ix_manufacturing_recipe_components_recipe", "recipe_id", "display_order"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    recipe_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("manufacturing_recipes.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity_per_batch: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class ManufacturingOrder(TimestampMixin, Base):
    __tablename__ = "manufacturing_orders"
    __table_args__ = (
        UniqueConstraint("order_number"),
        UniqueConstraint("create_idempotency_key"),
        UniqueConstraint("start_idempotency_key"),
        UniqueConstraint("completion_idempotency_key"),
        UniqueConstraint("cancellation_idempotency_key"),
        CheckConstraint(
            "status IN ('draft', 'in_progress', 'completed', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint("planned_batches > 0", name="planned_batches_positive"),
        CheckConstraint("issued_batches >= 0", name="issued_batches_nonnegative"),
        CheckConstraint("actual_batches >= 0", name="actual_batches_nonnegative"),
        CheckConstraint("target_weight_kg > 0", name="target_weight_positive"),
        CheckConstraint("planned_input_weight_kg > 0", name="planned_input_weight_positive"),
        CheckConstraint("material_cost >= 0", name="material_cost_nonnegative"),
        CheckConstraint("finished_cost >= 0", name="finished_cost_nonnegative"),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_manufacturing_orders_status_date", "status", "order_date"),
        Index("ix_manufacturing_orders_recipe_status", "recipe_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    order_number: Mapped[str] = mapped_column(String(40), nullable=False)
    recipe_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("manufacturing_recipes.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    order_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planned_batches: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_batches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_batches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    planned_input_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    returned_scrap_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False, default=0
    )
    material_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    finished_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    weight_variance_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    create_idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    create_request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    start_idempotency_key: Mapped[str | None] = mapped_column(String(120))
    start_request_hash: Mapped[str | None] = mapped_column(String(64))
    completion_idempotency_key: Mapped[str | None] = mapped_column(String(120))
    completion_request_hash: Mapped[str | None] = mapped_column(String(64))
    cancellation_idempotency_key: Mapped[str | None] = mapped_column(String(120))
    cancellation_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    started_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    completed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    cancelled_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ManufacturingOrderOutput(TimestampMixin, Base):
    __tablename__ = "manufacturing_order_outputs"
    __table_args__ = (
        UniqueConstraint("manufacturing_order_id", "product_id"),
        CheckConstraint("planned_quantity > 0", name="planned_quantity_positive"),
        CheckConstraint("standard_weight_kg > 0", name="standard_weight_positive"),
        CheckConstraint("good_quantity >= 0", name="good_quantity_nonnegative"),
        CheckConstraint("defective_quantity >= 0", name="defective_quantity_nonnegative"),
        CheckConstraint("actual_weight_kg >= 0", name="actual_weight_nonnegative"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_nonnegative"),
        CheckConstraint("line_cost >= 0", name="line_cost_nonnegative"),
        Index("ix_manufacturing_order_outputs_order", "manufacturing_order_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    manufacturing_order_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("manufacturing_orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    planned_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    standard_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    good_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    defective_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    actual_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    line_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    inventory_transaction_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT"), unique=True
    )


class ManufacturingOrderMaterial(TimestampMixin, Base):
    __tablename__ = "manufacturing_order_materials"
    __table_args__ = (
        UniqueConstraint("manufacturing_order_id", "product_id"),
        CheckConstraint("component_kind IN ('material', 'scrap')", name="kind_valid"),
        CheckConstraint("quantity_per_batch > 0", name="quantity_per_batch_positive"),
        CheckConstraint("planned_quantity >= 0", name="planned_quantity_nonnegative"),
        CheckConstraint("issued_quantity >= 0", name="issued_quantity_nonnegative"),
        CheckConstraint("used_quantity >= 0", name="used_quantity_nonnegative"),
        CheckConstraint("returned_quantity >= 0", name="returned_quantity_nonnegative"),
        CheckConstraint("issued_cost >= 0", name="issued_cost_nonnegative"),
        CheckConstraint("used_cost >= 0", name="used_cost_nonnegative"),
        Index("ix_manufacturing_order_materials_order", "manufacturing_order_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    manufacturing_order_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("manufacturing_orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    component_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity_per_batch: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    planned_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    issued_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    used_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    returned_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    issued_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    used_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    return_inventory_transaction_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT"), unique=True
    )


class ManufacturingMaterialIssue(TimestampMixin, Base):
    __tablename__ = "manufacturing_material_issues"
    __table_args__ = (
        UniqueConstraint("inventory_transaction_id"),
        UniqueConstraint("reversal_transaction_id"),
        CheckConstraint("issue_kind IN ('initial', 'additional')", name="kind_valid"),
        CheckConstraint("batch_count > 0", name="batch_count_positive"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("weight_kg >= 0", name="weight_nonnegative"),
        CheckConstraint("total_cost >= 0", name="total_cost_nonnegative"),
        Index("ix_manufacturing_material_issues_material", "order_material_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    order_material_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("manufacturing_order_materials.id", ondelete="CASCADE"), nullable=False
    )
    inventory_transaction_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT"), nullable=False
    )
    reversal_transaction_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT")
    )
    issue_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    batch_count: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)


class ManufacturingCompletion(TimestampMixin, Base):
    __tablename__ = "manufacturing_completions"
    __table_args__ = (
        UniqueConstraint("manufacturing_order_id"),
        UniqueConstraint("idempotency_key"),
        UniqueConstraint("scrap_inventory_transaction_id"),
        CheckConstraint("actual_batches > 0", name="actual_batches_positive"),
        CheckConstraint("full_batches >= 0", name="full_batches_nonnegative"),
        CheckConstraint("modified_batches >= 0", name="modified_batches_nonnegative"),
        CheckConstraint("good_output_quantity > 0", name="good_output_positive"),
        CheckConstraint("defective_output_quantity >= 0", name="defective_output_nonnegative"),
        CheckConstraint("actual_output_weight_kg > 0", name="actual_output_weight_positive"),
        CheckConstraint("scrap_weight_kg >= 0", name="scrap_weight_nonnegative"),
        CheckConstraint("used_input_weight_kg > 0", name="used_input_weight_positive"),
        CheckConstraint("full_mix_cost >= 0", name="full_mix_cost_nonnegative"),
        CheckConstraint("modified_mix_cost >= 0", name="modified_mix_cost_nonnegative"),
        CheckConstraint("total_material_cost >= 0", name="total_material_cost_nonnegative"),
        CheckConstraint("finished_cost >= 0", name="finished_cost_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    manufacturing_order_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("manufacturing_orders.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    actual_batches: Mapped[int] = mapped_column(Integer, nullable=False)
    full_batches: Mapped[int] = mapped_column(Integer, nullable=False)
    modified_batches: Mapped[int] = mapped_column(Integer, nullable=False)
    good_output_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    defective_output_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    actual_output_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    scrap_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    used_input_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    full_mix_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    modified_mix_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    total_material_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    average_input_cost_per_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    scrap_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    finished_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    cost_per_good_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    weight_variance_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    scrap_inventory_transaction_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT")
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    completed_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class ManufacturingCompletionOutput(TimestampMixin, Base):
    __tablename__ = "manufacturing_completion_outputs"
    __table_args__ = (
        UniqueConstraint("completion_id", "product_id"),
        UniqueConstraint("inventory_transaction_id"),
        CheckConstraint("good_quantity >= 0", name="good_quantity_nonnegative"),
        CheckConstraint("defective_quantity >= 0", name="defective_quantity_nonnegative"),
        CheckConstraint("actual_weight_kg >= 0", name="actual_weight_nonnegative"),
        CheckConstraint("line_cost >= 0", name="line_cost_nonnegative"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    completion_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("manufacturing_completions.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    good_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    defective_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    actual_weight_kg: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    line_cost: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    inventory_transaction_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("inventory_transactions.id", ondelete="RESTRICT")
    )


class ManufacturingMixAdjustment(TimestampMixin, Base):
    __tablename__ = "manufacturing_mix_adjustments"
    __table_args__ = (
        CheckConstraint("batch_count > 0", name="batch_count_positive"),
        CheckConstraint("cost_amount >= 0", name="cost_nonnegative"),
        Index("ix_manufacturing_mix_adjustments_completion", "completion_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    completion_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("manufacturing_completions.id", ondelete="CASCADE"), nullable=False
    )
    excluded_product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    batch_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    cost_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)


class ManufacturingMixAdjustmentMaterial(TimestampMixin, Base):
    __tablename__ = "manufacturing_mix_adjustment_materials"
    __table_args__ = (
        UniqueConstraint("adjustment_id", "product_id"),
        CheckConstraint("actual_quantity >= 0", name="actual_quantity_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    adjustment_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("manufacturing_mix_adjustments.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    actual_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
