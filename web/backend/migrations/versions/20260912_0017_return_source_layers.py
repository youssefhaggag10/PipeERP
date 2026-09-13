"""Add auditable source-layer provenance to invoice returns.

Revision ID: 20260912_0017
Revises: 20260824_0016
Create Date: 2026-09-12 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260912_0017"
down_revision: str | None = "20260824_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _backfill_deterministic_receipt_layers(connection: sa.Connection) -> None:
    purchase_receipts = connection.execute(
        sa.text(
            """
            SELECT prl.inventory_transaction_id AS transaction_id,
                   it.product_id, it.warehouse_id,
                   pr.id AS receipt_id,
                   prl.purchase_order_line_id AS purchase_order_line_id
            FROM purchase_receipt_lines prl
            JOIN purchase_receipts pr ON pr.id = prl.purchase_receipt_id
            JOIN inventory_transactions it ON it.id = prl.inventory_transaction_id
            WHERE pr.status = 'posted'
              AND it.transaction_type = 'receipt'
              AND it.reference_type = 'purchase_receipt'
              AND NOT EXISTS (
                  SELECT 1 FROM inventory_transactions reversal
                  WHERE reversal.reversal_of_id = it.id
              )
            ORDER BY pr.posted_at, pr.id, prl.id
            """
        )
    ).mappings()
    for receipt in purchase_receipts:
        matches = connection.execute(
            sa.text(
                """
                SELECT id
                FROM inventory_layers
                WHERE product_id = :product_id
                  AND warehouse_id = :warehouse_id
                  AND source_type = 'purchase_receipt'
                  AND source_id = :receipt_id
                  AND source_line_id = :purchase_order_line_id
                  AND source_transaction_id IS NULL
                ORDER BY received_at, id
                """
            ),
            {
                "product_id": receipt["product_id"],
                "warehouse_id": receipt["warehouse_id"],
                "receipt_id": str(receipt["receipt_id"]),
                "purchase_order_line_id": str(receipt["purchase_order_line_id"]),
            },
        ).scalars().all()
        if len(matches) == 1:
            connection.execute(
                sa.text(
                    """
                    UPDATE inventory_layers
                    SET source_transaction_id = :transaction_id
                    WHERE id = :layer_id AND source_transaction_id IS NULL
                    """
                ),
                {
                    "transaction_id": receipt["transaction_id"],
                    "layer_id": matches[0],
                },
            )

    transactions = connection.execute(
        sa.text(
            """
            SELECT id, product_id, warehouse_id, reference_type, reference_id,
                   reference_line_id
            FROM inventory_transactions
            WHERE transaction_type IN (
                'receipt', 'transfer_in', 'adjustment_in', 'return_in',
                'production_output', 'reversal_in'
            )
            ORDER BY posted_at, id
            """
        )
    ).mappings()
    for transaction in transactions:
        matches = connection.execute(
            sa.text(
                """
                SELECT id
                FROM inventory_layers
                WHERE product_id = :product_id
                  AND warehouse_id = :warehouse_id
                  AND source_type = :source_type
                  AND ((source_id = :source_id) OR (source_id IS NULL AND :source_id IS NULL))
                  AND ((source_line_id = :source_line_id)
                       OR (source_line_id IS NULL AND :source_line_id IS NULL))
                  AND source_transaction_id IS NULL
                ORDER BY received_at, id
                """
            ),
            {
                "product_id": transaction["product_id"],
                "warehouse_id": transaction["warehouse_id"],
                "source_type": transaction["reference_type"],
                "source_id": transaction["reference_id"],
                "source_line_id": transaction["reference_line_id"],
            },
        ).scalars().all()
        if len(matches) == 1:
            connection.execute(
                sa.text(
                    """
                    UPDATE inventory_layers
                    SET source_transaction_id = :transaction_id
                    WHERE id = :layer_id AND source_transaction_id IS NULL
                    """
                ),
                {"transaction_id": transaction["id"], "layer_id": matches[0]},
            )


def upgrade() -> None:
    with op.batch_alter_table("inventory_layers") as batch:
        batch.add_column(sa.Column("source_transaction_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("provenance_root_layer_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_inventory_layers_source_transaction_id_inventory_transactions"),
            "inventory_transactions",
            ["source_transaction_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            op.f("fk_inventory_layers_provenance_root_layer_id_inventory_layers"),
            "inventory_layers",
            ["provenance_root_layer_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint(
            op.f("uq_inventory_layers_source_transaction_id"),
            ["source_transaction_id"],
        )
    op.create_index(
        "ix_inventory_layers_provenance",
        "inventory_layers",
        ["provenance_root_layer_id", "product_id", "warehouse_id"],
        unique=False,
    )

    op.add_column(
        "invoice_returns",
        sa.Column(
            "valuation_method",
            sa.String(length=24),
            nullable=False,
            server_default="legacy_aggregate",
        ),
    )
    with op.batch_alter_table("invoice_returns") as batch:
        batch.create_check_constraint(
            op.f("ck_invoice_returns_valuation_method_valid"),
            "valuation_method IN ('legacy_aggregate','source_layer')",
        )
    op.execute(
        sa.text(
            "UPDATE invoice_returns SET valuation_method = 'legacy_aggregate' "
            "WHERE valuation_method IS NULL OR valuation_method = ''"
        )
    )

    with op.batch_alter_table("invoice_return_lines") as batch:
        batch.alter_column(
            "inventory_transaction_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )

    op.create_table(
        "invoice_return_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invoice_return_line_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.String(length=40), nullable=False),
        sa.Column("original_inventory_allocation_id", sa.Uuid(), nullable=True),
        sa.Column("purchase_receipt_line_id", sa.Uuid(), nullable=True),
        sa.Column("root_inventory_layer_id", sa.Uuid(), nullable=False),
        sa.Column("consumed_inventory_layer_id", sa.Uuid(), nullable=True),
        sa.Column("return_inventory_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("return_inventory_allocation_id", sa.Uuid(), nullable=True),
        sa.Column("return_inventory_layer_id", sa.Uuid(), nullable=True),
        sa.Column("reversal_inventory_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("reversal_inventory_layer_id", sa.Uuid(), nullable=True),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("weight_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("cost_basis", sa.String(length=16), nullable=False),
        sa.Column("unit_cost", sa.Numeric(20, 6), nullable=False),
        sa.Column("total_cost", sa.Numeric(20, 6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_kind IN ('sales_delivery_allocation','purchase_receipt_layer')",
            name=op.f("ck_invoice_return_sources_source_kind_valid"),
        ),
        sa.CheckConstraint(
            "quantity >= 0", name=op.f("ck_invoice_return_sources_quantity_nonnegative")
        ),
        sa.CheckConstraint(
            "weight_kg >= 0", name=op.f("ck_invoice_return_sources_weight_nonnegative")
        ),
        sa.CheckConstraint(
            "quantity > 0 OR weight_kg > 0",
            name=op.f("ck_invoice_return_sources_amount_positive"),
        ),
        sa.CheckConstraint(
            "cost_basis IN ('quantity','weight')",
            name=op.f("ck_invoice_return_sources_cost_basis_valid"),
        ),
        sa.CheckConstraint(
            "unit_cost >= 0", name=op.f("ck_invoice_return_sources_unit_cost_nonnegative")
        ),
        sa.CheckConstraint(
            "total_cost >= 0", name=op.f("ck_invoice_return_sources_total_cost_nonnegative")
        ),
        sa.CheckConstraint(
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
            name=op.f("ck_invoice_return_sources_source_references_match_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["invoice_return_line_id"],
            ["invoice_return_lines.id"],
            ondelete="CASCADE",
            name=op.f("fk_invoice_return_sources_invoice_return_line_id_invoice_return_lines"),
        ),
        sa.ForeignKeyConstraint(
            ["original_inventory_allocation_id"],
            ["inventory_allocations.id"],
            ondelete="RESTRICT",
            name=op.f(
                "fk_invoice_return_sources_original_inventory_allocation_id_inventory_allocations"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["purchase_receipt_line_id"],
            ["purchase_receipt_lines.id"],
            ondelete="RESTRICT",
            name=op.f(
                "fk_invoice_return_sources_purchase_receipt_line_id_purchase_receipt_lines"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["root_inventory_layer_id"],
            ["inventory_layers.id"],
            ondelete="RESTRICT",
            name=op.f("fk_invoice_return_sources_root_inventory_layer_id_inventory_layers"),
        ),
        sa.ForeignKeyConstraint(
            ["consumed_inventory_layer_id"],
            ["inventory_layers.id"],
            ondelete="RESTRICT",
            name=op.f(
                "fk_invoice_return_sources_consumed_inventory_layer_id_inventory_layers"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["return_inventory_transaction_id"],
            ["inventory_transactions.id"],
            ondelete="RESTRICT",
            name=op.f(
                "fk_invoice_return_sources_return_inventory_transaction_id_inventory_transactions"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["return_inventory_allocation_id"],
            ["inventory_allocations.id"],
            ondelete="RESTRICT",
            name=op.f(
                "fk_invoice_return_sources_return_inventory_allocation_id_inventory_allocations"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["return_inventory_layer_id"],
            ["inventory_layers.id"],
            ondelete="RESTRICT",
            name=op.f("fk_invoice_return_sources_return_inventory_layer_id_inventory_layers"),
        ),
        sa.ForeignKeyConstraint(
            ["reversal_inventory_transaction_id"],
            ["inventory_transactions.id"],
            ondelete="RESTRICT",
            name=op.f(
                "fk_invoice_return_sources_reversal_inventory_transaction_id_inventory_transactions"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["reversal_inventory_layer_id"],
            ["inventory_layers.id"],
            ondelete="RESTRICT",
            name=op.f("fk_invoice_return_sources_reversal_inventory_layer_id_inventory_layers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_return_sources")),
        sa.UniqueConstraint(
            "invoice_return_line_id",
            "original_inventory_allocation_id",
            name="uq_invoice_return_sources_sales_allocation",
        ),
        sa.UniqueConstraint(
            "invoice_return_line_id",
            "consumed_inventory_layer_id",
            name="uq_invoice_return_sources_purchase_layer",
        ),
        sa.UniqueConstraint(
            "return_inventory_transaction_id",
            name=op.f("uq_invoice_return_sources_return_inventory_transaction_id"),
        ),
        sa.UniqueConstraint(
            "return_inventory_allocation_id",
            name=op.f("uq_invoice_return_sources_return_inventory_allocation_id"),
        ),
        sa.UniqueConstraint(
            "return_inventory_layer_id",
            name=op.f("uq_invoice_return_sources_return_inventory_layer_id"),
        ),
        sa.UniqueConstraint(
            "reversal_inventory_transaction_id",
            name=op.f("uq_invoice_return_sources_reversal_inventory_transaction_id"),
        ),
        sa.UniqueConstraint(
            "reversal_inventory_layer_id",
            name=op.f("uq_invoice_return_sources_reversal_inventory_layer_id"),
        ),
    )
    op.create_index(
        "ix_invoice_return_sources_line",
        "invoice_return_sources",
        ["invoice_return_line_id", "id"],
        unique=False,
    )
    op.create_index(
        "ix_invoice_return_sources_original_allocation",
        "invoice_return_sources",
        ["original_inventory_allocation_id"],
        unique=False,
    )
    op.create_index(
        "ix_invoice_return_sources_purchase_receipt_line",
        "invoice_return_sources",
        ["purchase_receipt_line_id"],
        unique=False,
    )
    op.create_index(
        "ix_invoice_return_sources_root_layer",
        "invoice_return_sources",
        ["root_inventory_layer_id"],
        unique=False,
    )
    op.create_index(
        "ix_invoice_return_sources_consumed_layer",
        "invoice_return_sources",
        ["consumed_inventory_layer_id"],
        unique=False,
    )

    _backfill_deterministic_receipt_layers(op.get_bind())


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE invoice_return_lines
            SET inventory_transaction_id = (
                SELECT return_inventory_transaction_id
                FROM invoice_return_sources
                WHERE invoice_return_sources.invoice_return_line_id = invoice_return_lines.id
                ORDER BY invoice_return_sources.id
                LIMIT 1
            )
            WHERE inventory_transaction_id IS NULL
            """
        )
    )
    op.drop_index("ix_invoice_return_sources_consumed_layer", table_name="invoice_return_sources")
    op.drop_index("ix_invoice_return_sources_root_layer", table_name="invoice_return_sources")
    op.drop_index(
        "ix_invoice_return_sources_purchase_receipt_line", table_name="invoice_return_sources"
    )
    op.drop_index(
        "ix_invoice_return_sources_original_allocation", table_name="invoice_return_sources"
    )
    op.drop_index("ix_invoice_return_sources_line", table_name="invoice_return_sources")
    op.drop_table("invoice_return_sources")
    with op.batch_alter_table("invoice_return_lines") as batch:
        batch.alter_column(
            "inventory_transaction_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
    with op.batch_alter_table("invoice_returns") as batch:
        batch.drop_constraint(
            op.f("ck_invoice_returns_valuation_method_valid"), type_="check"
        )
        batch.drop_column("valuation_method")
    op.drop_index("ix_inventory_layers_provenance", table_name="inventory_layers")
    with op.batch_alter_table("inventory_layers") as batch:
        batch.drop_constraint(
            op.f("uq_inventory_layers_source_transaction_id"), type_="unique"
        )
        batch.drop_constraint(
            op.f("fk_inventory_layers_provenance_root_layer_id_inventory_layers"),
            type_="foreignkey",
        )
        batch.drop_constraint(
            op.f("fk_inventory_layers_source_transaction_id_inventory_transactions"),
            type_="foreignkey",
        )
        batch.drop_column("provenance_root_layer_id")
        batch.drop_column("source_transaction_id")
