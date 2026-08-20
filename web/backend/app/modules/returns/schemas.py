from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ReturnType = Literal["sales", "purchase"]
RefundType = Literal["customer_refund", "supplier_refund"]
PaymentMethod = Literal["cash", "bank_transfer", "cheque", "wallet"]


class ReturnView(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ReturnLineRequest(BaseModel):
    source_line_id: UUID
    quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=6)
    weight_kg: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=6)

    @model_validator(mode="after")
    def positive_amount(self) -> "ReturnLineRequest":
        if self.quantity <= 0 and self.weight_kg <= 0:
            raise ValueError("أدخل كمية أو وزنًا موجبًا للمرتجع")
        return self


class CreateInvoiceReturnRequest(BaseModel):
    return_type: ReturnType
    invoice_id: UUID
    reason: str = Field(min_length=1, max_length=1000)
    lines: list[ReturnLineRequest] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_lines(self) -> "CreateInvoiceReturnRequest":
        ids = [item.source_line_id for item in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("لا يمكن تكرار بند الفاتورة في المرتجع")
        return self


class ReverseRequest(BaseModel):
    version: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)


class CreateRefundRequest(BaseModel):
    refund_type: RefundType
    invoice_id: UUID
    financial_account_id: UUID
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=2)
    payment_method: PaymentMethod
    notes: str = Field(default="", max_length=1000)


class ReturnableLineView(ReturnView):
    source_line_id: UUID
    product_id: UUID
    product_code: str
    product_name_ar: str
    unit: str
    unit_price: Decimal
    cost_basis: Literal["quantity", "weight"]
    original_quantity: Decimal
    returned_quantity: Decimal
    remaining_quantity: Decimal
    original_weight_kg: Decimal
    returned_weight_kg: Decimal
    remaining_weight_kg: Decimal


class InvoiceReturnLineView(ReturnView):
    id: UUID
    source_line_id: UUID
    product_id: UUID
    product_code: str
    product_name_ar: str
    quantity: Decimal
    weight_kg: Decimal
    cost_basis: Literal["quantity", "weight"]
    unit: str
    unit_price: Decimal
    line_total: Decimal
    inventory_cost: Decimal


class InvoiceReturnView(ReturnView):
    id: UUID
    return_number: str
    return_type: ReturnType
    invoice_id: UUID
    invoice_number: str
    partner_id: UUID
    partner_name_ar: str
    warehouse_id: UUID
    warehouse_name_ar: str
    return_date: datetime
    total: Decimal
    reason: str
    status: Literal["posted", "reversed"]
    reversal_reason: str
    version: int
    lines: list[InvoiceReturnLineView]


class ReturnableInvoiceView(ReturnView):
    id: UUID
    invoice_number: str
    invoice_type: ReturnType
    invoice_date: datetime
    order_number: str
    partner_id: UUID
    partner_name_ar: str
    original_total: Decimal
    returned_total: Decimal
    net_total: Decimal
    paid: Decimal
    refunded: Decimal
    remaining: Decimal
    refundable: Decimal
    return_status: Literal["none", "partial", "full"]


class RefundView(ReturnView):
    id: UUID
    refund_number: str
    refund_type: RefundType
    invoice_id: UUID
    invoice_number: str
    partner_id: UUID
    partner_name_ar: str
    financial_account_id: UUID
    financial_account_name_ar: str
    refund_date: datetime
    amount: Decimal
    payment_method: PaymentMethod
    notes: str
    status: Literal["posted", "reversed"]
    reversal_reason: str
    version: int


class ReturnOptionsView(BaseModel):
    accounts: list[dict[str, str]]
