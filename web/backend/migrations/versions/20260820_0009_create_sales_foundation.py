"""create sales, weight-card, delivery, invoice and quotation foundation

Revision ID: 20260820_0009
Revises: 20260818_0008
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0009"
down_revision: str | None = "20260818_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "sales_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_number", sa.String(40), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("billing_method", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column(
            "order_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("subtotal", sa.Numeric(20, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("transport_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("total", sa.Numeric(20, 2), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('draft','delivered','reversed','cancelled')",
            name=op.f("ck_sales_orders_status_valid"),
        ),
        sa.CheckConstraint(
            "billing_method IN ('piece','weight')",
            name=op.f("ck_sales_orders_billing_method_valid"),
        ),
        sa.CheckConstraint("subtotal >= 0", name=op.f("ck_sales_orders_subtotal_nonnegative")),
        sa.CheckConstraint(
            "discount_amount >= 0", name=op.f("ck_sales_orders_discount_nonnegative")
        ),
        sa.CheckConstraint(
            "transport_amount >= 0", name=op.f("ck_sales_orders_transport_nonnegative")
        ),
        sa.CheckConstraint("tax_amount >= 0", name=op.f("ck_sales_orders_tax_nonnegative")),
        sa.CheckConstraint("total >= 0", name=op.f("ck_sales_orders_total_nonnegative")),
        sa.CheckConstraint("version > 0", name=op.f("ck_sales_orders_version_positive")),
        sa.ForeignKeyConstraint(["customer_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_number"),
    )
    op.create_index("ix_sales_orders_customer_status", "sales_orders", ["customer_id", "status"])
    op.create_table(
        "sales_order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("unit_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("line_total", sa.Numeric(20, 2), nullable=False),
        sa.Column("standard_weight_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("billing_weight_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("price_per_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_sales_order_lines_quantity_positive")),
        sa.CheckConstraint(
            "unit_price >= 0", name=op.f("ck_sales_order_lines_unit_price_nonnegative")
        ),
        sa.CheckConstraint(
            "line_total >= 0", name=op.f("ck_sales_order_lines_line_total_nonnegative")
        ),
        sa.CheckConstraint(
            "standard_weight_kg >= 0", name=op.f("ck_sales_order_lines_standard_weight_nonnegative")
        ),
        sa.CheckConstraint(
            "billing_weight_kg >= 0", name=op.f("ck_sales_order_lines_billing_weight_nonnegative")
        ),
        sa.CheckConstraint(
            "price_per_kg >= 0", name=op.f("ck_sales_order_lines_price_per_kg_nonnegative")
        ),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sales_order_id", "product_id"),
    )
    op.create_index("ix_sales_order_lines_order", "sales_order_lines", ["sales_order_id", "id"])
    op.create_table(
        "sales_weight_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("card_number", sa.String(40), nullable=False),
        sa.Column(
            "card_date", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("vehicle_number", sa.String(80), nullable=False),
        sa.Column("gross_weight_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("tare_weight_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("net_weight_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("weight_mode", sa.String(20), nullable=False),
        sa.Column("pricing_mode", sa.String(20), nullable=False),
        sa.Column("uniform_price_per_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("subtotal", sa.Numeric(20, 2), nullable=False),
        sa.Column("use_vehicle_scale", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('draft','posted','cancelled')",
            name=op.f("ck_sales_weight_cards_status_valid"),
        ),
        sa.CheckConstraint(
            "weight_mode IN ('total_card','per_line')",
            name=op.f("ck_sales_weight_cards_weight_mode_valid"),
        ),
        sa.CheckConstraint(
            "pricing_mode IN ('uniform','per_line')",
            name=op.f("ck_sales_weight_cards_pricing_mode_valid"),
        ),
        sa.CheckConstraint(
            "gross_weight_kg >= 0", name=op.f("ck_sales_weight_cards_gross_nonnegative")
        ),
        sa.CheckConstraint(
            "tare_weight_kg >= 0", name=op.f("ck_sales_weight_cards_tare_nonnegative")
        ),
        sa.CheckConstraint("net_weight_kg > 0", name=op.f("ck_sales_weight_cards_net_positive")),
        sa.CheckConstraint(
            "uniform_price_per_kg >= 0",
            name=op.f("ck_sales_weight_cards_uniform_price_nonnegative"),
        ),
        sa.CheckConstraint(
            "subtotal >= 0", name=op.f("ck_sales_weight_cards_subtotal_nonnegative")
        ),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("card_number"),
    )
    op.create_index(
        "ix_sales_weight_cards_order", "sales_weight_cards", ["sales_order_id", "created_at"]
    )
    op.create_table(
        "sales_weight_card_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("weight_card_id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_line_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_pieces", sa.Numeric(20, 6), nullable=False),
        sa.Column("standard_weight_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("theoretical_weight_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("actual_weight_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("price_per_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("line_total", sa.Numeric(20, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "quantity_pieces > 0", name=op.f("ck_sales_weight_card_lines_pieces_positive")
        ),
        sa.CheckConstraint(
            "standard_weight_kg >= 0",
            name=op.f("ck_sales_weight_card_lines_standard_weight_nonnegative"),
        ),
        sa.CheckConstraint(
            "theoretical_weight_kg >= 0",
            name=op.f("ck_sales_weight_card_lines_theoretical_weight_nonnegative"),
        ),
        sa.CheckConstraint(
            "actual_weight_kg > 0", name=op.f("ck_sales_weight_card_lines_actual_weight_positive")
        ),
        sa.CheckConstraint(
            "price_per_kg >= 0", name=op.f("ck_sales_weight_card_lines_price_nonnegative")
        ),
        sa.CheckConstraint(
            "line_total >= 0", name=op.f("ck_sales_weight_card_lines_line_total_nonnegative")
        ),
        sa.ForeignKeyConstraint(["weight_card_id"], ["sales_weight_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["sales_order_line_id"], ["sales_order_lines.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("weight_card_id", "sales_order_line_id"),
    )
    op.create_index(
        "ix_sales_weight_card_lines_card", "sales_weight_card_lines", ["weight_card_id", "id"]
    )
    op.create_table(
        "sales_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("delivery_number", sa.String(40), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("posted_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "posted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("reversal_idempotency_key", sa.String(120), nullable=True),
        sa.Column("reversed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "status IN ('posted','reversed')", name=op.f("ck_sales_deliveries_status_valid")
        ),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reversed_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delivery_number"),
        sa.UniqueConstraint("sales_order_id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("reversal_idempotency_key"),
    )
    op.create_table(
        "customer_invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invoice_number", sa.String(40), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "invoice_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("subtotal", sa.Numeric(20, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("transport_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("total", sa.Numeric(20, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column(
            "posted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "invoice_type IN ('standard','weight')",
            name=op.f("ck_customer_invoices_invoice_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('posted','reversed')", name=op.f("ck_customer_invoices_status_valid")
        ),
        sa.CheckConstraint("subtotal >= 0", name=op.f("ck_customer_invoices_subtotal_nonnegative")),
        sa.CheckConstraint(
            "discount_amount >= 0", name=op.f("ck_customer_invoices_discount_nonnegative")
        ),
        sa.CheckConstraint(
            "transport_amount >= 0", name=op.f("ck_customer_invoices_transport_nonnegative")
        ),
        sa.CheckConstraint("tax_amount >= 0", name=op.f("ck_customer_invoices_tax_nonnegative")),
        sa.CheckConstraint("total >= 0", name=op.f("ck_customer_invoices_total_nonnegative")),
        sa.CheckConstraint("version > 0", name=op.f("ck_customer_invoices_version_positive")),
        sa.ForeignKeyConstraint(["sales_order_id"], ["sales_orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number"),
        sa.UniqueConstraint("sales_order_id"),
    )
    op.create_index(
        "ix_customer_invoices_customer_status", "customer_invoices", ["customer_id", "status"]
    )
    op.create_table(
        "sales_delivery_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sales_delivery_id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_line_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("weight_kg", sa.Numeric(20, 6), nullable=False),
        sa.Column("cost_amount", sa.Numeric(20, 6), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_sales_delivery_lines_quantity_positive")),
        sa.CheckConstraint(
            "weight_kg >= 0", name=op.f("ck_sales_delivery_lines_weight_nonnegative")
        ),
        sa.CheckConstraint(
            "cost_amount >= 0", name=op.f("ck_sales_delivery_lines_cost_nonnegative")
        ),
        sa.ForeignKeyConstraint(["sales_delivery_id"], ["sales_deliveries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["sales_order_line_id"], ["sales_order_lines.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["inventory_transaction_id"], ["inventory_transactions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sales_delivery_id", "sales_order_line_id"),
        sa.UniqueConstraint("inventory_transaction_id"),
    )
    op.create_table(
        "sales_quotations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quotation_number", sa.String(40), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column(
            "quotation_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("total", sa.Numeric(20, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('draft','sent','accepted','rejected','cancelled')",
            name=op.f("ck_sales_quotations_status_valid"),
        ),
        sa.CheckConstraint("total >= 0", name=op.f("ck_sales_quotations_total_nonnegative")),
        sa.CheckConstraint("version > 0", name=op.f("ck_sales_quotations_version_positive")),
        sa.ForeignKeyConstraint(["customer_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quotation_number"),
    )
    op.create_index(
        "ix_sales_quotations_customer_date", "sales_quotations", ["customer_id", "quotation_date"]
    )
    op.create_table(
        "sales_quotation_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quotation_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("item_name", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("unit_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("line_total", sa.Numeric(20, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_sales_quotation_lines_quantity_positive")),
        sa.CheckConstraint(
            "unit_price >= 0", name=op.f("ck_sales_quotation_lines_unit_price_nonnegative")
        ),
        sa.CheckConstraint(
            "line_total >= 0", name=op.f("ck_sales_quotation_lines_line_total_nonnegative")
        ),
        sa.ForeignKeyConstraint(["quotation_id"], ["sales_quotations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sales_quotation_lines_quotation", "sales_quotation_lines", ["quotation_id", "id"]
    )

    # Master data already seeds sales_order, sales_invoice and weight_card.  Use
    # portable, idempotent inserts so this migration is also safe for databases
    # created by an earlier release and keeps their current sequence counters.
    for document_type, prefix in (
        ("sales_order", "SO-"),
        ("sales_delivery", "SD-"),
        ("sales_invoice", "SI-"),
        ("weight_card", "WC-"),
        ("sales_quotation", "QT-"),
    ):
        op.execute(
            sa.text(
                "INSERT INTO document_sequences "
                "(document_type, prefix, next_value, padding, version) "
                "SELECT :document_type, :prefix, 1, 6, 1 "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM document_sequences WHERE document_type = :document_type"
                ")"
            ).bindparams(document_type=document_type, prefix=prefix)
        )


def downgrade() -> None:
    # Do not remove the sales/order/invoice/weight sequences owned by the
    # master-data migration when rolling only this migration back.
    op.execute(
        "DELETE FROM document_sequences "
        "WHERE document_type IN ('sales_delivery','sales_quotation')"
    )
    for table in (
        "sales_quotation_lines",
        "sales_quotations",
        "sales_delivery_lines",
        "customer_invoices",
        "sales_deliveries",
        "sales_weight_card_lines",
        "sales_weight_cards",
        "sales_order_lines",
        "sales_orders",
    ):
        op.drop_table(table)
