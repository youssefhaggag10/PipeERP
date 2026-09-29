"""Allow the ordered company phone list used by desktop print settings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_0015"
down_revision: str | None = "20260824_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "company_settings",
        "phone",
        existing_type=sa.String(length=40),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE company_settings SET phone = LEFT(phone, 40)"))
    op.alter_column(
        "company_settings",
        "phone",
        existing_type=sa.Text(),
        type_=sa.String(length=40),
        existing_nullable=False,
    )
