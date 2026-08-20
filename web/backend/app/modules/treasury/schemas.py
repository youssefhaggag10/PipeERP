from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

AccountType = Literal["cash", "bank", "wallet", "other"]
PaymentMethod = Literal["cash", "bank_transfer", "cheque", "wallet"]
TransactionType = Literal["customer_receipt", "supplier_payment"]


class TreasuryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FinancialAccountRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name_ar: str = Field(min_length=1, max_length=200)
    account_type: AccountType
    opening_balance: Decimal = Field(default=Decimal("0"), max_digits=20, decimal_places=2)
    is_default: bool = False
    notes: str = Field(default="", max_length=2000)


class UpdateFinancialAccountRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name_ar: str = Field(min_length=1, max_length=200)
    account_type: AccountType
    is_default: bool = False
    is_active: bool = True
    notes: str = Field(default="", max_length=2000)
    version: int = Field(gt=0)


class FinancialAccountView(TreasuryView):
    id: UUID
    code: str
    name_ar: str
    account_type: AccountType
    opening_balance: Decimal
    current_balance: Decimal
    is_default: bool
    is_active: bool
    notes: str
    version: int


class InvoiceAllocationRequest(BaseModel):
    invoice_id: UUID
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=2)


class PostPaymentRequest(BaseModel):
    transaction_type: TransactionType
    partner_id: UUID
    financial_account_id: UUID
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=2)
    payment_method: PaymentMethod
    reference_type: Literal["sale", "purchase"] | None = None
    reference_id: UUID | None = None
    allocations: list[InvoiceAllocationRequest] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def unique_invoices(self) -> "PostPaymentRequest":
        invoice_ids = [allocation.invoice_id for allocation in self.allocations]
        if len(invoice_ids) != len(set(invoice_ids)):
            raise ValueError("لا يمكن تكرار الفاتورة داخل توزيع الدفعة")
        if sum((allocation.amount for allocation in self.allocations), Decimal("0")) > self.amount:
            raise ValueError("إجمالي التوزيع أكبر من مبلغ الحركة")
        if (self.reference_type is None) != (self.reference_id is None):
            raise ValueError("يجب تحديد نوع المستند ورقمه معًا")
        if self.allocations and self.reference_id is not None:
            raise ValueError("اختر إما أمرًا مرتبطًا أو توزيعًا على الفواتير")
        if self.reference_type == "sale" and self.transaction_type != "customer_receipt":
            raise ValueError("أمر البيع لا يقبل إلا تحصيل عميل")
        if self.reference_type == "purchase" and self.transaction_type != "supplier_payment":
            raise ValueError("أمر الشراء لا يقبل إلا سداد مورد")
        return self


class PaymentAllocationView(TreasuryView):
    invoice_id: UUID
    invoice_number: str
    amount: Decimal


class PaymentView(TreasuryView):
    id: UUID
    transaction_number: str
    transaction_date: datetime
    transaction_type: TransactionType
    partner_id: UUID
    partner_name_ar: str
    financial_account_id: UUID
    financial_account_name_ar: str
    amount: Decimal
    payment_method: PaymentMethod
    reference_type: Literal["sale", "purchase"] | None
    reference_id: UUID | None
    allocated_amount: Decimal
    unallocated_amount: Decimal
    status: Literal["posted", "reversed"]
    notes: str
    reversal_reason: str
    allocations: list[PaymentAllocationView]


class ReverseRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class TransferRequest(BaseModel):
    from_account_id: UUID
    to_account_id: UUID
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=2)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def different_accounts(self) -> "TransferRequest":
        if self.from_account_id == self.to_account_id:
            raise ValueError("لا يمكن التحويل إلى الحساب نفسه")
        return self


class TransferView(TreasuryView):
    id: UUID
    transfer_number: str
    transfer_date: datetime
    from_account_id: UUID
    from_account_name_ar: str
    to_account_id: UUID
    to_account_name_ar: str
    amount: Decimal
    status: Literal["posted", "reversed"]
    notes: str
    reversal_reason: str


class FinancialAdjustmentRequest(BaseModel):
    financial_account_id: UUID
    target_balance: Decimal = Field(max_digits=20, decimal_places=2)
    notes: str = Field(min_length=3, max_length=2000)


class FinancialAdjustmentView(TreasuryView):
    id: UUID
    adjustment_number: str
    adjustment_date: datetime
    financial_account_id: UUID
    financial_account_name_ar: str
    amount: Decimal
    target_balance: Decimal
    status: Literal["posted", "reversed"]
    notes: str
    reversal_reason: str


class OpeningBalanceRequest(BaseModel):
    partner_id: UUID
    nature: Literal["debit", "credit"]
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=2)
    entry_date: date
    notes: str = Field(default="", max_length=2000)


class OpeningBalanceView(TreasuryView):
    id: UUID
    entry_number: str
    entry_date: date
    partner_id: UUID
    partner_name_ar: str
    nature: Literal["debit", "credit"]
    amount: Decimal
    source: Literal["manual", "reversal"]
    reversal_of_id: UUID | None
    status: Literal["posted", "reversed", "reversal"]
    notes: str


class CustomerAdjustmentRequest(BaseModel):
    customer_id: UUID
    adjustment_type: Literal["debit", "credit"]
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=2)
    notes: str = Field(min_length=3, max_length=2000)


class CustomerAdjustmentView(TreasuryView):
    id: UUID
    adjustment_number: str
    adjustment_date: datetime
    customer_id: UUID
    customer_name_ar: str
    adjustment_type: Literal["debit", "credit"]
    amount: Decimal
    status: Literal["posted", "reversed"]
    notes: str
    reversal_reason: str


class PartnerBalanceView(TreasuryView):
    partner_id: UUID
    partner_code: str
    partner_name_ar: str
    partner_type: Literal["customer", "supplier"]
    opening_balance: Decimal
    invoices_total: Decimal
    paid_total: Decimal
    advances: Decimal
    adjustments_total: Decimal
    balance: Decimal


class OpenInvoiceView(TreasuryView):
    id: UUID
    invoice_number: str
    invoice_date: datetime
    partner_id: UUID
    partner_name_ar: str
    invoice_kind: Literal["sales", "purchase"]
    invoice_total: Decimal
    paid: Decimal
    remaining: Decimal


class OpenOrderView(TreasuryView):
    id: UUID
    order_number: str
    order_date: datetime
    partner_id: UUID
    partner_name_ar: str
    reference_type: Literal["sale", "purchase"]
    status: str
    total: Decimal
    paid: Decimal
    remaining: Decimal


class TreasurySummaryView(TreasuryView):
    financial_balance: Decimal
    receivables: Decimal
    payables: Decimal
    customer_receipts: Decimal
    supplier_payments: Decimal
    customer_advances: Decimal
    supplier_advances: Decimal


class StatementLineView(TreasuryView):
    movement_date: datetime
    document_number: str
    movement_type: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal
    notes: str


class PartnerStatementView(TreasuryView):
    partner_id: UUID
    partner_code: str
    partner_name_ar: str
    partner_type: Literal["customer", "supplier"]
    date_from: date
    date_to: date
    opening_balance: Decimal
    closing_balance: Decimal
    lines: list[StatementLineView]


class TreasuryPartnerOption(TreasuryView):
    id: UUID
    code: str
    name_ar: str
    is_customer: bool
    is_supplier: bool


class TreasuryOptionsView(TreasuryView):
    accounts: list[FinancialAccountView]
    partners: list[TreasuryPartnerOption]
