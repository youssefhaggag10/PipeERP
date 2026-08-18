from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.identity import router as identity_router
from app.api.routes.master_data import router as master_data_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["system"])
api_router.include_router(auth_router, tags=["identity"])
api_router.include_router(identity_router, tags=["identity"])
api_router.include_router(master_data_router, tags=["master data"])
