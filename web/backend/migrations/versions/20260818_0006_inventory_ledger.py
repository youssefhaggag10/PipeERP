"""Create immutable inventory ledger, FIFO layers, allocations, and balances."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0006"
down_revision: str | None = "20260818_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "inventory_lots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("lot_number", sa.String(length=80), nullable=False),
        sa.Column("normalized_lot_number", sa.String(length=80), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_lots_product_id_products"),
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_lots_warehouse_id_warehouses"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_lots")),
        sa.UniqueConstraint(
            "product_id",
            "warehouse_id",
            "normalized_lot_number",
            name=op.f("uq_inventory_lots_product_id"),
        ),
    )
    op.create_index(
        "ix_inventory_lots_product_warehouse",
        "inventory_lots",
        ["product_id", "warehouse_id"],
        unique=False,
    )

    op.create_table(
        "inventory_layers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("lot_id", sa.Uuid()),
        sa.Column("source_type", sa.String(length=60), nullable=False),
        sa.Column("source_id", sa.String(length=80)),
        sa.Column("source_line_id", sa.String(length=80)),
        sa.Column("cost_basis", sa.String(length=16), nullable=False),
        sa.Column("quantity_received", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("quantity_remaining", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("weight_received_kg", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("weight_remaining_kg", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "cost_basis IN ('quantity', 'weight')",
            name=op.f("ck_inventory_layers_cost_basis_valid"),
        ),
        sa.CheckConstraint(
            "quantity_received >= 0", name=op.f("ck_inventory_layers_quantity_received_nonnegative")
        ),
        sa.CheckConstraint(
            "quantity_remaining >= 0",
            name=op.f("ck_inventory_layers_quantity_remaining_nonnegative"),
        ),
        sa.CheckConstraint(
            "quantity_remaining <= quantity_received",
            name=op.f("ck_inventory_layers_quantity_remaining_within_received"),
        ),
        sa.CheckConstraint(
            "weight_received_kg >= 0", name=op.f("ck_inventory_layers_weight_received_nonnegative")
        ),
        sa.CheckConstraint(
            "weight_remaining_kg >= 0",
            name=op.f("ck_inventory_layers_weight_remaining_nonnegative"),
        ),
        sa.CheckConstraint(
            "weight_remaining_kg <= weight_received_kg",
            name=op.f("ck_inventory_layers_weight_remaining_within_received"),
        ),
        sa.CheckConstraint(
            "unit_cost >= 0", name=op.f("ck_inventory_layers_unit_cost_nonnegative")
        ),
        sa.CheckConstraint(
            "quantity_received > 0 OR weight_received_kg > 0",
            name=op.f("ck_inventory_layers_received_amount_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["inventory_lots.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_layers_lot_id_inventory_lots"),
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_layers_product_id_products"),
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_layers_warehouse_id_warehouses"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_layers")),
    )
    op.create_index(
        "ix_inventory_layers_fifo",
        "inventory_layers",
        ["product_id", "warehouse_id", "received_at", "id"],
        unique=False,
    )

    op.create_table(
        "inventory_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("lot_id", sa.Uuid()),
        sa.Column("quantity_delta", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("weight_delta_kg", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("total_cost", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("reference_type", sa.String(length=60), nullable=False),
        sa.Column("reference_id", sa.String(length=80)),
        sa.Column("reference_line_id", sa.String(length=80)),
        sa.Column("reversal_of_id", sa.Uuid()),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("posted_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "posted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "quantity_delta <> 0 OR weight_delta_kg <> 0",
            name=op.f("ck_inventory_transactions_movement_amount_nonzero"),
        ),
        sa.CheckConstraint(
            "unit_cost >= 0", name=op.f("ck_inventory_transactions_unit_cost_nonnegative")
        ),
        sa.CheckConstraint(
            "total_cost >= 0", name=op.f("ck_inventory_transactions_total_cost_nonnegative")
        ),
        sa.CheckConstraint(
            "transaction_type IN ('receipt', 'issue', 'transfer_out', 'transfer_in', "
            "'adjustment_in', 'adjustment_out', 'return_in', 'return_out', "
            "'production_issue', 'production_output')",
            name=op.f("ck_inventory_transactions_transaction_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["inventory_lots.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_transactions_lot_id_inventory_lots"),
        ),
        sa.ForeignKeyConstraint(
            ["posted_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_transactions_posted_by_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_transactions_product_id_products"),
        ),
        sa.ForeignKeyConstraint(
            ["reversal_of_id"],
            ["inventory_transactions.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_transactions_reversal_of_id_inventory_transactions"),
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_transactions_warehouse_id_warehouses"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_transactions")),
        sa.UniqueConstraint(
            "idempotency_key", name=op.f("uq_inventory_transactions_idempotency_key")
        ),
    )
    op.create_index(
        "ix_inventory_transactions_reference",
        "inventory_transactions",
        ["reference_type", "reference_id"],
        unique=False,
    )
    op.create_index(
        "ix_inventory_transactions_stock_card",
        "inventory_transactions",
        ["product_id", "warehouse_id", "posted_at"],
        unique=False,
    )

    op.create_table(
        "inventory_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("outbound_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("source_layer_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("total_cost", sa.Numeric(precision=20, scale=6), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "quantity >= 0", name=op.f("ck_inventory_allocations_quantity_nonnegative")
        ),
        sa.CheckConstraint(
            "weight_kg >= 0", name=op.f("ck_inventory_allocations_weight_nonnegative")
        ),
        sa.CheckConstraint(
            "unit_cost >= 0", name=op.f("ck_inventory_allocations_unit_cost_nonnegative")
        ),
        sa.CheckConstraint(
            "total_cost >= 0", name=op.f("ck_inventory_allocations_total_cost_nonnegative")
        ),
        sa.CheckConstraint(
            "quantity > 0 OR weight_kg > 0",
            name=op.f("ck_inventory_allocations_allocated_amount_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["outbound_transaction_id"],
            ["inventory_transactions.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_allocations_outbound_transaction_id_inventory_transactions"),
        ),
        sa.ForeignKeyConstraint(
            ["source_layer_id"],
            ["inventory_layers.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_allocations_source_layer_id_inventory_layers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_allocations")),
        sa.UniqueConstraint(
            "outbound_transaction_id",
            "source_layer_id",
            name=op.f("uq_inventory_allocations_outbound_transaction_id"),
        ),
    )
    op.create_index(
        "ix_inventory_allocations_layer", "inventory_allocations", ["source_layer_id"], unique=False
    )

    op.create_table(
        "inventory_balances",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_on_hand", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("weight_on_hand_kg", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "quantity_on_hand >= 0", name=op.f("ck_inventory_balances_quantity_nonnegative")
        ),
        sa.CheckConstraint(
            "weight_on_hand_kg >= 0", name=op.f("ck_inventory_balances_weight_nonnegative")
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_inventory_balances_version_positive")),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_balances_product_id_products"),
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            ondelete="RESTRICT",
            name=op.f("fk_inventory_balances_warehouse_id_warehouses"),
        ),
        sa.PrimaryKeyConstraint("product_id", "warehouse_id", name=op.f("pk_inventory_balances")),
    )


def downgrade() -> None:
    op.drop_table("inventory_balances")
    op.drop_index("ix_inventory_allocations_layer", table_name="inventory_allocations")
    op.drop_table("inventory_allocations")
    op.drop_index("ix_inventory_transactions_stock_card", table_name="inventory_transactions")
    op.drop_index("ix_inventory_transactions_reference", table_name="inventory_transactions")
    op.drop_table("inventory_transactions")
    op.drop_index("ix_inventory_layers_fifo", table_name="inventory_layers")
    op.drop_table("inventory_layers")
    op.drop_index("ix_inventory_lots_product_warehouse", table_name="inventory_lots")
    op.drop_table("inventory_lots")
