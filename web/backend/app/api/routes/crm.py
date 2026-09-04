from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import (
    CurrentPrincipal,
    DatabaseSession,
    client_context,
    enforce_csrf,
    enforce_permission,
)
from app.modules.crm.schemas import (
    ActivityView,
    CompleteActivityRequest,
    CrmOptions,
    CrmReportItem,
    CrmSummary,
    LeadPayload,
    LeadView,
    NoteRequest,
    PipelineItem,
    RescheduleActivityRequest,
    ScheduleActivityRequest,
    StageRequest,
)
from app.modules.crm.service import (
    CrmConflict,
    CrmNotFound,
    add_note,
    can_schedule_activities,
    cancel_activity,
    complete_activity,
    convert_to_customer,
    list_activities,
    list_leads,
    options,
    pipeline,
    reports,
    reschedule_activity,
    save_lead,
    schedule_activity,
    set_stage,
    summary,
    sync_customers_to_leads,
)
from app.modules.identity.permissions import PermissionCode

router = APIRouter(prefix="/crm")


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, CrmNotFound):
        return HTTPException(404, str(exc))
    if isinstance(exc, (CrmConflict, IntegrityError)):
        return HTTPException(409, str(exc))
    return HTTPException(422, str(exc))


def _read(request: Request, db: DatabaseSession, principal: CurrentPrincipal) -> None:
    enforce_permission(request, db, principal, PermissionCode.CRM_READ)


def _manage(request: Request, db: DatabaseSession, principal: CurrentPrincipal) -> None:
    enforce_permission(request, db, principal, PermissionCode.CRM_MANAGE)
    enforce_csrf(request, db, principal)


@router.get("/options", response_model=CrmOptions)
def crm_options(request: Request, principal: CurrentPrincipal, db: DatabaseSession) -> CrmOptions:
    _read(request, db, principal)
    try:
        sync_customers_to_leads(db, principal)
        result = options(db, principal)
        db.commit()
        return result
    except (CrmNotFound, CrmConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/summary", response_model=CrmSummary)
def crm_summary(request: Request, principal: CurrentPrincipal, db: DatabaseSession) -> CrmSummary:
    _read(request, db, principal)
    return summary(db, principal)


@router.get("/pipeline", response_model=list[PipelineItem])
def crm_pipeline(
    request: Request, principal: CurrentPrincipal, db: DatabaseSession
) -> list[PipelineItem]:
    _read(request, db, principal)
    return pipeline(db, principal)


@router.get("/reports", response_model=list[CrmReportItem])
def crm_reports(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    mode: str = "source",
) -> list[CrmReportItem]:
    _read(request, db, principal)
    try:
        return reports(db, principal, mode)
    except ValueError as exc:
        raise _error(exc) from exc


@router.get("/leads", response_model=list[LeadView])
def leads(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    search: str = "",
    stage: str | None = None,
    owner_id: UUID | None = None,
) -> list[LeadView]:
    _read(request, db, principal)
    return list_leads(db, principal, search=search, stage=stage, owner_id=owner_id)


@router.post("/leads", response_model=LeadView, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadPayload, request: Request, principal: CurrentPrincipal, db: DatabaseSession
) -> LeadView:
    _manage(request, db, principal)
    try:
        result = save_lead(db, payload=payload, principal=principal, client=client_context(request))
        db.commit()
        return result
    except (CrmNotFound, CrmConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _error(exc) from exc


@router.put("/leads/{lead_id}", response_model=LeadView)
def update_lead(
    lead_id: UUID,
    payload: LeadPayload,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> LeadView:
    _manage(request, db, principal)
    try:
        result = save_lead(
            db,
            lead_id=lead_id,
            payload=payload,
            principal=principal,
            client=client_context(request),
        )
        db.commit()
        return result
    except (CrmNotFound, CrmConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/leads/{lead_id}/stage", response_model=LeadView)
def change_stage(
    lead_id: UUID,
    payload: StageRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> LeadView:
    _manage(request, db, principal)
    try:
        result = set_stage(db, lead_id=lead_id, stage=payload.stage_code, principal=principal)
        db.commit()
        return result
    except (CrmNotFound, CrmConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/leads/{lead_id}/notes", response_model=ActivityView, status_code=201)
def lead_note(
    lead_id: UUID,
    payload: NoteRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> ActivityView:
    _manage(request, db, principal)
    try:
        result = add_note(
            db, lead_id=lead_id, note=payload.note, kind=payload.activity_type, principal=principal
        )
        db.commit()
        return result
    except (CrmNotFound, CrmConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/leads/{lead_id}/activities", response_model=ActivityView, status_code=201)
def create_activity(
    lead_id: UUID,
    payload: ScheduleActivityRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> ActivityView:
    _manage(request, db, principal)
    if not can_schedule_activities(principal):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "جدولة الأنشطة متاحة للأدمن فقط")
    try:
        result = schedule_activity(db, lead_id=lead_id, payload=payload, principal=principal)
        db.commit()
        return result
    except (CrmNotFound, CrmConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/activities", response_model=list[ActivityView])
def activities(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    activity_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[ActivityView]:
    _read(request, db, principal)
    return list_activities(db, principal, activity_status)


@router.post("/activities/{activity_id}/completion", response_model=ActivityView)
def activity_completion(
    activity_id: UUID,
    payload: CompleteActivityRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> ActivityView:
    _manage(request, db, principal)
    try:
        result = complete_activity(db, activity_id, payload, principal)
        db.commit()
        return result
    except (CrmNotFound, CrmConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/activities/{activity_id}/reschedule", response_model=ActivityView)
def activity_reschedule(
    activity_id: UUID,
    payload: RescheduleActivityRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> ActivityView:
    _manage(request, db, principal)
    try:
        result = reschedule_activity(db, activity_id, payload, principal)
        db.commit()
        return result
    except (CrmNotFound, CrmConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/activities/{activity_id}/cancellation", response_model=ActivityView)
def activity_cancellation(
    activity_id: UUID, request: Request, principal: CurrentPrincipal, db: DatabaseSession
) -> ActivityView:
    _manage(request, db, principal)
    try:
        result = cancel_activity(db, activity_id, principal)
        db.commit()
        return result
    except (CrmNotFound, CrmConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/leads/{lead_id}/conversion")
def conversion(
    lead_id: UUID, request: Request, principal: CurrentPrincipal, db: DatabaseSession
) -> dict[str, UUID]:
    _manage(request, db, principal)
    try:
        partner_id = convert_to_customer(db, lead_id, principal)
        db.commit()
        return {"partner_id": partner_id}
    except (CrmNotFound, CrmConflict, IntegrityError, ValueError) as exc:
        db.rollback()
        raise _error(exc) from exc
