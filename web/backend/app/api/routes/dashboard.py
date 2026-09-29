from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentPrincipal, DatabaseSession
from app.modules.identity.permissions import PermissionCode
from app.modules.inventory.models import InventoryBalance
from app.modules.manufacturing.models import ManufacturingOrder
from app.modules.master_data.models import Product
from app.modules.purchasing.models import PurchaseOrder
from app.modules.sales.models import SalesOrder, SalesOrderLine

router = APIRouter(prefix="/dashboard")


class DashboardActivity(BaseModel):
    document_number: str
    module: Literal["sales", "purchases", "manufacturing"]
    status: str
    occurred_at: datetime
    route: str


class DashboardSummary(BaseModel):
    sales_today: Decimal | None
    open_manufacturing_orders: int | None
    low_stock_products: int | None
    weight_sold_today_kg: Decimal | None
    activity: list[DashboardActivity]


def _sales_metrics(
    db: Session,
    *,
    day_start: datetime,
    can_piece_sales: bool,
    can_weight_sales: bool,
) -> tuple[Decimal | None, Decimal | None]:
    if not (can_piece_sales or can_weight_sales):
        return None, None
    allowed_billing_methods = [
        method
        for method, allowed in (("piece", can_piece_sales), ("weight", can_weight_sales))
        if allowed
    ]
    sales_today = Decimal(
        db.scalar(
            select(func.coalesce(func.sum(SalesOrder.total), 0)).where(
                SalesOrder.status == "delivered",
                SalesOrder.billing_method.in_(allowed_billing_methods),
                SalesOrder.order_date >= day_start,
            )
        )
        or 0
    )
    if not can_weight_sales:
        return sales_today, None
    weight_sold = Decimal(
        db.scalar(
            select(func.coalesce(func.sum(SalesOrderLine.billing_weight_kg), 0))
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .where(
                SalesOrder.status == "delivered",
                SalesOrder.billing_method == "weight",
                SalesOrder.order_date >= day_start,
            )
        )
        or 0
    )
    return sales_today, weight_sold


def _open_manufacturing_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count(ManufacturingOrder.id)).where(
                ManufacturingOrder.status.in_(("draft", "in_progress"))
            )
        )
        or 0
    )


def _low_stock_count(db: Session) -> int:
    quantities = {
        product_id: Decimal(total or 0)
        for product_id, total in db.execute(
            select(
                InventoryBalance.product_id,
                func.coalesce(func.sum(InventoryBalance.quantity_on_hand), 0),
            ).group_by(InventoryBalance.product_id)
        )
    }
    products = db.execute(
        select(Product.id, Product.min_stock).where(
            Product.is_active.is_(True), Product.min_stock > 0
        )
    )
    return sum(
        1
        for product_id, minimum in products
        if quantities.get(product_id, Decimal("0")) < minimum
    )


def _recent_activity(
    db: Session,
    *,
    can_sales: bool,
    can_purchases: bool,
    can_manufacturing: bool,
) -> list[DashboardActivity]:
    activity: list[DashboardActivity] = []
    if can_sales:
        activity.extend(
            DashboardActivity(
                document_number=row.order_number,
                module="sales",
                status=row.status,
                occurred_at=row.order_date,
                route="/weight-sales" if row.billing_method == "weight" else "/sales",
            )
            for row in db.scalars(
                select(SalesOrder).order_by(SalesOrder.order_date.desc()).limit(5)
            )
        )
    if can_purchases:
        activity.extend(
            DashboardActivity(
                document_number=row.order_number,
                module="purchases",
                status=row.status,
                occurred_at=row.order_date,
                route="/purchases",
            )
            for row in db.scalars(
                select(PurchaseOrder).order_by(PurchaseOrder.order_date.desc()).limit(5)
            )
        )
    if can_manufacturing:
        activity.extend(
            DashboardActivity(
                document_number=row.order_number,
                module="manufacturing",
                status=row.status,
                occurred_at=row.order_date,
                route="/manufacturing",
            )
            for row in db.scalars(
                select(ManufacturingOrder)
                .order_by(ManufacturingOrder.order_date.desc())
                .limit(5)
            )
        )
    activity.sort(key=lambda item: item.occurred_at, reverse=True)
    return activity[:8]


@router.get("/summary")
def summary(request: Request, principal: CurrentPrincipal, db: DatabaseSession) -> DashboardSummary:
    del request
    permissions = principal.permissions
    day_start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    can_piece_sales = PermissionCode.SALES_READ in permissions
    can_weight_sales = PermissionCode.WEIGHT_SALES_READ in permissions
    can_sales = can_piece_sales or can_weight_sales
    can_manufacturing = PermissionCode.MANUFACTURING_READ in permissions
    can_inventory = PermissionCode.INVENTORY_READ in permissions
    can_purchases = PermissionCode.PURCHASES_READ in permissions

    sales_today, weight_sold = _sales_metrics(
        db,
        day_start=day_start,
        can_piece_sales=can_piece_sales,
        can_weight_sales=can_weight_sales,
    )
    open_manufacturing = _open_manufacturing_count(db) if can_manufacturing else None
    low_stock = _low_stock_count(db) if can_inventory else None
    activity = _recent_activity(
        db,
        can_sales=can_sales,
        can_purchases=can_purchases,
        can_manufacturing=can_manufacturing,
    )
    return DashboardSummary(
        sales_today=sales_today,
        open_manufacturing_orders=open_manufacturing,
        low_stock_products=low_stock,
        weight_sold_today_kg=weight_sold,
        activity=activity,
    )
