from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.modules.crm.models import CrmActivity, CrmLead
from app.modules.crm.schemas import (
    ActivityView,
    CompleteActivityRequest,
    CrmOption,
    CrmOptions,
    CrmReportItem,
    CrmSummary,
    LeadPayload,
    LeadView,
    OwnerOption,
    PipelineItem,
    RescheduleActivityRequest,
    ScheduleActivityRequest,
)
from app.modules.identity.models import User
from app.modules.identity.permissions import PermissionCode
from app.modules.identity.service import ClientContext, Principal, add_audit
from app.modules.master_data.models import Partner
from app.modules.master_data.service import allocate_document_number, normalize_code

SOURCES = (
    ("facebook", "فيسبوك"),
    ("instagram", "إنستجرام"),
    ("whatsapp", "واتساب"),
    ("website", "الموقع"),
    ("paid_ad", "إعلان ممول"),
    ("referral", "ترشيح عميل"),
    ("sales_rep", "مندوب"),
    ("inbound_call", "اتصال وارد"),
    ("exhibition", "معرض"),
    ("other", "مصدر آخر"),
)
STAGES = (
    ("new", "عميل جديد"),
    ("not_contacted", "لم يتم التواصل"),
    ("contacted", "تم التواصل"),
    ("interested", "مهتم"),
    ("quotation", "إرسال عرض سعر"),
    ("negotiation", "تفاوض"),
    ("waiting", "انتظار قرار"),
    ("won", "تم البيع"),
    ("postponed", "مؤجل"),
    ("no_answer", "لا يرد"),
    ("not_interested", "غير مهتم"),
    ("invalid_phone", "رقم غير صحيح"),
    ("lost", "خسارة الصفقة"),
)
SOURCE_NAMES = dict(SOURCES)
STAGE_NAMES = dict(STAGES)
LOST_STAGES = {"not_interested", "invalid_phone", "lost"}


class CrmNotFound(Exception):
    pass


class CrmConflict(Exception):
    pass


def _can_manage(principal: Principal) -> bool:
    return PermissionCode.CRM_MANAGE in principal.permissions


def can_schedule_activities(principal: Principal) -> bool:
    return "system_admin" in principal.roles


def sync_customers_to_leads(db: Session, principal: Principal) -> int:
    """Mirror Desktop's idempotent customer-to-CRM synchronization on navigation."""
    customers = list(
        db.scalars(
            select(Partner)
            .where(Partner.is_customer.is_(True), Partner.is_active.is_(True))
            .order_by(Partner.id)
            .with_for_update()
        )
    )
    synced = 0
    now = datetime.now(UTC)
    for customer in customers:
        lead = db.scalar(
            select(CrmLead).where(CrmLead.customer_partner_id == customer.id).limit(1)
        )
        subject = ""
        if lead is None and customer.phone.strip():
            lead = db.scalar(
                select(CrmLead)
                .where(
                    CrmLead.phone == customer.phone.strip(),
                    CrmLead.is_active.is_(True),
                    CrmLead.customer_partner_id.is_(None),
                )
                .order_by(CrmLead.created_at.desc(), CrmLead.id.desc())
                .limit(1)
            )
            if lead is not None:
                subject = "ربط العميل الحالي بسجل CRM"
        if lead is None:
            lead = CrmLead(
                lead_number=allocate_document_number(db, "crm_lead"),
                name=customer.name_ar,
                phone=customer.phone.strip(),
                address=customer.address,
                source_code="other",
                customer_type="customer",
                temperature="warm",
                stage_code="won",
                assigned_user_id=principal.user.id,
                tags="عميل سابق",
                general_notes=f"تمت المزامنة من شاشة العملاء — الكود: {customer.code or '-'}",
                customer_partner_id=customer.id,
                created_by_id=principal.user.id,
                is_active=True,
            )
            db.add(lead)
            db.flush()
            subject = "استيراد عميل حالي إلى CRM"
        else:
            lead.name = customer.name_ar
            lead.phone = customer.phone.strip()
            lead.address = customer.address
            lead.customer_partner_id = customer.id
            lead.customer_type = "customer"
            lead.stage_code = "won"
            lead.is_active = True
        if subject:
            db.add(
                CrmActivity(
                    lead_id=lead.id,
                    activity_type="conversion",
                    subject=subject,
                    notes=f"تم الربط بالعميل رقم {customer.id}",
                    assigned_user_id=principal.user.id,
                    status="done",
                    created_by_id=principal.user.id,
                    completed_at=now,
                )
            )
            synced += 1
    db.flush()
    return synced


def _lead_query(principal: Principal) -> Select[tuple[CrmLead]]:
    statement = select(CrmLead)
    return (
        statement
        if _can_manage(principal)
        else statement.where(CrmLead.assigned_user_id == principal.user.id)
    )


def _get_lead(db: Session, lead_id: UUID, principal: Principal, *, lock: bool = False) -> CrmLead:
    statement = _lead_query(principal).where(CrmLead.id == lead_id)
    if lock:
        statement = statement.with_for_update()
    lead = db.scalar(statement)
    if lead is None or not lead.is_active:
        raise CrmNotFound("العميل المحتمل غير موجود أو غير مسموح لك بعرضه")
    return lead


def _lead_view(db: Session, lead: CrmLead) -> LeadView:
    owner = db.get(User, lead.assigned_user_id)
    next_activity = db.scalar(
        select(func.min(CrmActivity.due_at)).where(
            CrmActivity.lead_id == lead.id, CrmActivity.status == "scheduled"
        )
    )
    activity_count = int(
        db.scalar(select(func.count(CrmActivity.id)).where(CrmActivity.lead_id == lead.id)) or 0
    )
    return LeadView(
        **{
            field: getattr(lead, field)
            for field in (
                "id",
                "lead_number",
                "name",
                "phone",
                "alternate_phone",
                "company",
                "address",
                "source_code",
                "customer_type",
                "temperature",
                "stage_code",
                "assigned_user_id",
                "interested_products",
                "tags",
                "opportunity_value",
                "general_notes",
                "lost_reason",
                "customer_partner_id",
                "last_contact_at",
                "created_at",
            )
        },
        source_name=SOURCE_NAMES.get(lead.source_code, lead.source_code),
        stage_name=STAGE_NAMES.get(lead.stage_code, lead.stage_code),
        owner_name=owner.display_name if owner else "",
        next_activity_at=next_activity,
        activity_count=activity_count,
    )


def options(db: Session, principal: Principal) -> CrmOptions:
    owners = (
        [principal.user]
        if not _can_manage(principal)
        else list(
            db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.display_name))
        )
    )
    return CrmOptions(
        sources=[CrmOption(code=code, name=name) for code, name in SOURCES],
        stages=[CrmOption(code=code, name=name) for code, name in STAGES],
        owners=[OwnerOption(id=user.id, name=user.display_name) for user in owners],
    )


def list_leads(
    db: Session,
    principal: Principal,
    *,
    search: str = "",
    stage: str | None = None,
    owner_id: UUID | None = None,
) -> list[LeadView]:
    statement = _lead_query(principal).where(CrmLead.is_active.is_(True))
    if search.strip():
        token = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                CrmLead.lead_number.ilike(token),
                CrmLead.name.ilike(token),
                CrmLead.phone.ilike(token),
                CrmLead.company.ilike(token),
                CrmLead.tags.ilike(token),
            )
        )
    if stage:
        statement = statement.where(CrmLead.stage_code == stage)
    if owner_id:
        statement = statement.where(CrmLead.assigned_user_id == owner_id)
    rows = db.scalars(statement.order_by(CrmLead.updated_at.desc(), CrmLead.id.desc()))
    return [_lead_view(db, row) for row in rows]


def save_lead(
    db: Session,
    *,
    payload: LeadPayload,
    principal: Principal,
    client: ClientContext,
    lead_id: UUID | None = None,
) -> LeadView:
    if payload.source_code not in SOURCE_NAMES or payload.stage_code not in STAGE_NAMES:
        raise CrmConflict("المصدر أو المرحلة غير صحيحة")
    duplicate = db.scalar(
        select(CrmLead.id).where(
            CrmLead.phone == payload.phone.strip(),
            CrmLead.is_active.is_(True),
            CrmLead.id != lead_id if lead_id else CrmLead.id.is_not(None),
        )
    )
    if duplicate is not None:
        raise CrmConflict("رقم الهاتف مسجل لعميل محتمل آخر")
    lead = (
        _get_lead(db, lead_id, principal, lock=True)
        if lead_id
        else CrmLead(
            lead_number=allocate_document_number(db, "crm_lead"),
            assigned_user_id=principal.user.id,
            created_by_id=principal.user.id,
        )
    )
    owner_id = payload.assigned_user_id if _can_manage(principal) else principal.user.id
    if owner_id is None or db.get(User, owner_id) is None:
        raise CrmNotFound("مسؤول المتابعة غير موجود")
    for field in (
        "name",
        "phone",
        "alternate_phone",
        "company",
        "address",
        "source_code",
        "customer_type",
        "temperature",
        "stage_code",
        "interested_products",
        "tags",
        "opportunity_value",
        "general_notes",
        "lost_reason",
    ):
        value = getattr(payload, field)
        setattr(lead, field, value.strip() if isinstance(value, str) else value)
    lead.assigned_user_id = owner_id
    if lead_id is None:
        db.add(lead)
        db.flush()
        db.add(
            CrmActivity(
                lead_id=lead.id,
                activity_type="note",
                subject="إنشاء العميل المحتمل",
                notes=lead.lead_number,
                assigned_user_id=owner_id,
                status="done",
                created_by_id=principal.user.id,
                completed_at=datetime.now(UTC),
            )
        )
    add_audit(
        db,
        actor_user_id=principal.user.id,
        event_type="crm.lead.update" if lead_id else "crm.lead.create",
        entity_type="crm_lead",
        entity_id=str(lead.id),
        outcome="success",
        client=client,
        after_state={"lead_number": lead.lead_number, "stage": lead.stage_code},
    )
    db.flush()
    return _lead_view(db, lead)


def set_stage(db: Session, *, lead_id: UUID, stage: str, principal: Principal) -> LeadView:
    if stage not in STAGE_NAMES:
        raise CrmConflict("مرحلة غير صحيحة")
    lead = _get_lead(db, lead_id, principal, lock=True)
    before = lead.stage_code
    lead.stage_code = stage
    db.add(
        CrmActivity(
            lead_id=lead.id,
            activity_type="stage",
            subject="تغيير المرحلة",
            notes=f"من {STAGE_NAMES.get(before, before)} إلى {STAGE_NAMES[stage]}",
            assigned_user_id=lead.assigned_user_id,
            status="done",
            created_by_id=principal.user.id,
            completed_at=datetime.now(UTC),
        )
    )
    db.flush()
    return _lead_view(db, lead)


def add_note(
    db: Session, *, lead_id: UUID, note: str, kind: str, principal: Principal
) -> ActivityView:
    lead = _get_lead(db, lead_id, principal, lock=True)
    activity = CrmActivity(
        lead_id=lead.id,
        activity_type=kind,
        subject="ملاحظة متابعة",
        notes=note.strip(),
        assigned_user_id=lead.assigned_user_id,
        status="done",
        created_by_id=principal.user.id,
        completed_at=datetime.now(UTC),
    )
    lead.last_contact_at = datetime.now(UTC)
    db.add(activity)
    db.flush()
    return _activity_view(db, activity)


def schedule_activity(
    db: Session, *, lead_id: UUID, payload: ScheduleActivityRequest, principal: Principal
) -> ActivityView:
    if not can_schedule_activities(principal):
        raise CrmConflict("جدولة الأنشطة متاحة للأدمن فقط")
    lead = _get_lead(db, lead_id, principal)
    owner_id = payload.assigned_user_id if _can_manage(principal) else principal.user.id
    activity = CrmActivity(
        lead_id=lead.id,
        activity_type=payload.activity_type,
        subject=payload.subject.strip(),
        notes=payload.notes.strip(),
        due_at=payload.due_at,
        priority=payload.priority,
        assigned_user_id=owner_id or lead.assigned_user_id,
        status="scheduled",
        created_by_id=principal.user.id,
    )
    db.add(activity)
    db.flush()
    return _activity_view(db, activity)


def _activity_view(db: Session, activity: CrmActivity) -> ActivityView:
    lead = db.get(CrmLead, activity.lead_id)
    owner = db.get(User, activity.assigned_user_id)
    if lead is None:
        raise CrmNotFound("العميل المحتمل المرتبط بالنشاط غير موجود")
    return ActivityView(
        **{
            field: getattr(activity, field)
            for field in (
                "id",
                "lead_id",
                "activity_type",
                "subject",
                "notes",
                "due_at",
                "priority",
                "assigned_user_id",
                "status",
                "outcome",
                "completed_at",
                "created_at",
            )
        },
        lead_number=lead.lead_number,
        lead_name=lead.name,
        phone=lead.phone,
        owner_name=owner.display_name if owner else "",
    )


def list_activities(
    db: Session, principal: Principal, status: str | None = None
) -> list[ActivityView]:
    statement = (
        select(CrmActivity)
        .join(CrmLead, CrmLead.id == CrmActivity.lead_id)
        .where(CrmLead.is_active.is_(True))
    )
    if not _can_manage(principal):
        statement = statement.where(CrmActivity.assigned_user_id == principal.user.id)
    if status:
        statement = statement.where(CrmActivity.status == status)
    rows = db.scalars(statement.order_by(CrmActivity.due_at, CrmActivity.created_at.desc()))
    return [_activity_view(db, row) for row in rows]


def complete_activity(
    db: Session, activity_id: UUID, payload: CompleteActivityRequest, principal: Principal
) -> ActivityView:
    activity = _get_activity(db, activity_id, principal)
    activity.status = "done"
    activity.outcome = payload.outcome.strip()
    activity.completed_at = datetime.now(UTC)
    lead = db.get(CrmLead, activity.lead_id)
    if lead:
        lead.last_contact_at = datetime.now(UTC)
    db.flush()
    return _activity_view(db, activity)


def reschedule_activity(
    db: Session, activity_id: UUID, payload: RescheduleActivityRequest, principal: Principal
) -> ActivityView:
    activity = _get_activity(db, activity_id, principal)
    activity.status = "scheduled"
    activity.due_at = payload.due_at
    activity.completed_at = None
    activity.outcome = ""
    db.flush()
    return _activity_view(db, activity)


def cancel_activity(db: Session, activity_id: UUID, principal: Principal) -> ActivityView:
    activity = _get_activity(db, activity_id, principal)
    activity.status = "cancelled"
    db.flush()
    return _activity_view(db, activity)


def _get_activity(db: Session, activity_id: UUID, principal: Principal) -> CrmActivity:
    statement = select(CrmActivity).where(CrmActivity.id == activity_id).with_for_update()
    if not _can_manage(principal):
        statement = statement.where(CrmActivity.assigned_user_id == principal.user.id)
    activity = db.scalar(statement)
    if activity is None:
        raise CrmNotFound("النشاط غير موجود")
    return activity


def convert_to_customer(db: Session, lead_id: UUID, principal: Principal) -> UUID:
    lead = _get_lead(db, lead_id, principal, lock=True)
    if lead.customer_partner_id:
        return lead.customer_partner_id
    partner = db.scalar(
        select(Partner).where(
            Partner.phone == lead.phone, Partner.is_customer.is_(True), Partner.is_active.is_(True)
        )
    )
    if partner is None:
        code = f"CRM-{lead.lead_number}"
        partner = Partner(
            code=code,
            normalized_code=normalize_code(code),
            name_ar=lead.name,
            phone=lead.phone,
            address=lead.address,
            tax_number="",
            is_customer=True,
            is_supplier=False,
            is_active=True,
            version=1,
        )
        db.add(partner)
        db.flush()
    lead.customer_partner_id = partner.id
    lead.customer_type = "customer"
    lead.stage_code = "won"
    db.flush()
    return partner.id


def summary(db: Session, principal: Principal) -> CrmSummary:
    leads = list(db.scalars(_lead_query(principal).where(CrmLead.is_active.is_(True))))
    activities = list_activities(db, principal, "scheduled")
    now = datetime.now(UTC)
    due_dates = [
        item.due_at.replace(tzinfo=UTC)
        if item.due_at is not None and item.due_at.tzinfo is None
        else item.due_at
        for item in activities
    ]
    return CrmSummary(
        total=len(leads),
        new_count=sum(x.stage_code == "new" for x in leads),
        hot_count=sum(
            x.temperature == "hot" and x.stage_code not in LOST_STAGES | {"won"} for x in leads
        ),
        won_count=sum(x.stage_code == "won" for x in leads),
        open_value=sum(
            (x.opportunity_value for x in leads if x.stage_code not in LOST_STAGES | {"won"}),
            Decimal("0"),
        ),
        today_count=sum(due is not None and due.date() == now.date() for due in due_dates),
        overdue_count=sum(due is not None and due < now for due in due_dates),
    )


def pipeline(db: Session, principal: Principal) -> list[PipelineItem]:
    leads = list(db.scalars(_lead_query(principal).where(CrmLead.is_active.is_(True))))
    return [
        PipelineItem(
            code=code,
            name=name,
            lead_count=sum(x.stage_code == code for x in leads),
            total_value=sum(
                (x.opportunity_value for x in leads if x.stage_code == code), Decimal("0")
            ),
        )
        for code, name in STAGES
    ]


def reports(db: Session, principal: Principal, mode: str) -> list[CrmReportItem]:
    if mode not in {"source", "owner", "lost"}:
        raise ValueError("نوع تقرير CRM غير صحيح")
    leads = list(db.scalars(_lead_query(principal).where(CrmLead.is_active.is_(True))))
    owner_names = {
        user.id: user.display_name
        for user in db.scalars(select(User).where(User.is_active.is_(True)))
    }
    grouped: dict[str, CrmReportItem] = {}
    for lead in leads:
        if mode == "lost" and lead.stage_code not in LOST_STAGES:
            continue
        if mode == "source":
            label = SOURCE_NAMES.get(lead.source_code, "غير محدد")
        elif mode == "owner":
            label = owner_names.get(lead.assigned_user_id, "غير مسند")
        else:
            label = lead.lost_reason.strip() or "غير محدد"
        item = grouped.setdefault(
            label,
            CrmReportItem(label=label, total=0, won=0, value=Decimal("0")),
        )
        item.total += 1
        if lead.stage_code == "won":
            item.won += 1
        if mode != "lost":
            item.value += lead.opportunity_value
    rows = list(grouped.values())
    if mode == "owner":
        return sorted(rows, key=lambda item: (-item.won, -item.total, item.label))
    return sorted(rows, key=lambda item: (-item.total, item.label))
