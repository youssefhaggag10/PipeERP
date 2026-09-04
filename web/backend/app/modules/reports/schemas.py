from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.modules.treasury.schemas import PartnerStatementView

ReportKey = Literal[
    "sales",
    "purchases",
    "customer_balances",
    "supplier_balances",
    "payments",
    "inventory_valuation",
]


class ReportView(BaseModel):
    report_key: ReportKey
    title: str
    date_from: date
    date_to: date
    columns: list[str]
    rows: list[dict[str, str]]
    summary: dict[str, str]


class ReportPartnerOption(BaseModel):
    id: UUID
    code: str
    name_ar: str
    is_customer: bool
    is_supplier: bool


class ReportOptionsView(BaseModel):
    partners: list[ReportPartnerOption]


class PrintCompanyView(BaseModel):
    name_ar: str
    phone: str
    address: str
    tax_number: str
    currency_code: str


class PrintDocumentLineView(BaseModel):
    code: str
    name: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    line_total: Decimal
    notes: str
    actual_weight_kg: Decimal | None = None
    price_per_kg: Decimal | None = None


class PrintDocumentView(BaseModel):
    document_type: Literal["sales_invoice", "weight_invoice", "quotation"]
    document_title: str
    document_number: str
    document_date: datetime
    order_number: str
    partner_name_ar: str
    partner_code: str
    partner_phone: str
    partner_address: str
    status: str
    payment_methods: list[str]
    subtotal: Decimal
    discount_amount: Decimal
    transport_amount: Decimal
    tax_amount: Decimal
    original_total: Decimal
    returned_total: Decimal
    net_total: Decimal
    paid: Decimal
    refunded: Decimal
    remaining: Decimal
    notes: str
    valid_until: datetime | None = None
    card_number: str = ""
    vehicle_number: str = ""
    gross_weight_kg: Decimal = Decimal("0")
    tare_weight_kg: Decimal = Decimal("0")
    net_weight_kg: Decimal = Decimal("0")
    lines: list[PrintDocumentLineView]
    company: PrintCompanyView


class CustomerStatementSummaryView(BaseModel):
    opening_balance: Decimal
    standard_sales_total: Decimal
    weight_sales_total: Decimal
    returns_total: Decimal
    receipts_total: Decimal
    customer_refunds_total: Decimal
    adjustments_total: Decimal
    net_movement: Decimal
    closing_balance: Decimal


class CustomerStatementPrintView(BaseModel):
    company: PrintCompanyView
    partner_phone: str
    statement: PartnerStatementView
    detailed: bool
    include_drafts: bool
    invoice_details: dict[str, list[PrintDocumentLineView]]
    summary: CustomerStatementSummaryView
