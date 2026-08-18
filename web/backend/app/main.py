from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

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


@app.middleware("http")
async def security_headers(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    request.state.request_id = request.headers.get("x-request-id", str(uuid4()))[:80]
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = request.state.request_id
    return response


app.include_router(api_router, prefix="/api/v1")
