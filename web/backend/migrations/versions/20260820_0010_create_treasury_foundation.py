"""create treasury, payments, allocations and partner account foundation

Revision ID: 20260820_0010
Revises: 20260820_0009
Create Date: 2026-08-20
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0010"
down_revision: str | None = "20260820_0009"
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
        "financial_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("normalized_code", sa.String(80), nullable=False),
        sa.Column("name_ar", sa.String(200), nullable=False),
        sa.Column("account_type", sa.String(20), nullable=False),
        sa.Column("opening_balance", sa.Numeric(20, 2), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "account_type IN ('cash','bank','wallet','other')",
            name=op.f("ck_financial_accounts_account_type_valid"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_financial_accounts_version_positive")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_code"),
    )
    op.create_index(
        "uq_financial_accounts_single_default",
        "financial_accounts",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
        sqlite_where=sa.text("is_default = 1"),
    )
    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transaction_number", sa.String(40), nullable=False),
        sa.Column(
            "transaction_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("transaction_type", sa.String(24), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("financial_account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("payment_method", sa.String(24), nullable=False),
        sa.Column("reference_type", sa.String(16), nullable=True),
        sa.Column("reference_id", sa.Uuid(), nullable=True),
        sa.Column("customer_invoice_id", sa.Uuid(), nullable=True),
        sa.Column("supplier_invoice_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("posted_by_id", sa.Uuid(), nullable=False),
        sa.Column("reversal_idempotency_key", sa.String(120), nullable=True),
        sa.Column("reversed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payment_transactions_amount_positive")),
        sa.CheckConstraint(
            "payment_method IN ('cash','bank_transfer','cheque','wallet')",
            name=op.f("ck_payment_transactions_payment_method_valid"),
        ),
        sa.CheckConstraint(
            "reference_type IN ('sale','purchase') OR reference_type IS NULL",
            name=op.f("ck_payment_transactions_reference_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('posted','reversed')",
            name=op.f("ck_payment_transactions_status_valid"),
        ),
        sa.CheckConstraint(
            "transaction_type IN ('customer_receipt','supplier_payment')",
            name=op.f("ck_payment_transactions_transaction_type_valid"),
        ),
        sa.CheckConstraint(
            "(transaction_type = 'customer_receipt' AND supplier_invoice_id IS NULL) OR "
            "(transaction_type = 'supplier_payment' AND customer_invoice_id IS NULL)",
            name=op.f("ck_payment_transactions_invoice_type_matches_transaction"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_invoice_id"], ["customer_invoices.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["financial_account_id"], ["financial_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reversed_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["supplier_invoice_id"], ["supplier_invoices.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("reversal_idempotency_key"),
        sa.UniqueConstraint("transaction_number"),
    )
    op.create_index(
        "ix_payment_transactions_partner_date",
        "payment_transactions",
        ["partner_id", "transaction_date"],
    )
    op.create_index(
        "ix_payment_transactions_account_date",
        "payment_transactions",
        ["financial_account_id", "transaction_date"],
    )
    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("customer_invoice_id", sa.Uuid(), nullable=True),
        sa.Column("supplier_invoice_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payment_allocations_amount_positive")),
        sa.CheckConstraint(
            "(customer_invoice_id IS NOT NULL AND supplier_invoice_id IS NULL) OR "
            "(customer_invoice_id IS NULL AND supplier_invoice_id IS NOT NULL)",
            name=op.f("ck_payment_allocations_exactly_one_invoice"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_invoice_id"], ["customer_invoices.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["payment_transaction_id"], ["payment_transactions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["supplier_invoice_id"], ["supplier_invoices.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "payment_transaction_id",
            "customer_invoice_id",
            name=op.f("uq_payment_allocations_payment_customer_invoice"),
        ),
        sa.UniqueConstraint(
            "payment_transaction_id",
            "supplier_invoice_id",
            name=op.f("uq_payment_allocations_payment_supplier_invoice"),
        ),
    )
    op.create_index(
        "ix_payment_allocations_customer_invoice",
        "payment_allocations",
        ["customer_invoice_id", "id"],
    )
    op.create_index(
        "ix_payment_allocations_supplier_invoice",
        "payment_allocations",
        ["supplier_invoice_id", "id"],
    )
    op.create_table(
        "financial_account_transfers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transfer_number", sa.String(40), nullable=False),
        sa.Column(
            "transfer_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("from_account_id", sa.Uuid(), nullable=False),
        sa.Column("to_account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("posted_by_id", sa.Uuid(), nullable=False),
        sa.Column("reversal_idempotency_key", sa.String(120), nullable=True),
        sa.Column("reversed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "amount > 0", name=op.f("ck_financial_account_transfers_amount_positive")
        ),
        sa.CheckConstraint(
            "from_account_id <> to_account_id",
            name=op.f("ck_financial_account_transfers_different_accounts"),
        ),
        sa.CheckConstraint(
            "status IN ('posted','reversed')",
            name=op.f("ck_financial_account_transfers_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["from_account_id"], ["financial_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["posted_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reversed_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_account_id"], ["financial_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("reversal_idempotency_key"),
        sa.UniqueConstraint("transfer_number"),
    )
    op.create_index(
        "ix_financial_transfers_from_date",
        "financial_account_transfers",
        ["from_account_id", "transfer_date"],
    )
    op.create_index(
        "ix_financial_transfers_to_date",
        "financial_account_transfers",
        ["to_account_id", "transfer_date"],
    )
    op.create_table(
        "financial_account_adjustments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("adjustment_number", sa.String(40), nullable=False),
        sa.Column(
            "adjustment_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("financial_account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("target_balance", sa.Numeric(20, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("posted_by_id", sa.Uuid(), nullable=False),
        sa.Column("reversal_idempotency_key", sa.String(120), nullable=True),
        sa.Column("reversed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "amount <> 0", name=op.f("ck_financial_account_adjustments_amount_nonzero")
        ),
        sa.CheckConstraint(
            "status IN ('posted','reversed')",
            name=op.f("ck_financial_account_adjustments_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["financial_account_id"], ["financial_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["posted_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reversed_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("adjustment_number"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("reversal_idempotency_key"),
    )
    op.create_index(
        "ix_financial_adjustments_account_date",
        "financial_account_adjustments",
        ["financial_account_id", "adjustment_date"],
    )
    op.create_table(
        "partner_opening_balance_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entry_number", sa.String(40), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("nature", sa.String(12), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("reversal_of_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "amount > 0", name=op.f("ck_partner_opening_balance_entries_amount_positive")
        ),
        sa.CheckConstraint(
            "nature IN ('debit','credit')",
            name=op.f("ck_partner_opening_balance_entries_nature_valid"),
        ),
        sa.CheckConstraint(
            "source IN ('manual','reversal')",
            name=op.f("ck_partner_opening_balance_entries_source_valid"),
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reversal_of_id"], ["partner_opening_balance_entries.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_number"),
        sa.UniqueConstraint("reversal_of_id"),
    )
    op.create_index(
        "ix_partner_opening_entries_partner_date",
        "partner_opening_balance_entries",
        ["partner_id", "entry_date"],
    )
    op.create_table(
        "customer_account_adjustments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("adjustment_number", sa.String(40), nullable=False),
        sa.Column(
            "adjustment_date",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("adjustment_type", sa.String(12), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("reversed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "adjustment_type IN ('debit','credit')",
            name=op.f("ck_customer_account_adjustments_type_valid"),
        ),
        sa.CheckConstraint(
            "amount > 0", name=op.f("ck_customer_account_adjustments_amount_positive")
        ),
        sa.CheckConstraint(
            "status IN ('posted','reversed')",
            name=op.f("ck_customer_account_adjustments_status_valid"),
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reversed_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("adjustment_number"),
    )
    op.create_index(
        "ix_customer_adjustments_customer_date",
        "customer_account_adjustments",
        ["customer_id", "adjustment_date"],
    )

    op.execute(
        sa.text(
            "INSERT INTO financial_accounts "
            "(id, code, normalized_code, name_ar, account_type, opening_balance, "
            "is_default, is_active, notes, version) "
            "VALUES (:id, 'CASH-MAIN', 'CASH-MAIN', 'الخزينة الرئيسية', 'cash', 0, "
            "true, true, 'الحساب المالي الافتراضي', 1)"
        ).bindparams(id=uuid4())
    )
    for document_type, prefix in (
        ("customer_receipt", "CR-"),
        ("supplier_payment", "SP-"),
        ("financial_transfer", "TR-"),
        ("financial_adjustment", "ADJ-FIN-"),
        ("opening_balance", "OB-"),
        ("opening_balance_reversal", "OBR-"),
        ("customer_adjustment", "CA-"),
    ):
        op.execute(
            sa.text(
                "INSERT INTO document_sequences "
                "(document_type, prefix, next_value, padding, version) "
                "SELECT :document_type, :prefix, 1, 6, 1 "
                "WHERE NOT EXISTS (SELECT 1 FROM document_sequences "
                "WHERE document_type = :document_type)"
            ).bindparams(document_type=document_type, prefix=prefix)
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM document_sequences WHERE document_type IN "
        "('customer_receipt','supplier_payment','financial_transfer',"
        "'financial_adjustment','opening_balance_reversal','customer_adjustment')"
    )
    for table in (
        "customer_account_adjustments",
        "partner_opening_balance_entries",
        "financial_account_adjustments",
        "financial_account_transfers",
        "payment_allocations",
        "payment_transactions",
        "financial_accounts",
    ):
        op.drop_table(table)
