from datetime import datetime

from sqlalchemy import BigInteger, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db.base import Base
from shared.models.job import JobStatus


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    from_status: Mapped[JobStatus | None] = mapped_column(
        Enum(JobStatus, name="job_status"), nullable=True
    )
    to_status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), nullable=False
    )
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    job: Mapped["Job"] = relationship("Job", back_populates="job_events")
