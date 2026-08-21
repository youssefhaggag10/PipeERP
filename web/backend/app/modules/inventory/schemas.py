from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

CostBasis = Literal["quantity", "weight"]
AdjustmentDirection = Literal["increase", "decrease"]


class InventoryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ReceiptRequest(BaseModel):
    product_id: UUID
    warehouse_id: UUID
    quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=6)
    weight_kg: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=6)
    cost_basis: CostBasis
    unit_cost: Decimal = Field(ge=0, max_digits=20, decimal_places=6)
    lot_number: str = Field(default="", max_length=80)
    reference_type: str = Field(min_length=1, max_length=60)
    reference_id: str | None = Field(default=None, max_length=80)
    reference_line_id: str | None = Field(default=None, max_length=80)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_basis_amount(self) -> "ReceiptRequest":
        basis_amount = self.quantity if self.cost_basis == "quantity" else self.weight_kg
        if basis_amount <= 0:
            raise ValueError("يجب إدخال كمية موجبة لأساس التكلفة المختار")
        return self


class IssueRequest(BaseModel):
    product_id: UUID
    warehouse_id: UUID
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    cost_basis: CostBasis
    reference_type: str = Field(min_length=1, max_length=60)
    reference_id: str | None = Field(default=None, max_length=80)
    reference_line_id: str | None = Field(default=None, max_length=80)
    notes: str = Field(default="", max_length=2000)


class TransferRequest(BaseModel):
    product_id: UUID
    source_warehouse_id: UUID
    destination_warehouse_id: UUID
    amount: Decimal = Field(gt=0, max_digits=20, decimal_places=6)
    cost_basis: CostBasis
    reference_id: str | None = Field(default=None, max_length=80)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_warehouses(self) -> "TransferRequest":
        if self.source_warehouse_id == self.destination_warehouse_id:
            raise ValueError("يجب اختيار مخزنين مختلفين للتحويل")
        return self


class AdjustmentRequest(BaseModel):
    product_id: UUID
    warehouse_id: UUID
    direction: AdjustmentDirection
    quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=6)
    weight_kg: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=6)
    cost_basis: CostBasis
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=6)
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_basis_amount(self) -> "AdjustmentRequest":
        basis_amount = self.quantity if self.cost_basis == "quantity" else self.weight_kg
        if basis_amount <= 0:
            raise ValueError("يجب إدخال مقدار موجب للتسوية")
        return self


class ReversalRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class TransactionView(InventoryView):
    id: UUID
    idempotency_key: str
    transaction_type: str
    product_id: UUID
    warehouse_id: UUID
    lot_id: UUID | None
    lot_number: str
    quantity_delta: Decimal
    weight_delta_kg: Decimal
    unit_cost: Decimal
    total_cost: Decimal
    cost_basis: CostBasis
    reference_type: str
    reference_id: str | None
    reversal_of_id: UUID | None
    product_code: str
    product_name_ar: str
    warehouse_name_ar: str
    notes: str
    posted_at: datetime


class TransferView(BaseModel):
    reference_id: str
    outbound: TransactionView
    inbound: TransactionView


class BalanceView(InventoryView):
    product_id: UUID
    warehouse_id: UUID
    quantity_on_hand: Decimal
    weight_on_hand_kg: Decimal
    version: int
    product_code: str
    product_name_ar: str
    warehouse_name_ar: str


class LotBalanceView(InventoryView):
    lot_id: UUID
    product_id: UUID
    warehouse_id: UUID
    product_code: str
    product_name_ar: str
    warehouse_name_ar: str
    lot_number: str
    received_at: datetime
    quantity_received: Decimal
    quantity_issued: Decimal
    quantity_remaining: Decimal
    weight_received_kg: Decimal
    weight_issued_kg: Decimal
    weight_remaining_kg: Decimal
    average_cost: Decimal
    inventory_value: Decimal


class InventoryOption(InventoryView):
    id: UUID
    code: str
    name_ar: str


class InventoryOptionsView(BaseModel):
    products: list[InventoryOption]
    warehouses: list[InventoryOption]
