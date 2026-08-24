from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ManufacturingStatus = Literal["draft", "in_progress", "completed", "cancelled"]
ComponentKind = Literal["material", "scrap"]


class ManufacturingView(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RecipeComponentRequest(BaseModel):
    product_id: UUID
    quantity_per_batch: Decimal = Field(gt=0, max_digits=20, decimal_places=6)


class CreateRecipeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name_ar: str = Field(min_length=1, max_length=200)
    output_product_ids: list[UUID] = Field(min_length=1, max_length=100)
    components: list[RecipeComponentRequest] = Field(min_length=1, max_length=100)
    suggested_scrap_per_batch: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=20, decimal_places=6
    )
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_unique_products(self) -> "CreateRecipeRequest":
        if len(self.output_product_ids) != len(set(self.output_product_ids)):
            raise ValueError("لا يمكن تكرار المنتج النهائي داخل الخلطة")
        component_ids = [item.product_id for item in self.components]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("لا يمكن تكرار نفس الخامة داخل الخلطة")
        return self


class UpdateRecipeRequest(CreateRecipeRequest):
    version: int = Field(gt=0)


class RecipeOutputView(ManufacturingView):
    id: UUID
    product_id: UUID
    product_code: str
    product_name_ar: str
    standard_weight_kg: Decimal


class RecipeComponentView(ManufacturingView):
    id: UUID
    product_id: UUID
    product_code: str
    product_name_ar: str
    quantity_per_batch: Decimal
    display_order: int


class RecipeView(ManufacturingView):
    id: UUID
    code: str
    name_ar: str
    scrap_product_id: UUID
    scrap_product_code: str
    suggested_scrap_per_batch: Decimal
    notes: str
    is_active: bool
    version: int
    outputs: list[RecipeOutputView]
    components: list[RecipeComponentView]


class OrderOutputRequest(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=6)


class OrderScrapInputRequest(BaseModel):
    product_id: UUID
    quantity_per_batch: Decimal = Field(gt=0, max_digits=20, decimal_places=6)


class CreateManufacturingOrderRequest(BaseModel):
    recipe_id: UUID
    warehouse_id: UUID
    outputs: list[OrderOutputRequest] = Field(min_length=1, max_length=100)
    scrap_inputs: list[OrderScrapInputRequest] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_unique_lines(self) -> "CreateManufacturingOrderRequest":
        output_ids = [item.product_id for item in self.outputs]
        scrap_ids = [item.product_id for item in self.scrap_inputs]
        if len(output_ids) != len(set(output_ids)):
            raise ValueError("لا يمكن تكرار المنتج النهائي داخل أمر التصنيع")
        if len(scrap_ids) != len(set(scrap_ids)):
            raise ValueError("لا يمكن تكرار مصدر الكسر داخل أمر التصنيع")
        return self


class UpdateManufacturingOrderRequest(CreateManufacturingOrderRequest):
    version: int = Field(gt=0)


class TransitionRequest(BaseModel):
    version: int = Field(gt=0)


class ReplanView(BaseModel):
    changed: bool
    old_batches: int
    new_batches: int
    target_weight_kg: Decimal
    planned_scrap_kg: Decimal
    usable_scrap_kg: Decimal
    planned_input_weight_kg: Decimal
    expected_overage_kg: Decimal


class MaterialAvailabilityLineView(BaseModel):
    product_id: UUID
    product_code: str
    product_name_ar: str
    component_kind: ComponentKind
    required_quantity: Decimal
    available_quantity: Decimal
    issue_quantity: Decimal
    shortage_quantity: Decimal
    blocks_start: bool


class MaterialAvailabilityView(BaseModel):
    order_id: UUID
    order_number: str
    plan: ReplanView
    rows: list[MaterialAvailabilityLineView]
    has_blocking_shortage: bool


class CancelManufacturingOrderRequest(TransitionRequest):
    reason: str = Field(min_length=3, max_length=500)


class CompletionOutputRequest(BaseModel):
    product_id: UUID
    good_quantity: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=6)
    defective_quantity: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=6)
    actual_weight_kg: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=6)


class MixMaterialQuantityRequest(BaseModel):
    product_id: UUID
    actual_quantity: Decimal = Field(ge=0, decimal_places=6)


class MixAdjustmentRequest(BaseModel):
    excluded_product_id: UUID
    batch_count: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)
    actual_material_quantities: list[MixMaterialQuantityRequest] = Field(
        default_factory=list, max_length=100
    )

    @model_validator(mode="after")
    def validate_unique_materials(self) -> "MixAdjustmentRequest":
        product_ids = [item.product_id for item in self.actual_material_quantities]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("لا يمكن تكرار خامة داخل مجموعة التعديل")
        return self


class CompleteManufacturingOrderRequest(TransitionRequest):
    actual_batches: int = Field(gt=0)
    scrap_weight_kg: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=6)
    outputs: list[CompletionOutputRequest] = Field(min_length=1, max_length=100)
    adjustments: list[MixAdjustmentRequest] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_unique_outputs(self) -> "CompleteManufacturingOrderRequest":
        product_ids = [item.product_id for item in self.outputs]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("لا يمكن تكرار المنتج النهائي في الإكمال")
        return self


class OrderOutputView(ManufacturingView):
    id: UUID
    product_id: UUID
    product_code: str
    product_name_ar: str
    planned_quantity: Decimal
    standard_weight_kg: Decimal
    good_quantity: Decimal
    defective_quantity: Decimal
    actual_weight_kg: Decimal
    unit_cost: Decimal
    line_cost: Decimal


class MaterialIssueView(ManufacturingView):
    id: UUID
    inventory_transaction_id: UUID
    reversal_transaction_id: UUID | None
    issue_kind: Literal["initial", "additional"]
    batch_count: int
    quantity: Decimal
    weight_kg: Decimal
    total_cost: Decimal


class OrderMaterialView(ManufacturingView):
    id: UUID
    product_id: UUID
    product_code: str
    product_name_ar: str
    component_kind: ComponentKind
    quantity_per_batch: Decimal
    planned_quantity: Decimal
    issued_quantity: Decimal
    used_quantity: Decimal
    returned_quantity: Decimal
    issued_cost: Decimal
    used_cost: Decimal
    issues: list[MaterialIssueView]


class MixAdjustmentMaterialView(ManufacturingView):
    product_id: UUID
    product_code: str
    product_name_ar: str
    actual_quantity: Decimal


class MixAdjustmentView(ManufacturingView):
    id: UUID
    excluded_product_id: UUID
    excluded_product_code: str
    excluded_product_name_ar: str
    batch_count: int
    reason: str
    cost_amount: Decimal
    actual_material_quantities: list[MixAdjustmentMaterialView]


class CompletionView(ManufacturingView):
    id: UUID
    actual_batches: int
    full_batches: int
    modified_batches: int
    good_output_quantity: Decimal
    defective_output_quantity: Decimal
    actual_output_weight_kg: Decimal
    scrap_weight_kg: Decimal
    used_input_weight_kg: Decimal
    full_mix_cost: Decimal
    modified_mix_cost: Decimal
    total_material_cost: Decimal
    average_input_cost_per_kg: Decimal
    scrap_value: Decimal
    finished_cost: Decimal
    cost_per_good_kg: Decimal
    weight_variance_kg: Decimal
    notes: str
    adjustments: list[MixAdjustmentView]


class ManufacturingOrderView(ManufacturingView):
    id: UUID
    order_number: str
    recipe_id: UUID
    recipe_code: str
    recipe_name_ar: str
    warehouse_id: UUID
    warehouse_name_ar: str
    status: ManufacturingStatus
    order_date: datetime
    planned_batches: int
    issued_batches: int
    actual_batches: int
    target_weight_kg: Decimal
    planned_input_weight_kg: Decimal
    returned_scrap_quantity: Decimal
    material_cost: Decimal
    finished_cost: Decimal
    weight_variance_kg: Decimal
    notes: str
    cancellation_reason: str
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    version: int
    outputs: list[OrderOutputView]
    materials: list[OrderMaterialView]
    completion: CompletionView | None


class ManufacturingOption(ManufacturingView):
    id: UUID
    code: str
    name_ar: str
    product_type: str = ""
    standard_weight_kg: Decimal = Decimal("0")


class ManufacturingOptionsView(BaseModel):
    recipes: list[ManufacturingOption]
    warehouses: list[ManufacturingOption]
    output_products: list[ManufacturingOption]
    material_products: list[ManufacturingOption]
    scrap_products: list[ManufacturingOption]
