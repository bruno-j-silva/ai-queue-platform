import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base

if TYPE_CHECKING:
    from shared.models.model_catalog import ModelCatalog
    from shared.models.plan import Plan


class PlanModel(Base):
    __tablename__ = "plan_models"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id"), primary_key=True
    )
    model_id: Mapped[str] = mapped_column(String, ForeignKey("models.id"), primary_key=True)

    plan: Mapped["Plan"] = relationship("Plan", back_populates="plan_models")
    model: Mapped["ModelCatalog"] = relationship("ModelCatalog", back_populates="plan_models")
