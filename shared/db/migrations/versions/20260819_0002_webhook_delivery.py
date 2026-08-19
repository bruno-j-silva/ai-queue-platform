"""Complete webhook delivery schema for M3.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("webhook_endpoints", sa.Column("secret_encrypted", sa.String(), nullable=True))
    op.create_index(
        "ix_webhook_endpoints_tenant_status",
        "webhook_endpoints",
        ["tenant_id", "status"],
    )

    op.add_column(
        "jobs",
        sa.Column("webhook_endpoint_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_jobs_webhook_endpoint",
        "jobs",
        "webhook_endpoints",
        ["webhook_endpoint_id"],
        ["id"],
    )

    op.alter_column("webhook_deliveries", "job_id", existing_type=postgresql.UUID(), nullable=True)
    op.add_column("webhook_deliveries", sa.Column("event", sa.String(), nullable=True))
    op.add_column(
        "webhook_deliveries",
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("webhook_deliveries", sa.Column("last_error", sa.String(), nullable=True))
    op.add_column("webhook_deliveries", sa.Column("last_attempt_at", sa.DateTime(), nullable=True))
    op.create_unique_constraint(
        "uq_delivery_job_endpoint_event",
        "webhook_deliveries",
        ["job_id", "endpoint_id", "event"],
    )
    op.create_index(
        "ix_webhook_deliveries_status_next_attempt",
        "webhook_deliveries",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_status_next_attempt", table_name="webhook_deliveries")
    op.drop_constraint("uq_delivery_job_endpoint_event", "webhook_deliveries", type_="unique")
    op.drop_column("webhook_deliveries", "last_attempt_at")
    op.drop_column("webhook_deliveries", "last_error")
    op.drop_column("webhook_deliveries", "payload")
    op.drop_column("webhook_deliveries", "event")
    op.alter_column("webhook_deliveries", "job_id", existing_type=postgresql.UUID(), nullable=False)

    op.drop_constraint("fk_jobs_webhook_endpoint", "jobs", type_="foreignkey")
    op.drop_column("jobs", "webhook_endpoint_id")
    op.drop_index("ix_webhook_endpoints_tenant_status", table_name="webhook_endpoints")
    op.drop_column("webhook_endpoints", "secret_encrypted")
