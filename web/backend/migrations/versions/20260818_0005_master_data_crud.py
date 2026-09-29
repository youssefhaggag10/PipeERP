"""Add optimistic versions and enforce a single default warehouse."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0005"
down_revision: str | None = "20260818_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("units_of_measure", "product_categories", "company_settings"):
        op.add_column(
            table_name,
            sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        )
        op.alter_column(table_name, "version", server_default=None)
    op.create_index(
        "uq_warehouses_single_default",
        "warehouses",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )


def downgrade() -> None:
    op.drop_index("uq_warehouses_single_default", table_name="warehouses")
    for table_name in ("company_settings", "product_categories", "units_of_measure"):
        op.drop_column(table_name, "version")
