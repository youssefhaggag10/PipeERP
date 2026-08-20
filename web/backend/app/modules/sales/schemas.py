from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

BillingMethod = Literal["piece", "weight"]
WeightMode = Literal["total_card", "per_line"]
PricingMode = Literal["uniform", "per_line"]
PaymentMethod = Literal["cash", "bank_transfer", "cheque", "wallet"]


class SalesView(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CreatePieceLineRequest(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    unit: str = Field(default="قطعة", min_length=1, max_length=40)
    unit_price: Decimal = Field(ge=0, max_digits=20, decimal_places=6)
    notes: str = Field(default="", max_length=500)


class CreatePieceOrderRequest(BaseModel):
    customer_id: UUID
    warehouse_id: UUID
    notes: str = Field(default="", max_length=2000)
    advance_amount: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    advance_payment_method: PaymentMethod = "cash"
    advance_financial_account_id: UUID | None = None
    lines: list[CreatePieceLineRequest] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_products(self) -> "CreatePieceOrderRequest":
        values = [line.product_id for line in self.lines]
        if len(values) != len(set(values)):
            raise ValueError("لا يمكن تكرار المنتج داخل أمر البيع")
        if self.advance_amount > 0 and self.advance_financial_account_id is None:
            raise ValueError("اختر حساب الخزينة أو البنك للدفعة المقدمة")
        return self


class WeightSaleLineRequest(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    unit: str = Field(default="ماسورة", min_length=1, max_length=40)
    actual_weight_kg: Decimal | None = Field(default=None, gt=0, decimal_places=6)
    price_per_kg: Decimal | None = Field(default=None, ge=0, decimal_places=6)
    notes: str = Field(default="", max_length=500)


class CreateWeightSaleRequest(BaseModel):
    customer_id: UUID
    warehouse_id: UUID
    weight_mode: WeightMode
    pricing_mode: PricingMode
    total_actual_weight_kg: Decimal | None = Field(default=None, gt=0, decimal_places=6)
    uniform_price_per_kg: Decimal | None = Field(default=None, ge=0, decimal_places=6)
    use_vehicle_scale: bool = False
    gross_weight_kg: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=6)
    tare_weight_kg: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=6)
    vehicle_number: str = Field(default="", max_length=80)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    transport_amount: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    notes: str = Field(default="", max_length=2000)
    advance_amount: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    advance_payment_method: PaymentMethod = "cash"
    advance_financial_account_id: UUID | None = None
    lines: list[WeightSaleLineRequest] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_modes(self) -> "CreateWeightSaleRequest":
        product_ids = [line.product_id for line in self.lines]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("لا يمكن تكرار المقاس داخل كارتة الوزن")
        if self.use_vehicle_scale:
            if self.gross_weight_kg <= 0 or self.gross_weight_kg <= self.tare_weight_kg:
                raise ValueError("الوزن القائم يجب أن يكون أكبر من وزن السيارة الفارغ")
        elif self.weight_mode == "total_card" and self.total_actual_weight_kg is None:
            raise ValueError("أدخل الوزن الفعلي الإجمالي للكارتة")
        if self.weight_mode == "per_line" and any(
            line.actual_weight_kg is None for line in self.lines
        ):
            raise ValueError("أدخل الوزن الفعلي لكل بند")
        if self.pricing_mode == "uniform" and self.uniform_price_per_kg is None:
            raise ValueError("أدخل سعر الكيلو الموحد")
        if self.pricing_mode == "per_line" and any(
            line.price_per_kg is None for line in self.lines
        ):
            raise ValueError("أدخل سعر الكيلو لكل بند")
        if self.advance_amount > 0 and self.advance_financial_account_id is None:
            raise ValueError("اختر حساب الخزينة أو البنك للدفعة المقدمة")
        return self


class DeliverOrderRequest(BaseModel):
    version: int = Field(gt=0)


class CancelOrderRequest(BaseModel):
    version: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)


class ReverseDeliveryRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class SalesOrderLineView(SalesView):
    id: UUID
    product_id: UUID
    product_code: str
    product_name_ar: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    line_total: Decimal
    standard_weight_kg: Decimal
    billing_weight_kg: Decimal
    price_per_kg: Decimal
    notes: str


class WeightCardLineView(SalesView):
    id: UUID
    sales_order_line_id: UUID
    product_id: UUID
    product_code: str
    product_name_ar: str
    quantity_pieces: Decimal
    standard_weight_kg: Decimal
    theoretical_weight_kg: Decimal
    actual_weight_kg: Decimal
    price_per_kg: Decimal
    line_total: Decimal
    notes: str


class WeightCardView(SalesView):
    id: UUID
    card_number: str
    card_date: datetime
    vehicle_number: str
    gross_weight_kg: Decimal
    tare_weight_kg: Decimal
    net_weight_kg: Decimal
    weight_mode: WeightMode
    pricing_mode: PricingMode
    uniform_price_per_kg: Decimal
    subtotal: Decimal
    use_vehicle_scale: bool
    status: Literal["draft", "posted", "cancelled"]
    notes: str
    lines: list[WeightCardLineView]


class CustomerInvoiceView(SalesView):
    id: UUID
    invoice_number: str
    sales_order_id: UUID
    customer_id: UUID
    invoice_type: Literal["standard", "weight"]
    status: Literal["posted", "reversed"]
    invoice_date: datetime
    subtotal: Decimal
    discount_amount: Decimal
    transport_amount: Decimal
    tax_amount: Decimal
    total: Decimal
    notes: str
    posted_at: datetime
    reversed_at: datetime | None
    reversal_reason: str
    version: int


class SalesDeliveryLineView(SalesView):
    id: UUID
    sales_order_line_id: UUID
    inventory_transaction_id: UUID
    product_code: str
    product_name_ar: str
    quantity: Decimal
    weight_kg: Decimal
    cost_amount: Decimal


class SalesDeliveryView(SalesView):
    id: UUID
    delivery_number: str
    sales_order_id: UUID
    status: Literal["posted", "reversed"]
    posted_at: datetime
    reversed_at: datetime | None
    reversal_reason: str
    lines: list[SalesDeliveryLineView]


class SalesOrderView(SalesView):
    id: UUID
    order_number: str
    customer_id: UUID
    customer_code: str
    customer_name_ar: str
    warehouse_id: UUID
    warehouse_name_ar: str
    billing_method: BillingMethod
    status: Literal["draft", "delivered", "reversed", "cancelled"]
    order_date: datetime
    notes: str
    subtotal: Decimal
    discount_amount: Decimal
    transport_amount: Decimal
    tax_amount: Decimal
    total: Decimal
    version: int
    lines: list[SalesOrderLineView]
    weight_cards: list[WeightCardView]
    invoice: CustomerInvoiceView | None
    delivery: SalesDeliveryView | None


class QuotationLineRequest(BaseModel):
    product_id: UUID | None = None
    item_name: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    unit: str = Field(min_length=1, max_length=40)
    unit_price: Decimal = Field(ge=0, max_digits=20, decimal_places=6)
    notes: str = Field(default="", max_length=500)


class CreateQuotationRequest(BaseModel):
    customer_id: UUID
    valid_until: datetime | None = None
    notes: str = Field(default="", max_length=2000)
    lines: list[QuotationLineRequest] = Field(min_length=1, max_length=100)


class QuotationLineView(SalesView):
    id: UUID
    product_id: UUID | None
    item_name: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    line_total: Decimal
    notes: str


class QuotationView(SalesView):
    id: UUID
    quotation_number: str
    customer_id: UUID
    customer_code: str
    customer_name_ar: str
    quotation_date: datetime
    valid_until: datetime | None
    status: Literal["draft", "sent", "accepted", "rejected", "cancelled"]
    total: Decimal
    notes: str
    version: int
    lines: list[QuotationLineView]


class SalesOption(SalesView):
    id: UUID
    code: str
    name_ar: str
    standard_weight_kg: Decimal = Decimal("0")
    unit_symbol: str = ""
    account_type: str = ""


class SalesOptionsView(BaseModel):
    customers: list[SalesOption]
    warehouses: list[SalesOption]
    products: list[SalesOption]
    financial_accounts: list[SalesOption]
