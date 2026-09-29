"""Backfill the payable document for legacy received purchase orders."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0016"
down_revision: str | None = "20260824_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    sqlite = connection.dialect.name == "sqlite"
    rows = connection.execute(
        sa.text(
            """
            SELECT po.id, po.supplier_id, po.total
            FROM purchase_orders AS po
            LEFT JOIN supplier_invoices AS si ON si.purchase_order_id = po.id
            WHERE po.status = 'received' AND si.id IS NULL
            ORDER BY po.order_date, po.id
            """
        )
    ).mappings()
    now = datetime.now(UTC)
    for row in rows:
        order_id = UUID(str(row["id"]))
        invoice_id = uuid4()
        suffix = order_id.hex[:30]
        connection.execute(
            sa.text(
                """
                INSERT INTO supplier_invoices (
                    id, invoice_number, supplier_invoice_number,
                    purchase_order_id, supplier_id, status, total,
                    posted_at, version, created_at, updated_at
                ) VALUES (
                    :id, :invoice_number, :supplier_invoice_number,
                    :purchase_order_id, :supplier_id, 'posted', :total,
                    :posted_at, 1, :created_at, :updated_at
                )
                """
            ),
            {
                # SQLAlchemy's UUID type is stored as 32 hex characters by SQLite,
                # while PostgreSQL accepts the canonical dashed representation.
                "id": invoice_id.hex if sqlite else str(invoice_id),
                "invoice_number": f"PI-LEGACY-{suffix}",
                "supplier_invoice_number": f"LEGACY-{order_id.hex}",
                # Preserve the database-native representation of existing UUIDs so
                # the backfill also satisfies SQLite foreign keys in local installs.
                "purchase_order_id": row["id"],
                "supplier_id": row["supplier_id"],
                "total": row["total"],
                "posted_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    # The migration repairs accounting history. Downgrade must not delete posted invoices.
    pass
