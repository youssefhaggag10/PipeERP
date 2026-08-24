from decimal import Decimal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import case, func, select

from app.api.dependencies import CurrentPrincipal, DatabaseSession
from app.modules.inventory.models import InventoryBalance, InventoryLayer
from app.modules.master_data.models import Product

router = APIRouter(prefix="/dashboard")


class DashboardSummary(BaseModel):
    total_products: int
    products_with_stock: int
    raw_material_balance: Decimal
    finished_good_balance: Decimal
    waste_balance: Decimal
    inventory_value: Decimal
    low_stock_products: int


@router.get("/summary", response_model=DashboardSummary)
def summary(request: Request, principal: CurrentPrincipal, db: DatabaseSession) -> DashboardSummary:
    del request, principal
    total_products = int(
        db.scalar(select(func.count(Product.id)).where(Product.is_active.is_(True))) or 0
    )
    balance_rows = list(
        db.execute(
            select(
                InventoryBalance.product_id,
                func.coalesce(func.sum(InventoryBalance.quantity_on_hand), 0),
            ).group_by(InventoryBalance.product_id)
        )
    )
    quantities = {product_id: Decimal(value or 0) for product_id, value in balance_rows}
    products_with_stock = sum(value > 0 for value in quantities.values())

    def quantity_by_type(product_type: str) -> Decimal:
        return Decimal(
            db.scalar(
                select(func.coalesce(func.sum(InventoryBalance.quantity_on_hand), 0))
                .join(Product, Product.id == InventoryBalance.product_id)
                .where(Product.product_type == product_type, Product.is_active.is_(True))
            )
            or 0
        )

    inventory_value = Decimal(
        db.scalar(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                InventoryLayer.cost_basis == "weight",
                                InventoryLayer.weight_remaining_kg * InventoryLayer.unit_cost,
                            ),
                            else_=InventoryLayer.quantity_remaining * InventoryLayer.unit_cost,
                        )
                    ),
                    0,
                )
            )
        )
        or 0
    )
    low_stock_products = sum(
        quantities.get(product_id, Decimal("0")) < Decimal(minimum)
        for product_id, minimum in db.execute(
            select(Product.id, Product.min_stock).where(
                Product.is_active.is_(True), Product.min_stock > 0
            )
        )
    )
    return DashboardSummary(
        total_products=total_products,
        products_with_stock=products_with_stock,
        raw_material_balance=quantity_by_type("raw_material"),
        finished_good_balance=quantity_by_type("finished_good"),
        waste_balance=quantity_by_type("waste"),
        inventory_value=inventory_value,
        low_stock_products=low_stock_products,
    )
