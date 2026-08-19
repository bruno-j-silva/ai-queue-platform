"""initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. plans
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("priority_weight", sa.Integer(), nullable=False),
        sa.Column("max_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("result_ttl_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("max_payload_mb", sa.Integer(), nullable=False),
    )

    # 2. tenants
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "suspended", name="tenant_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # 3. api_keys
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("prefix", sa.String(8), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "revoked", name="api_key_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # 4. models (catalog)
    op.create_table(
        "models",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "backend",
            sa.Enum("ollama", "vllm", name="model_backend"),
            nullable=False,
        ),
        sa.Column("backend_model_name", sa.String(), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(), nullable=True),
        sa.Column("pool", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", name="model_status"),
            nullable=False,
            server_default="active",
        ),
    )

    # 5. plan_models
    op.create_table(
        "plan_models",
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id"),
            primary_key=True,
        ),
        sa.Column("model_id", sa.String(), sa.ForeignKey("models.id"), primary_key=True),
    )

    # 6. artifacts
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.Enum("input", "output", name="artifact_kind"),
            nullable=False,
        ),
        sa.Column("media_type", sa.String(), nullable=True),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # 7. jobs
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("model_id", sa.String(), sa.ForeignKey("models.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "succeeded",
                "failed",
                "cancelled",
                "expired",
                name="job_status",
            ),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("priority_weight", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("result_inline", postgresql.JSONB(), nullable=True),
        sa.Column("result_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("usage", postgresql.JSONB(), nullable=True),
        sa.Column("queued_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_tenant_id", "jobs", ["tenant_id"])
    op.create_index("ix_jobs_tenant_id_queued_at", "jobs", ["tenant_id", "queued_at"])
    op.create_unique_constraint(
        "uq_jobs_tenant_idempotency_key", "jobs", ["tenant_id", "idempotency_key"]
    )

    # 8. job_events
    op.create_table(
        "job_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id"),
            nullable=False,
        ),
        sa.Column(
            "from_status",
            sa.Enum(
                "queued",
                "running",
                "succeeded",
                "failed",
                "cancelled",
                "expired",
                name="job_status",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "queued",
                "running",
                "succeeded",
                "failed",
                "cancelled",
                "expired",
                name="job_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )

    # 9. webhook_endpoints
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("secret_hash", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", name="webhook_endpoint_status"),
            nullable=False,
            server_default="active",
        ),
    )

    # 10. webhook_deliveries
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id"),
            nullable=False,
        ),
        sa.Column(
            "endpoint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhook_endpoints.id"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "delivering",
                "delivered",
                "dead",
                name="webhook_delivery_status",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_response_code", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # 11. outbox
    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # Drop in reverse FK order
    op.drop_table("outbox")
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
    op.drop_table("job_events")
    op.drop_index("ix_jobs_tenant_id_queued_at", table_name="jobs")
    op.drop_index("ix_jobs_tenant_id", table_name="jobs")
    op.drop_constraint("uq_jobs_tenant_idempotency_key", "jobs")
    op.drop_table("jobs")
    op.drop_table("artifacts")
    op.drop_table("plan_models")
    op.drop_table("models")
    op.drop_table("api_keys")
    op.drop_table("tenants")
    op.drop_table("plans")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS webhook_delivery_status")
    op.execute("DROP TYPE IF EXISTS webhook_endpoint_status")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS artifact_kind")
    op.execute("DROP TYPE IF EXISTS model_status")
    op.execute("DROP TYPE IF EXISTS model_backend")
    op.execute("DROP TYPE IF EXISTS api_key_status")
    op.execute("DROP TYPE IF EXISTS tenant_status")
