from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.inventory.schemas import CostBasis

PurchaseOrderStatus = Literal["draft", "approved", "partially_received", "received", "cancelled"]
PaymentMethod = Literal["cash", "bank_transfer", "cheque", "wallet"]


class PurchasingView(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CreatePurchaseOrderLineRequest(BaseModel):
    product_id: UUID
    cost_basis: CostBasis
    ordered_quantity: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=6)
    ordered_weight_kg: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=6)
    unit_price: Decimal = Field(ge=0, decimal_places=6)
    additional_unit_cost: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=6)

    @model_validator(mode="after")
    def validate_basis_amount(self) -> "CreatePurchaseOrderLineRequest":
        basis = self.ordered_quantity if self.cost_basis == "quantity" else self.ordered_weight_kg
        if basis <= 0:
            raise ValueError("يجب إدخال مقدار موجب لأساس تكلفة بند الشراء")
        return self


class CreatePurchaseOrderRequest(BaseModel):
    supplier_id: UUID
    warehouse_id: UUID
    notes: str = Field(default="", max_length=2000)
    advance_amount: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    advance_payment_method: PaymentMethod = "cash"
    advance_financial_account_id: UUID | None = None
    lines: list[CreatePurchaseOrderLineRequest] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_products(self) -> "CreatePurchaseOrderRequest":
        product_ids = [line.product_id for line in self.lines]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("لا يمكن تكرار المنتج داخل أمر الشراء نفسه")
        if self.advance_amount > 0 and self.advance_financial_account_id is None:
            raise ValueError("اختر حساب الخزينة أو البنك للدفعة المقدمة")
        return self


class ApprovePurchaseOrderRequest(BaseModel):
    version: int = Field(gt=0)


class PurchaseReceiptLineRequest(BaseModel):
    purchase_order_line_id: UUID
    gross_quantity: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=6)
    gross_weight_kg: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=6)
    loss_quantity: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=6)
    loss_weight_kg: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=6)
    lot_number: str = Field(default="", max_length=80)

    @model_validator(mode="after")
    def validate_loss(self) -> "PurchaseReceiptLineRequest":
        if self.loss_quantity > self.gross_quantity:
            raise ValueError("فاقد العدد لا يمكن أن يتجاوز المستلم")
        if self.loss_weight_kg > self.gross_weight_kg:
            raise ValueError("فاقد الوزن لا يمكن أن يتجاوز المستلم")
        return self


class PostPurchaseReceiptRequest(BaseModel):
    notes: str = Field(default="", max_length=2000)
    lines: list[PurchaseReceiptLineRequest] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_lines(self) -> "PostPurchaseReceiptRequest":
        line_ids = [line.purchase_order_line_id for line in self.lines]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("لا يمكن تكرار بند أمر الشراء في سند الاستلام")
        return self


class ReversePurchaseReceiptRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class CreateSupplierInvoiceRequest(BaseModel):
    supplier_invoice_number: str = Field(min_length=1, max_length=80)


class PurchaseOrderLineView(PurchasingView):
    id: UUID
    product_id: UUID
    product_code: str
    product_name_ar: str
    cost_basis: CostBasis
    ordered_quantity: Decimal
    ordered_weight_kg: Decimal
    received_quantity: Decimal
    received_weight_kg: Decimal
    unit_price: Decimal
    additional_unit_cost: Decimal
    line_total: Decimal
    version: int


class PurchaseOrderView(PurchasingView):
    id: UUID
    order_number: str
    supplier_id: UUID
    supplier_code: str
    supplier_name_ar: str
    warehouse_id: UUID
    warehouse_name_ar: str
    status: PurchaseOrderStatus
    order_date: datetime
    notes: str
    total: Decimal
    version: int
    lines: list[PurchaseOrderLineView]


class PurchaseReceiptLineView(PurchasingView):
    id: UUID
    purchase_order_line_id: UUID
    inventory_transaction_id: UUID
    product_code: str
    product_name_ar: str
    lot_number: str
    gross_quantity: Decimal
    gross_weight_kg: Decimal
    loss_quantity: Decimal
    loss_weight_kg: Decimal
    net_quantity: Decimal
    net_weight_kg: Decimal
    capitalized_cost: Decimal
    inventory_unit_cost: Decimal


class PurchaseReceiptView(PurchasingView):
    id: UUID
    receipt_number: str
    purchase_order_id: UUID
    status: Literal["posted", "reversed"]
    notes: str
    posted_at: datetime
    reversed_at: datetime | None
    reversal_reason: str
    lines: list[PurchaseReceiptLineView]


class SupplierInvoiceView(PurchasingView):
    id: UUID
    invoice_number: str
    supplier_invoice_number: str
    purchase_order_id: UUID
    supplier_id: UUID
    status: Literal["draft", "posted", "reversed"]
    total: Decimal
    posted_at: datetime | None
    version: int


class PurchaseOption(PurchasingView):
    id: UUID
    code: str
    name_ar: str
    account_type: str = ""


class PurchaseOptionsView(BaseModel):
    suppliers: list[PurchaseOption]
    warehouses: list[PurchaseOption]
    products: list[PurchaseOption]
    financial_accounts: list[PurchaseOption]
