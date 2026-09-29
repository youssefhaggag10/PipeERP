from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Temperature = Literal["cold", "warm", "hot"]
ActivityStatus = Literal["scheduled", "done", "cancelled"]


class CrmView(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LeadPayload(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=3, max_length=40)
    alternate_phone: str = Field(default="", max_length=40)
    company: str = Field(default="", max_length=200)
    address: str = Field(default="", max_length=2000)
    source_code: str = Field(default="other", max_length=40)
    customer_type: str = Field(default="potential", max_length=40)
    temperature: Temperature = "warm"
    stage_code: str = Field(default="new", max_length=40)
    assigned_user_id: UUID | None = None
    interested_products: str = Field(default="", max_length=2000)
    tags: str = Field(default="", max_length=1000)
    opportunity_value: Decimal = Field(default=Decimal("0"), ge=0)
    general_notes: str = Field(default="", max_length=4000)
    lost_reason: str = Field(default="", max_length=1000)


class LeadView(CrmView):
    id: UUID
    lead_number: str
    name: str
    phone: str
    alternate_phone: str
    company: str
    address: str
    source_code: str
    source_name: str
    customer_type: str
    temperature: Temperature
    stage_code: str
    stage_name: str
    assigned_user_id: UUID
    owner_name: str
    interested_products: str
    tags: str
    opportunity_value: Decimal
    general_notes: str
    lost_reason: str
    customer_partner_id: UUID | None
    last_contact_at: datetime | None
    next_activity_at: datetime | None
    activity_count: int
    created_at: datetime


class StageRequest(BaseModel):
    stage_code: str = Field(min_length=1, max_length=40)


class NoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=4000)
    activity_type: str = Field(default="note", max_length=40)


class ScheduleActivityRequest(BaseModel):
    activity_type: str = Field(default="call", max_length=40)
    subject: str = Field(min_length=2, max_length=200)
    notes: str = Field(default="", max_length=4000)
    due_at: datetime
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    assigned_user_id: UUID | None = None


class CompleteActivityRequest(BaseModel):
    outcome: str = Field(default="", max_length=4000)


class RescheduleActivityRequest(BaseModel):
    due_at: datetime


class ActivityView(CrmView):
    id: UUID
    lead_id: UUID
    lead_number: str
    lead_name: str
    phone: str
    activity_type: str
    subject: str
    notes: str
    due_at: datetime | None
    priority: str
    assigned_user_id: UUID
    owner_name: str
    status: ActivityStatus
    outcome: str
    completed_at: datetime | None
    created_at: datetime


class CrmOption(BaseModel):
    code: str
    name: str


class OwnerOption(BaseModel):
    id: UUID
    name: str


class CrmOptions(BaseModel):
    sources: list[CrmOption]
    stages: list[CrmOption]
    owners: list[OwnerOption]


class CrmSummary(BaseModel):
    total: int
    new_count: int
    hot_count: int
    won_count: int
    open_value: Decimal
    today_count: int
    overdue_count: int


class PipelineItem(BaseModel):
    code: str
    name: str
    lead_count: int
    total_value: Decimal


class CrmReportItem(BaseModel):
    label: str
    total: int
    won: int
    value: Decimal
