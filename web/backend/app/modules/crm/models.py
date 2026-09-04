from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin


class CrmLead(TimestampMixin, Base):
    __tablename__ = "crm_leads"
    __table_args__ = (
        UniqueConstraint("lead_number"),
        CheckConstraint("opportunity_value >= 0", name="opportunity_value_nonnegative"),
        CheckConstraint("temperature IN ('cold','warm','hot')", name="temperature_valid"),
        Index("ix_crm_leads_stage_active", "stage_code", "is_active"),
        Index("ix_crm_leads_owner_active", "assigned_user_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    lead_number: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(40), nullable=False)
    alternate_phone: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    company: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    address: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_code: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    customer_type: Mapped[str] = mapped_column(String(40), nullable=False, default="potential")
    temperature: Mapped[str] = mapped_column(String(12), nullable=False, default="warm")
    stage_code: Mapped[str] = mapped_column(String(40), nullable=False, default="new")
    assigned_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    interested_products: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="")
    opportunity_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    general_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lost_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    customer_partner_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT")
    )
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)


class CrmActivity(TimestampMixin, Base):
    __tablename__ = "crm_activities"
    __table_args__ = (
        CheckConstraint("status IN ('scheduled','done','cancelled')", name="status_valid"),
        CheckConstraint("priority IN ('low','normal','high','urgent')", name="priority_valid"),
        Index("ix_crm_activities_due", "status", "due_at"),
        Index("ix_crm_activities_lead", "lead_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("crm_leads.id", ondelete="CASCADE"), nullable=False
    )
    activity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    priority: Mapped[str] = mapped_column(String(12), nullable=False, default="normal")
    assigned_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="scheduled")
    outcome: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
