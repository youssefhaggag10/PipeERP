from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin


class FinancialAccount(TimestampMixin, Base):
    __tablename__ = "financial_accounts"
    __table_args__ = (
        UniqueConstraint("normalized_code"),
        CheckConstraint(
            "account_type IN ('cash','bank','wallet','other')", name="account_type_valid"
        ),
        CheckConstraint("version > 0", name="version_positive"),
        Index(
            "uq_financial_accounts_single_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default"),
            sqlite_where=text("is_default = 1"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PaymentTransaction(TimestampMixin, Base):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("transaction_number"),
        UniqueConstraint("idempotency_key"),
        UniqueConstraint("reversal_idempotency_key"),
        CheckConstraint(
            "transaction_type IN ('customer_receipt','supplier_payment')",
            name="transaction_type_valid",
        ),
        CheckConstraint(
            "payment_method IN ('cash','bank_transfer','cheque','wallet')",
            name="payment_method_valid",
        ),
        CheckConstraint(
            "reference_type IN ('sale','purchase') OR reference_type IS NULL",
            name="reference_type_valid",
        ),
        CheckConstraint("status IN ('posted','reversed')", name="status_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "(transaction_type = 'customer_receipt' AND supplier_invoice_id IS NULL) OR "
            "(transaction_type = 'supplier_payment' AND customer_invoice_id IS NULL)",
            name="invoice_type_matches_transaction",
        ),
        Index("ix_payment_transactions_partner_date", "partner_id", "transaction_date"),
        Index("ix_payment_transactions_account_date", "financial_account_id", "transaction_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    transaction_number: Mapped[str] = mapped_column(String(40), nullable=False)
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    transaction_type: Mapped[str] = mapped_column(String(24), nullable=False)
    partner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    financial_account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(24), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(16))
    reference_id: Mapped[UUID | None] = mapped_column(Uuid)
    customer_invoice_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("customer_invoices.id", ondelete="RESTRICT")
    )
    supplier_invoice_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("supplier_invoices.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="posted")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    posted_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reversal_idempotency_key: Mapped[str | None] = mapped_column(String(120))
    reversed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")


class PaymentAllocation(TimestampMixin, Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (
        UniqueConstraint(
            "payment_transaction_id",
            "customer_invoice_id",
            name="uq_payment_allocations_payment_customer_invoice",
        ),
        UniqueConstraint(
            "payment_transaction_id",
            "supplier_invoice_id",
            name="uq_payment_allocations_payment_supplier_invoice",
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "(customer_invoice_id IS NOT NULL AND supplier_invoice_id IS NULL) OR "
            "(customer_invoice_id IS NULL AND supplier_invoice_id IS NOT NULL)",
            name="exactly_one_invoice",
        ),
        Index("ix_payment_allocations_customer_invoice", "customer_invoice_id", "id"),
        Index("ix_payment_allocations_supplier_invoice", "supplier_invoice_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    payment_transaction_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("payment_transactions.id", ondelete="CASCADE"), nullable=False
    )
    customer_invoice_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("customer_invoices.id", ondelete="RESTRICT")
    )
    supplier_invoice_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("supplier_invoices.id", ondelete="RESTRICT")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)


class FinancialTransfer(TimestampMixin, Base):
    __tablename__ = "financial_account_transfers"
    __table_args__ = (
        UniqueConstraint("transfer_number"),
        UniqueConstraint("idempotency_key"),
        UniqueConstraint("reversal_idempotency_key"),
        CheckConstraint("from_account_id <> to_account_id", name="different_accounts"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("status IN ('posted','reversed')", name="status_valid"),
        Index("ix_financial_transfers_from_date", "from_account_id", "transfer_date"),
        Index("ix_financial_transfers_to_date", "to_account_id", "transfer_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    transfer_number: Mapped[str] = mapped_column(String(40), nullable=False)
    transfer_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    from_account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    to_account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="posted")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    posted_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reversal_idempotency_key: Mapped[str | None] = mapped_column(String(120))
    reversed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")


class FinancialAdjustment(TimestampMixin, Base):
    __tablename__ = "financial_account_adjustments"
    __table_args__ = (
        UniqueConstraint("adjustment_number"),
        UniqueConstraint("idempotency_key"),
        UniqueConstraint("reversal_idempotency_key"),
        CheckConstraint("amount <> 0", name="amount_nonzero"),
        CheckConstraint("status IN ('posted','reversed')", name="status_valid"),
        Index("ix_financial_adjustments_account_date", "financial_account_id", "adjustment_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    adjustment_number: Mapped[str] = mapped_column(String(40), nullable=False)
    adjustment_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    financial_account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("financial_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    target_balance: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="posted")
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    posted_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reversal_idempotency_key: Mapped[str | None] = mapped_column(String(120))
    reversed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")


class PartnerOpeningBalance(TimestampMixin, Base):
    __tablename__ = "partner_opening_balance_entries"
    __table_args__ = (
        UniqueConstraint("entry_number"),
        UniqueConstraint("reversal_of_id"),
        CheckConstraint("nature IN ('debit','credit')", name="nature_valid"),
        CheckConstraint("source IN ('manual','reversal')", name="source_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_partner_opening_entries_partner_date", "partner_id", "entry_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    entry_number: Mapped[str] = mapped_column(String(40), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    partner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    nature: Mapped[str] = mapped_column(String(12), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(12), nullable=False, default="manual")
    reversal_of_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("partner_opening_balance_entries.id", ondelete="RESTRICT")
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class CustomerAccountAdjustment(TimestampMixin, Base):
    __tablename__ = "customer_account_adjustments"
    __table_args__ = (
        UniqueConstraint("adjustment_number"),
        CheckConstraint("adjustment_type IN ('debit','credit')", name="type_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("status IN ('posted','reversed')", name="status_valid"),
        Index("ix_customer_adjustments_customer_date", "customer_id", "adjustment_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    adjustment_number: Mapped[str] = mapped_column(String(40), nullable=False)
    adjustment_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    customer_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    adjustment_type: Mapped[str] = mapped_column(String(12), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="posted")
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reversed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
