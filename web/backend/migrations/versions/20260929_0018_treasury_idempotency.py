"""Close treasury idempotency gaps for opening balances and legacy reversals.

Revision ID: 20260929_0018
Revises: 20260912_0017
Create Date: 2026-09-29 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260929_0018"
down_revision: str | None = "20260912_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "partner_opening_balance_entries",
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "partner_opening_balance_entries",
        sa.Column("request_hash", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        op.f("uq_partner_opening_balance_entries_idempotency_key"),
        "partner_opening_balance_entries",
        ["idempotency_key"],
    )
    op.add_column(
        "customer_account_adjustments",
        sa.Column("reversal_idempotency_key", sa.String(length=120), nullable=True),
    )
    op.create_unique_constraint(
        op.f("uq_customer_account_adjustments_reversal_idempotency_key"),
        "customer_account_adjustments",
        ["reversal_idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_customer_account_adjustments_reversal_idempotency_key"),
        "customer_account_adjustments",
        type_="unique",
    )
    op.drop_column("customer_account_adjustments", "reversal_idempotency_key")
    op.drop_constraint(
        op.f("uq_partner_opening_balance_entries_idempotency_key"),
        "partner_opening_balance_entries",
        type_="unique",
    )
    op.drop_column("partner_opening_balance_entries", "request_hash")
    op.drop_column("partner_opening_balance_entries", "idempotency_key")
