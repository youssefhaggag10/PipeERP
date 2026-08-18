from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.settings import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Database migrations run as a deployment step, never implicitly on startup.
    yield


settings = get_settings()
app = FastAPI(
    title="PipeERP API",
    version="0.1.0",
    docs_url="/api/docs" if settings.expose_api_docs else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.expose_api_docs else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
)
app.include_router(api_router, prefix="/api/v1")
