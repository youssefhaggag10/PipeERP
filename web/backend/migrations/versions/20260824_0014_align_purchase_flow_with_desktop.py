"""Align the purchase order fields and flow with the desktop reference."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0014"
down_revision: str | None = "20260821_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "purchase_order_lines",
        sa.Column("lot_number", sa.String(80), nullable=False, server_default=""),
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column(
            "purchase_loss_quantity", sa.Numeric(20, 6), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column("net_quantity", sa.Numeric(20, 6), nullable=False, server_default="0"),
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column(
            "inventory_unit_cost", sa.Numeric(20, 6), nullable=False, server_default="0"
        ),
    )
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(
            sa.text(
                "UPDATE purchase_order_lines "
                "SET lot_number = 'PUR-LEGACY-' || id::text, "
                "net_quantity = ordered_quantity, "
                "inventory_unit_cost = unit_price + additional_unit_cost"
            )
        )
    else:
        connection.execute(
            sa.text(
                "UPDATE purchase_order_lines "
                "SET lot_number = 'PUR-LEGACY-' || CAST(id AS TEXT), "
                "net_quantity = ordered_quantity, "
                "inventory_unit_cost = unit_price + additional_unit_cost"
            )
        )
    connection.execute(
        sa.text("UPDATE purchase_orders SET status = 'draft' WHERE status = 'approved'")
    )
    op.create_check_constraint(
        op.f("ck_purchase_order_lines_purchase_loss_nonnegative"),
        "purchase_order_lines",
        "purchase_loss_quantity >= 0",
    )
    op.create_check_constraint(
        op.f("ck_purchase_order_lines_purchase_loss_within_order"),
        "purchase_order_lines",
        "ordered_quantity = 0 OR purchase_loss_quantity < ordered_quantity",
    )
    op.create_check_constraint(
        op.f("ck_purchase_order_lines_net_quantity_nonnegative"),
        "purchase_order_lines",
        "net_quantity >= 0",
    )
    op.create_check_constraint(
        op.f("ck_purchase_order_lines_inventory_unit_cost_nonnegative"),
        "purchase_order_lines",
        "inventory_unit_cost >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_purchase_order_lines_inventory_unit_cost_nonnegative"),
        "purchase_order_lines",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_purchase_order_lines_net_quantity_nonnegative"),
        "purchase_order_lines",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_purchase_order_lines_purchase_loss_within_order"),
        "purchase_order_lines",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_purchase_order_lines_purchase_loss_nonnegative"),
        "purchase_order_lines",
        type_="check",
    )
    op.drop_column("purchase_order_lines", "inventory_unit_cost")
    op.drop_column("purchase_order_lines", "net_quantity")
    op.drop_column("purchase_order_lines", "purchase_loss_quantity")
    op.drop_column("purchase_order_lines", "lot_number")
