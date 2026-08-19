import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base
from shared.models.job import JobStatus

if TYPE_CHECKING:
    from shared.models.job import Job

_job_status_type = Enum(JobStatus, name="job_status", create_type=False)


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )
    from_status: Mapped[JobStatus | None] = mapped_column(_job_status_type, nullable=True)
    to_status: Mapped[JobStatus] = mapped_column(_job_status_type, nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    job: Mapped["Job"] = relationship("Job", back_populates="job_events")
