import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base

if TYPE_CHECKING:
    from shared.models.plan_model import PlanModel
    from shared.models.tenant import Tenant


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    priority_weight: Mapped[int] = mapped_column(Integer, nullable=False)
    max_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    result_ttl_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    max_payload_mb: Mapped[int] = mapped_column(Integer, nullable=False)

    tenants: Mapped[list["Tenant"]] = relationship("Tenant", back_populates="plan")
    plan_models: Mapped[list["PlanModel"]] = relationship("PlanModel", back_populates="plan")
