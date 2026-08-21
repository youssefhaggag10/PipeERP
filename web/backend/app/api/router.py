from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.crm import router as crm_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import router as health_router
from app.api.routes.identity import router as identity_router
from app.api.routes.inventory import router as inventory_router
from app.api.routes.manufacturing import router as manufacturing_router
from app.api.routes.master_data import router as master_data_router
from app.api.routes.purchasing import router as purchasing_router
from app.api.routes.reports import router as reports_router
from app.api.routes.returns import router as returns_router
from app.api.routes.sales import router as sales_router
from app.api.routes.treasury import router as treasury_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["system"])
api_router.include_router(auth_router, tags=["identity"])
api_router.include_router(crm_router, tags=["crm"])
api_router.include_router(dashboard_router, tags=["dashboard"])
api_router.include_router(identity_router, tags=["identity"])
api_router.include_router(master_data_router, tags=["master data"])
api_router.include_router(inventory_router, tags=["inventory"])
api_router.include_router(manufacturing_router, tags=["manufacturing"])
api_router.include_router(purchasing_router, tags=["purchasing"])
api_router.include_router(returns_router, tags=["returns"])
api_router.include_router(sales_router, tags=["sales"])
api_router.include_router(treasury_router, tags=["accounts"])
api_router.include_router(reports_router, tags=["reports"])
