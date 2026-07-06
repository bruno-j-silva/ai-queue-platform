import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base


class ArtifactKind(str, enum.Enum):
    input = "input"
    output = "output"


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    kind: Mapped[ArtifactKind] = mapped_column(
        Enum(ArtifactKind, name="artifact_kind"), nullable=False
    )
    media_type: Mapped[str | None] = mapped_column(String, nullable=True)
    storage_key: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="artifacts")
