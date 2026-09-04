"""Add the audit index used by login rate limiting."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260818_0002"
down_revision: str | None = "20260818_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_logs_login_rate",
        "audit_logs",
        ["event_type", "ip_address", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_login_rate", table_name="audit_logs")
