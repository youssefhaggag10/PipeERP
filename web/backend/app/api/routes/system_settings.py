import os
from datetime import UTC, datetime
from pathlib import Path
from subprocess import DEVNULL, CalledProcessError, TimeoutExpired, run
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.api.dependencies import (
    CurrentPrincipal,
    DatabaseSession,
    client_context,
    enforce_csrf,
    enforce_permission,
)
from app.core.settings import get_settings
from app.modules.identity.permissions import PermissionCode
from app.modules.identity.security import verify_password
from app.modules.identity.service import add_audit

router = APIRouter(prefix="/system")

OPERATIONAL_TABLES = (
    "return_refunds",
    "payment_allocations",
    "payment_transactions",
    "invoice_return_lines",
    "invoice_returns",
    "customer_account_adjustments",
    "financial_account_adjustments",
    "financial_account_transfers",
    "manufacturing_mix_adjustment_materials",
    "manufacturing_mix_adjustments",
    "manufacturing_completion_outputs",
    "manufacturing_completions",
    "manufacturing_material_issues",
    "manufacturing_order_materials",
    "manufacturing_order_outputs",
    "manufacturing_orders",
    "inventory_allocations",
    "inventory_transactions",
    "inventory_layers",
    "inventory_balances",
    "inventory_lots",
    "customer_invoices",
    "supplier_invoices",
    "sales_delivery_lines",
    "sales_deliveries",
    "sales_weight_card_lines",
    "sales_weight_cards",
    "sales_order_lines",
    "sales_orders",
    "sales_quotation_lines",
    "sales_quotations",
    "purchase_receipt_lines",
    "purchase_receipts",
    "purchase_order_lines",
    "purchase_orders",
    "crm_activities",
    "crm_leads",
)


class ResetRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    confirmation: str


def _require_admin(principal: CurrentPrincipal) -> None:
    if "system_admin" not in principal.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "هذه العملية متاحة لمدير النظام فقط")


@router.get("/backup")
def create_backup(
    background_tasks: BackgroundTasks,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> FileResponse:
    enforce_permission(request, db, principal, PermissionCode.SETTINGS_MANAGE)
    _require_admin(principal)
    configured_url = make_url(get_settings().database_url)
    if not configured_url.drivername.startswith("postgresql"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "النسخ الاحتياطي اليدوي متاح عند تشغيل PostgreSQL فقط",
        )
    with NamedTemporaryFile(prefix="pipeerp-", suffix=".dump", delete=False) as temporary:
        path = Path(temporary.name)
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--no-password",
        f"--file={path}",
    ]
    if configured_url.host:
        command.append(f"--host={configured_url.host}")
    if configured_url.port:
        command.append(f"--port={configured_url.port}")
    if configured_url.username:
        command.append(f"--username={configured_url.username}")
    command.append(str(configured_url.database or "pipeerp"))
    environment = dict(os.environ)
    environment["PGCONNECT_TIMEOUT"] = "10"
    if configured_url.password:
        environment["PGPASSWORD"] = configured_url.password
    try:
        run(
            command,
            check=True,
            capture_output=True,
            stdin=DEVNULL,
            env=environment,
            timeout=300,
        )
    except (CalledProcessError, OSError, TimeoutExpired) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "تعذر إنشاء النسخة الاحتياطية",
        ) from exc
    add_audit(
        db,
        actor_user_id=principal.user.id,
        event_type="system.backup.create",
        entity_type="database_backup",
        outcome="success",
        client=client_context(request),
    )
    db.commit()
    background_tasks.add_task(path.unlink, missing_ok=True)
    filename = f"PipeERP-{datetime.now(UTC):%Y%m%d-%H%M%S}.dump"
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_operational_data(
    payload: ResetRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> None:
    enforce_permission(request, db, principal, PermissionCode.SETTINGS_MANAGE)
    enforce_csrf(request, db, principal)
    _require_admin(principal)
    if payload.confirmation.strip() != "تصفير النظام":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "عبارة التأكيد غير صحيحة")
    if not verify_password(payload.password, principal.user.password_hash):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "كلمة مرور الأدمن غير صحيحة")

    try:
        for table_name in OPERATIONAL_TABLES:
            db.execute(text(f'DELETE FROM "{table_name}"'))
        db.execute(text("UPDATE document_sequences SET next_value = 1, version = version + 1"))
        add_audit(
            db,
            actor_user_id=principal.user.id,
            event_type="system.operational_data.reset",
            entity_type="system",
            outcome="success",
            client=client_context(request),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
