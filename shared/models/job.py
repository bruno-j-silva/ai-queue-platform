import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    expired = "expired"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_jobs_tenant_idempotency_key"),
        Index("ix_jobs_tenant_id_queued_at", "tenant_id", "queued_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    model_id: Mapped[str] = mapped_column(String, ForeignKey("models.id"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), nullable=False, default=JobStatus.queued
    )
    priority_weight: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_inline: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="jobs")
    model: Mapped["ModelCatalog"] = relationship("ModelCatalog", back_populates="jobs")
    job_events: Mapped[list["JobEvent"]] = relationship("JobEvent", back_populates="job")
    webhook_deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        "WebhookDelivery", back_populates="job"
    )
