from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

CostBasis = Literal["quantity", "weight"]


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


class TransactionView(InventoryView):
    id: UUID
    idempotency_key: str
    transaction_type: str
    product_id: UUID
    warehouse_id: UUID
    lot_id: UUID | None
    quantity_delta: Decimal
    weight_delta_kg: Decimal
    unit_cost: Decimal
    total_cost: Decimal
    reference_type: str
    reference_id: str | None
    product_code: str
    product_name_ar: str
    warehouse_name_ar: str
    notes: str
    posted_at: datetime


class BalanceView(InventoryView):
    product_id: UUID
    warehouse_id: UUID
    quantity_on_hand: Decimal
    weight_on_hand_kg: Decimal
    version: int
    product_code: str
    product_name_ar: str
    warehouse_name_ar: str


class InventoryOption(InventoryView):
    id: UUID
    code: str
    name_ar: str


class InventoryOptionsView(BaseModel):
    products: list[InventoryOption]
    warehouses: list[InventoryOption]
