"""
JobRepository — sole access layer for the `jobs` table.

Invariant I5: EVERY read method MUST filter by tenant_id.
              No fallback. No default. Missing tenant_id raises TypeError.

Transaction contract: create() calls session.add() but does NOT commit.
                      The caller (service / unit-of-work) owns the transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from shared.models.job import Job, JobStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class JobRepository:
    """Repository for the `jobs` table. All reads enforce tenant_id (I5)."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        model_id: str,
        payload: dict[str, Any],
        timeout_seconds: int,
        priority_weight: int,
        idempotency_key: str | None = None,
        webhook_endpoint_id: uuid.UUID | None = None,
    ) -> Job:
        """
        Creates a Job in 'queued' status and adds it to the session.
        Does NOT commit — caller controls the transaction boundary.
        """
        job = Job(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            model_id=model_id,
            status=JobStatus.queued,
            payload=payload,
            timeout_seconds=timeout_seconds,
            priority_weight=priority_weight,
            idempotency_key=idempotency_key,
            webhook_endpoint_id=webhook_endpoint_id,
            queued_at=datetime.now(UTC),
            cancel_requested=False,
            attempt=0,
        )
        self._db.add(job)
        return job

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, job_id: uuid.UUID, tenant_id: uuid.UUID) -> Job | None:
        """
        Returns the Job identified by job_id that belongs to tenant_id.
        Returns None if not found OR if the job belongs to a different tenant (I5).
        """
        stmt = select(Job).where(Job.id == job_id, Job.tenant_id == tenant_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        *,
        status: str | None = None,
        created_after: datetime | None = None,
        cursor: uuid.UUID | None = None,
        limit: int = 20,
    ) -> list[Job]:
        """
        Returns jobs for tenant_id ordered by queued_at ascending.
        Optionally filters by status and supports cursor-based pagination.
        ALWAYS filters by tenant_id (I5).
        """
        stmt = select(Job).where(Job.tenant_id == tenant_id)

        if status is not None:
            stmt = stmt.where(Job.status == JobStatus(status))

        if created_after is not None:
            stmt = stmt.where(Job.queued_at > created_after)

        if cursor is not None:
            # cursor is a job_id; fetch jobs with queued_at > cursor job's queued_at
            subq = select(Job.queued_at).where(Job.id == cursor, Job.tenant_id == tenant_id)
            stmt = stmt.where(Job.queued_at > subq.scalar_subquery())

        stmt = stmt.order_by(Job.queued_at.asc()).limit(limit)

        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_queue_position(self, job_id: uuid.UUID, tenant_id: uuid.UUID) -> int | None:
        """
        Returns the estimated queue position of a job:
        COUNT of all queued jobs (across all tenants) with queued_at strictly
        less than the target job's queued_at.

        Returns None if the job does not exist for this tenant or is not in queued status.
        ALWAYS filters by tenant_id on the target job lookup (I5).
        """
        # 1. Fetch the target job — enforcing tenant_id filter (I5)
        job_stmt = select(Job.queued_at, Job.status).where(
            Job.id == job_id,
            Job.tenant_id == tenant_id,
        )
        job_result = await self._db.execute(job_stmt)
        row = job_result.one_or_none()

        if row is None:
            return None

        job_queued_at, job_status = row

        if job_status != JobStatus.queued:
            return None

        # DESIGN: A posição na fila é calculada globalmente (cross-tenant) porque a fila
        # de inferência é compartilhada. Isso pode indiretamente revelar o volume de jobs
        # de outros tenants, mas não revela seu conteúdo. Decisão consciente de produto.
        # 2. Count queued jobs enqueued strictly before this one
        count_stmt = select(func.count()).where(
            Job.status == JobStatus.queued,
            Job.queued_at < job_queued_at,
        )
        count_result = await self._db.execute(count_stmt)
        position: int = count_result.scalar_one()
        return position

    async def find_by_idempotency_key(
        self,
        tenant_id: uuid.UUID,
        idempotency_key: str,
    ) -> Job | None:
        """
        Returns an existing Job matching (tenant_id, idempotency_key), or None.
        ALWAYS filters by tenant_id (I5).
        """
        stmt = select(Job).where(
            Job.tenant_id == tenant_id,
            Job.idempotency_key == idempotency_key,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
