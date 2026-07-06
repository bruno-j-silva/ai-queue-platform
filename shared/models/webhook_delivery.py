import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base


class WebhookDeliveryStatus(str, enum.Enum):
    pending = "pending"
    delivering = "delivering"
    delivered = "delivered"
    dead = "dead"


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhook_endpoints.id"), nullable=False
    )
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        Enum(WebhookDeliveryStatus, name="webhook_delivery_status"),
        nullable=False,
        default=WebhookDeliveryStatus.pending,
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)

    job: Mapped["Job"] = relationship("Job", back_populates="webhook_deliveries")
    endpoint: Mapped["WebhookEndpoint"] = relationship(
        "WebhookEndpoint", back_populates="deliveries"
    )
