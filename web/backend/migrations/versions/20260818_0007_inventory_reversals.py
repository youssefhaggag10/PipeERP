"""Store inventory cost basis and enforce one compensating reversal."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0007"
down_revision: str | None = "20260818_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inventory_transactions",
        sa.Column("cost_basis", sa.String(length=16), nullable=True),
    )
    op.execute(
        "UPDATE inventory_transactions SET cost_basis = "
        "CASE WHEN quantity_delta = 0 THEN 'weight' ELSE 'quantity' END"
    )
    op.alter_column("inventory_transactions", "cost_basis", nullable=False)
    op.create_check_constraint(
        op.f("ck_inventory_transactions_cost_basis_valid"),
        "inventory_transactions",
        "cost_basis IN ('quantity', 'weight')",
    )
    op.drop_constraint(
        op.f("ck_inventory_transactions_transaction_type_valid"),
        "inventory_transactions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_inventory_transactions_transaction_type_valid"),
        "inventory_transactions",
        "transaction_type IN ('receipt', 'issue', 'transfer_out', 'transfer_in', "
        "'adjustment_in', 'adjustment_out', 'return_in', 'return_out', "
        "'production_issue', 'production_output', 'reversal_in', 'reversal_out')",
    )
    op.create_index(
        "ux_inventory_transactions_reversal",
        "inventory_transactions",
        ["reversal_of_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_inventory_transactions_reversal", table_name="inventory_transactions")
    op.drop_constraint(
        op.f("ck_inventory_transactions_transaction_type_valid"),
        "inventory_transactions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_inventory_transactions_transaction_type_valid"),
        "inventory_transactions",
        "transaction_type IN ('receipt', 'issue', 'transfer_out', 'transfer_in', "
        "'adjustment_in', 'adjustment_out', 'return_in', 'return_out', "
        "'production_issue', 'production_output')",
    )
    op.drop_constraint(
        op.f("ck_inventory_transactions_cost_basis_valid"),
        "inventory_transactions",
        type_="check",
    )
    op.drop_column("inventory_transactions", "cost_basis")
