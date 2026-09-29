"""Add module permissions used by navigation and API authorization."""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0003"
down_revision: str | None = "20260818_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


MODULE_PERMISSIONS = {
    "products.read": "عرض المنتجات",
    "products.manage": "إدارة المنتجات",
    "partners.read": "عرض العملاء والموردين",
    "partners.manage": "إدارة العملاء والموردين",
    "warehouses.read": "عرض المخازن",
    "warehouses.manage": "إدارة المخازن",
    "inventory.read": "عرض المخزون",
    "inventory.manage": "إدارة المخزون",
    "purchases.read": "عرض المشتريات",
    "purchases.manage": "إدارة المشتريات",
    "sales.read": "عرض المبيعات",
    "sales.manage": "إدارة المبيعات",
    "weight_sales.read": "عرض البيع بالوزن",
    "weight_sales.manage": "إدارة البيع بالوزن",
    "manufacturing.read": "عرض التصنيع",
    "manufacturing.manage": "إدارة التصنيع",
    "accounts.read": "عرض الحسابات",
    "accounts.manage": "إدارة الحسابات",
    "returns.read": "عرض المرتجعات",
    "returns.manage": "إدارة المرتجعات",
    "reports.read": "عرض التقارير",
    "settings.read": "عرض الإعدادات",
    "settings.manage": "إدارة الإعدادات",
}

OPERATIONS_READ_CODES = {
    code for code in MODULE_PERMISSIONS if code.endswith(".read")
}


def _tables() -> tuple[sa.TableClause, sa.TableClause, sa.TableClause]:
    permissions = sa.table(
        "permissions",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("module", sa.String()),
        sa.column("action", sa.String()),
        sa.column("name_ar", sa.String()),
        sa.column("description", sa.Text()),
    )
    roles = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Uuid()),
        sa.column("permission_id", sa.Uuid()),
    )
    return permissions, roles, role_permissions


def upgrade() -> None:
    permissions, roles, role_permissions = _tables()
    connection = op.get_bind()
    permission_ids: dict[str, object] = {}

    for code, name_ar in MODULE_PERMISSIONS.items():
        permission_id = connection.scalar(
            sa.select(permissions.c.id).where(permissions.c.code == code)
        )
        if permission_id is None:
            permission_id = uuid4()
            module, action = code.split(".", maxsplit=1)
            connection.execute(
                permissions.insert().values(
                    id=permission_id,
                    code=code,
                    module=module,
                    action=action,
                    name_ar=name_ar,
                    description="",
                )
            )
        permission_ids[code] = permission_id

    role_ids = dict(connection.execute(sa.select(roles.c.code, roles.c.id)).all())
    grants = {
        "system_admin": set(MODULE_PERMISSIONS),
        "operations_manager": OPERATIONS_READ_CODES,
    }
    for role_code, permission_codes in grants.items():
        role_id = role_ids.get(role_code)
        if role_id is None:
            continue
        for code in permission_codes:
            permission_id = permission_ids[code]
            exists = connection.scalar(
                sa.select(role_permissions.c.role_id).where(
                    role_permissions.c.role_id == role_id,
                    role_permissions.c.permission_id == permission_id,
                )
            )
            if exists is None:
                connection.execute(
                    role_permissions.insert().values(
                        role_id=role_id,
                        permission_id=permission_id,
                    )
                )


def downgrade() -> None:
    permissions, _, role_permissions = _tables()
    connection = op.get_bind()
    permission_ids = list(
        connection.scalars(
            sa.select(permissions.c.id).where(
                permissions.c.code.in_(MODULE_PERMISSIONS)
            )
        )
    )
    if permission_ids:
        connection.execute(
            role_permissions.delete().where(
                role_permissions.c.permission_id.in_(permission_ids)
            )
        )
        connection.execute(
            permissions.delete().where(permissions.c.id.in_(permission_ids))
        )
