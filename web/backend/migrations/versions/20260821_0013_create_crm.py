"""Create CRM leads and activities."""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0013"
down_revision: str | None = "20260821_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_leads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lead_number", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(40), nullable=False),
        sa.Column("alternate_phone", sa.String(40), nullable=False, server_default=""),
        sa.Column("company", sa.String(200), nullable=False, server_default=""),
        sa.Column("address", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_code", sa.String(40), nullable=False, server_default="other"),
        sa.Column("customer_type", sa.String(40), nullable=False, server_default="potential"),
        sa.Column("temperature", sa.String(12), nullable=False, server_default="warm"),
        sa.Column("stage_code", sa.String(40), nullable=False, server_default="new"),
        sa.Column(
            "assigned_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("interested_products", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", sa.Text(), nullable=False, server_default=""),
        sa.Column("opportunity_value", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("general_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("lost_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "customer_partner_id", sa.Uuid(), sa.ForeignKey("partners.id", ondelete="RESTRICT")
        ),
        sa.Column(
            "created_by_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("last_contact_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "opportunity_value >= 0", name="ck_crm_leads_opportunity_value_nonnegative"
        ),
        sa.CheckConstraint(
            "temperature IN ('cold','warm','hot')", name="ck_crm_leads_temperature_valid"
        ),
    )
    op.create_index("ix_crm_leads_stage_active", "crm_leads", ["stage_code", "is_active"])
    op.create_index("ix_crm_leads_owner_active", "crm_leads", ["assigned_user_id", "is_active"])
    op.create_table(
        "crm_activities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "lead_id", sa.Uuid(), sa.ForeignKey("crm_leads.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("activity_type", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("priority", sa.String(12), nullable=False, server_default="normal"),
        sa.Column(
            "assigned_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="scheduled"),
        sa.Column("outcome", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_by_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('scheduled','done','cancelled')", name="ck_crm_activities_status_valid"
        ),
        sa.CheckConstraint(
            "priority IN ('low','normal','high','urgent')", name="ck_crm_activities_priority_valid"
        ),
    )
    op.create_index("ix_crm_activities_due", "crm_activities", ["status", "due_at"])
    op.create_index("ix_crm_activities_lead", "crm_activities", ["lead_id", "created_at"])

    connection = op.get_bind()
    permissions = sa.table(
        "permissions",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("module", sa.String()),
        sa.column("action", sa.String()),
        sa.column("name_ar", sa.String()),
        sa.column("description", sa.Text()),
    )
    roles = sa.table("roles", sa.column("id", sa.Uuid()), sa.column("code", sa.String()))
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", sa.Uuid()), sa.column("permission_id", sa.Uuid())
    )
    permission_ids = {}
    for code, name in (("crm.read", "عرض متابعة العملاء"), ("crm.manage", "إدارة متابعة العملاء")):
        permission_id = uuid4()
        permission_ids[code] = permission_id
        connection.execute(
            permissions.insert().values(
                id=permission_id,
                code=code,
                module="crm",
                action=code.split(".")[1],
                name_ar=name,
                description="",
            )
        )
    role_ids = dict(connection.execute(sa.select(roles.c.code, roles.c.id)).all())
    for role_code, codes in (
        ("system_admin", permission_ids),
        ("operations_manager", {"crm.read": permission_ids["crm.read"]}),
    ):
        if role_id := role_ids.get(role_code):
            for permission_id in codes.values():
                connection.execute(
                    role_permissions.insert().values(role_id=role_id, permission_id=permission_id)
                )
    connection.execute(
        sa.text(
            "INSERT INTO document_sequences "
            "(document_type, prefix, next_value, padding, version) "
            "VALUES ('crm_lead', 'LD-', 1, 6, 1)"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM document_sequences WHERE document_type='crm_lead'"))
    connection.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code IN ('crm.read','crm.manage'))"
        )
    )
    connection.execute(sa.text("DELETE FROM permissions WHERE code IN ('crm.read','crm.manage')"))
    op.drop_table("crm_activities")
    op.drop_table("crm_leads")
