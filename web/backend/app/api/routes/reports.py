from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import CurrentPrincipal, DatabaseSession, enforce_permission
from app.modules.identity.permissions import PermissionCode
from app.modules.reports.schemas import (
    CustomerStatementPrintView,
    PrintDocumentView,
    ReportOptionsView,
    ReportView,
)
from app.modules.reports.service import (
    PrintDocumentNotFound,
    ReportError,
    customer_statement_print_data,
    customer_statement_xlsx,
    generate_report,
    quotation_print_data,
    report_options,
    report_xlsx,
    sales_invoice_print_data,
)
from app.modules.treasury.service import TreasuryConflict, TreasuryNotFound

router = APIRouter(prefix="/reports")


def _read(request: Request, db: DatabaseSession, principal: CurrentPrincipal) -> None:
    enforce_permission(request, db, principal, PermissionCode.REPORTS_READ)


@router.get("/options", response_model=ReportOptionsView)
def options(
    request: Request, principal: CurrentPrincipal, db: DatabaseSession
) -> ReportOptionsView:
    _read(request, db, principal)
    return report_options(db)


@router.get("/generate", response_model=ReportView)
def generate(
    report_key: Annotated[
        str,
        Query(
            pattern="^(sales|purchases|customer_balances|supplier_balances|payments|inventory_valuation)$"
        ),
    ],
    date_from: date,
    date_to: date,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    partner_id: UUID | None = None,
) -> ReportView:
    _read(request, db, principal)
    try:
        return generate_report(
            db, report_key=report_key, date_from=date_from, date_to=date_to, partner_id=partner_id
        )
    except ReportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("/export.xlsx")
def export_xlsx(
    report_key: Annotated[
        str,
        Query(
            pattern="^(sales|purchases|customer_balances|supplier_balances|payments|inventory_valuation)$"
        ),
    ],
    date_from: date,
    date_to: date,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    partner_id: UUID | None = None,
) -> StreamingResponse:
    _read(request, db, principal)
    try:
        view = generate_report(
            db, report_key=report_key, date_from=date_from, date_to=date_to, partner_id=partner_id
        )
    except ReportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    filename = f"{report_key}-{date_from.isoformat()}-{date_to.isoformat()}.xlsx"
    return StreamingResponse(
        report_xlsx(view),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/print/sales-invoices/{invoice_id}", response_model=PrintDocumentView)
def print_sales_invoice(
    invoice_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> PrintDocumentView:
    _read(request, db, principal)
    try:
        view = sales_invoice_print_data(db, invoice_id)
        permission = (
            PermissionCode.WEIGHT_SALES_READ
            if view.document_type == "weight_invoice"
            else PermissionCode.SALES_READ
        )
        enforce_permission(request, db, principal, permission)
        return view
    except PrintDocumentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ReportError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/print/quotations/{quotation_id}", response_model=PrintDocumentView)
def print_quotation(
    quotation_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> PrintDocumentView:
    _read(request, db, principal)
    enforce_permission(request, db, principal, PermissionCode.SALES_READ)
    try:
        return quotation_print_data(db, quotation_id)
    except PrintDocumentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/print/customer-statements/{customer_id}", response_model=CustomerStatementPrintView)
def print_customer_statement(
    customer_id: UUID,
    date_from: date,
    date_to: date,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    detailed: bool = False,
    include_drafts: bool = False,
) -> CustomerStatementPrintView:
    _read(request, db, principal)
    enforce_permission(request, db, principal, PermissionCode.ACCOUNTS_READ)
    try:
        return customer_statement_print_data(
            db,
            customer_id=customer_id,
            date_from=date_from,
            date_to=date_to,
            detailed=detailed,
            include_drafts=include_drafts,
        )
    except TreasuryNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except (ReportError, TreasuryConflict, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("/export/customer-statements/{customer_id}.xlsx")
def export_customer_statement(
    customer_id: UUID,
    date_from: date,
    date_to: date,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    detailed: bool = False,
    include_drafts: bool = False,
) -> StreamingResponse:
    _read(request, db, principal)
    enforce_permission(request, db, principal, PermissionCode.ACCOUNTS_READ)
    try:
        view = customer_statement_print_data(
            db,
            customer_id=customer_id,
            date_from=date_from,
            date_to=date_to,
            detailed=detailed,
            include_drafts=include_drafts,
        )
    except TreasuryNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except (ReportError, TreasuryConflict, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    filename = f"customer-statement-{customer_id}-{date_from}-{date_to}.xlsx"
    return StreamingResponse(
        customer_statement_xlsx(view),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
