from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProductType = Literal[
    "raw_material",
    "finished_good",
    "waste",
    "service",
    "spare_part",
]


class MasterDataView(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UnitView(MasterDataView):
    id: UUID
    code: str
    name_ar: str
    symbol: str
    decimal_places: int
    is_active: bool
    version: int


class CreateUnitRequest(BaseModel):
    code: str = Field(min_length=1, max_length=24)
    name_ar: str = Field(min_length=2, max_length=120)
    symbol: str = Field(min_length=1, max_length=24)
    decimal_places: int = Field(default=3, ge=0, le=6)


class UpdateUnitRequest(CreateUnitRequest):
    version: int = Field(ge=1)
    is_active: bool = True


class CategoryView(MasterDataView):
    id: UUID
    code: str
    name_ar: str
    parent_id: UUID | None
    is_active: bool
    version: int


class CreateCategoryRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name_ar: str = Field(min_length=2, max_length=160)
    parent_id: UUID | None = None


class UpdateCategoryRequest(CreateCategoryRequest):
    version: int = Field(ge=1)
    is_active: bool = True


class ProductView(MasterDataView):
    id: UUID
    code: str
    name_ar: str
    product_type: ProductType
    unit_id: UUID
    category_id: UUID | None
    min_stock: Decimal
    track_lots: bool
    standard_weight_kg: Decimal
    weight_tolerance_percent: Decimal
    is_active: bool
    version: int


class CreateProductRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name_ar: str = Field(min_length=2, max_length=200)
    product_type: ProductType
    unit_id: UUID
    category_id: UUID | None = None
    min_stock: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=3)
    track_lots: bool = True
    standard_weight_kg: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=3)
    weight_tolerance_percent: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, max_digits=7, decimal_places=3
    )


class UpdateProductRequest(BaseModel):
    version: int = Field(ge=1)
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name_ar: str | None = Field(default=None, min_length=2, max_length=200)
    product_type: ProductType | None = None
    unit_id: UUID | None = None
    category_id: UUID | None = None
    clear_category: bool = False
    min_stock: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=3)
    track_lots: bool | None = None
    standard_weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=3)
    weight_tolerance_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=7, decimal_places=3
    )
    is_active: bool | None = None


class PartnerView(MasterDataView):
    id: UUID
    code: str
    name_ar: str
    phone: str
    address: str
    tax_number: str
    is_customer: bool
    is_supplier: bool
    is_active: bool
    version: int


class PartnerPayload(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name_ar: str = Field(min_length=2, max_length=200)
    phone: str = Field(default="", max_length=40)
    address: str = Field(default="", max_length=2000)
    tax_number: str = Field(default="", max_length=80)
    is_customer: bool = False
    is_supplier: bool = False

    @model_validator(mode="after")
    def partner_has_type(self) -> "PartnerPayload":
        if not self.is_customer and not self.is_supplier:
            raise ValueError("يجب اختيار عميل أو مورد على الأقل")
        return self


class CreatePartnerRequest(PartnerPayload):
    pass


class UpdatePartnerRequest(PartnerPayload):
    version: int = Field(ge=1)
    is_active: bool = True


class WarehouseView(MasterDataView):
    id: UUID
    code: str
    name_ar: str
    is_default: bool
    is_active: bool
    version: int


class CreateWarehouseRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name_ar: str = Field(min_length=2, max_length=160)
    is_default: bool = False


class UpdateWarehouseRequest(CreateWarehouseRequest):
    version: int = Field(ge=1)
    is_active: bool = True


class CompanySettingsView(MasterDataView):
    company_name_ar: str
    phone: str
    address: str
    tax_number: str
    currency_code: str
    currency_decimal_places: int
    tax_enabled: bool
    default_tax_rate: Decimal
    default_warehouse_id: UUID | None
    version: int


class UpdateCompanySettingsRequest(BaseModel):
    version: int = Field(ge=1)
    company_name_ar: str = Field(min_length=2, max_length=200)
    phone: str = Field(default="", max_length=1000)
    address: str = Field(default="", max_length=2000)
    tax_number: str = Field(default="", max_length=80)
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    currency_decimal_places: int = Field(ge=0, le=4)
    tax_enabled: bool
    default_tax_rate: Decimal = Field(ge=0, le=100, max_digits=7, decimal_places=3)
    default_warehouse_id: UUID | None = None
