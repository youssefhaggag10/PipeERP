from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DatabaseSession

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["pipeerp-api"]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="pipeerp-api")


@router.get("/health/ready", response_model=HealthResponse)
def readiness(db: DatabaseSession) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "قاعدة البيانات غير جاهزة",
        ) from exc
    return HealthResponse(status="ok", service="pipeerp-api")
