import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base

if TYPE_CHECKING:
    from shared.models.tenant import Tenant
    from shared.models.webhook_delivery import WebhookDelivery


class WebhookEndpointStatus(StrEnum):
    active = "active"
    disabled = "disabled"


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    url: Mapped[str] = mapped_column(String, nullable=False)
    secret_hash: Mapped[str] = mapped_column(String, nullable=False)
    secret_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[WebhookEndpointStatus] = mapped_column(
        Enum(WebhookEndpointStatus, name="webhook_endpoint_status"),
        nullable=False,
        default=WebhookEndpointStatus.active,
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="webhook_endpoints")
    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        "WebhookDelivery", back_populates="endpoint"
    )
