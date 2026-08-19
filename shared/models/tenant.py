import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base

if TYPE_CHECKING:
    from shared.models.api_key import ApiKey
    from shared.models.artifact import Artifact
    from shared.models.job import Job
    from shared.models.plan import Plan
    from shared.models.webhook_endpoint import WebhookEndpoint


class TenantStatus(StrEnum):
    active = "active"
    suspended = "suspended"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False
    )
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status"), nullable=False, default=TenantStatus.active
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)

    plan: Mapped["Plan"] = relationship("Plan", back_populates="tenants")
    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="tenant")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="tenant")
    artifacts: Mapped[list["Artifact"]] = relationship("Artifact", back_populates="tenant")
    webhook_endpoints: Mapped[list["WebhookEndpoint"]] = relationship(
        "WebhookEndpoint", back_populates="tenant"
    )
