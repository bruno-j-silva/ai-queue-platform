import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base


class ApiKeyStatus(str, enum.Enum):
    active = "active"
    revoked = "revoked"


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    key_hash: Mapped[str] = mapped_column(String, nullable=False)
    prefix: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status: Mapped[ApiKeyStatus] = mapped_column(
        Enum(ApiKeyStatus, name="api_key_status"), nullable=False, default=ApiKeyStatus.active
    )
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="api_keys")
