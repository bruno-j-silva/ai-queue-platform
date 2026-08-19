from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base

if TYPE_CHECKING:
    from shared.models.job import Job
    from shared.models.plan_model import PlanModel


class ModelBackend(StrEnum):
    ollama = "ollama"
    vllm = "vllm"


class ModelStatus(StrEnum):
    active = "active"
    disabled = "disabled"


class ModelCatalog(Base):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    backend: Mapped[ModelBackend] = mapped_column(
        Enum(ModelBackend, name="model_backend"), nullable=False
    )
    backend_model_name: Mapped[str] = mapped_column(String, nullable=False)
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    pool: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[ModelStatus] = mapped_column(
        Enum(ModelStatus, name="model_status"), nullable=False, default=ModelStatus.active
    )

    plan_models: Mapped[list["PlanModel"]] = relationship("PlanModel", back_populates="model")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="model")
