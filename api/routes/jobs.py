"""Job endpoints — submission and retrieval (SPEC-001)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import problem_response
from shared.auth.api_key import TenantIdentity
from shared.auth.dependencies import (
    _get_db,  # shared placeholder, overridden in tests/app
    get_current_tenant,
)
from shared.models.job import Job, JobStatus
from shared.models.job_event import JobEvent
from shared.models.model_catalog import ModelCatalog, ModelStatus
from shared.models.outbox import Outbox
from shared.models.plan import Plan
from shared.models.plan_model import PlanModel
from shared.models.tenant import Tenant, TenantStatus
from shared.repositories.job_repository import JobRepository

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class JobMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str | list[dict[str, Any]]


class JobInput(BaseModel):
    messages: list[JobMessage] = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class JobSubmitRequest(BaseModel):
    model: str
    input: JobInput
    timeout_seconds: int = Field(gt=0)
    webhook_endpoint_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobSubmitResponse(BaseModel):
    job_id: str
    status: str
    created_at: str  # ISO 8601
    links: dict[str, str]


class JobDetailResponse(BaseModel):
    job_id: str
    status: str
    queue_position: int | None = None  # present only when status == 'queued'
    result: dict[str, Any] | None
    usage: dict[str, Any] | None
    error: dict[str, Any] | None
    timestamps: dict[str, str | None]
    expires_at: str | None


class JobListResponse(BaseModel):
    items: list[JobDetailResponse]
    next_cursor: str | None  # UUID of the last item for cursor-based pagination


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _fetch_tenant_with_plan(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    """Load Tenant with its Plan eager-loaded in one query."""
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _fetch_plan(db: AsyncSession, plan_id: uuid.UUID) -> Plan | None:
    stmt = select(Plan).where(Plan.id == plan_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _fetch_model(db: AsyncSession, model_id: str) -> ModelCatalog | None:
    stmt = select(ModelCatalog).where(ModelCatalog.id == model_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _model_in_plan(db: AsyncSession, plan_id: uuid.UUID, model_id: str) -> bool:
    stmt = select(PlanModel).where(
        PlanModel.plan_id == plan_id,
        PlanModel.model_id == model_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


def _build_response(job: Job, status_code: int) -> JSONResponse:
    data = JobSubmitResponse(
        job_id=str(job.id),
        status=job.status.value,
        created_at=job.queued_at.isoformat(),
        links={"self": f"/v1/jobs/{job.id}"},
    )
    return JSONResponse(status_code=status_code, content=data.model_dump())


def _create_outbox_entry(job: Job, priority_weight: int) -> Outbox:
    return Outbox(
        topic="inference.dispatch",
        payload={
            "job_id": str(job.id),
            "model_id": job.model_id,
            "tenant_id": str(job.tenant_id),
            "priority_weight": priority_weight,
        },
    )


def _create_job_event(job: Job) -> JobEvent:
    return JobEvent(
        job_id=job.id,
        from_status=None,
        to_status=JobStatus.queued,
        detail=None,
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("", status_code=202)
async def submit_job(
    request: JobSubmitRequest,
    tenant: Annotated[TenantIdentity, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(_get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    """Submit a new inference job.

    1. Idempotency check — same (tenant_id, idempotency_key) returns the original job.
    2. Validate model_id exists in catalog (→ 422 if not).
    3. Validate model_id is allowed by tenant's plan (→ 422 if not).
    4. Validate timeout_seconds ≤ plan.max_timeout_seconds (→ 422 if exceeded).
    5. Create Job + Outbox + JobEvent in a single transaction (invariant I4).
    6. Return 202 with job_id, status, and created_at.
    """
    tenant_id = uuid.UUID(tenant["tenant_id"])
    repo = JobRepository(db)

    # 1. Idempotency check
    if idempotency_key is not None:
        existing = await repo.find_by_idempotency_key(tenant_id, idempotency_key)
        if existing is not None:
            return _build_response(existing, status_code=200)

    # 2. Load tenant + plan
    tenant_row = await _fetch_tenant_with_plan(db, tenant_id)
    if tenant_row is None:
        return problem_response(422, "Tenant Not Found", "Tenant does not exist.")
    if tenant_row.status != TenantStatus.active:
        return problem_response(403, "Tenant Suspended", "Tenant is not active.")

    plan = await _fetch_plan(db, tenant_row.plan_id)
    if plan is None:
        return problem_response(422, "Plan Not Found", "Tenant's plan does not exist.")

    # 3. Validate model in catalog
    model = await _fetch_model(db, request.model)
    if model is None:
        return problem_response(
            422,
            "Model Not Found",
            f"model '{request.model}' does not exist in the model catalog.",
        )
    if model.status != ModelStatus.active:
        return problem_response(422, "Model Disabled", f"model '{request.model}' is disabled.")

    # 4. Validate model in plan
    if not await _model_in_plan(db, plan.id, request.model):
        return problem_response(
            422,
            "Model Not Allowed",
            f"model '{request.model}' is not allowed by the tenant's plan.",
        )

    # 5. Validate timeout cap
    if request.timeout_seconds > plan.max_timeout_seconds:
        return problem_response(
            422,
            "Timeout Exceeds Cap",
            (
                f"timeout_seconds={request.timeout_seconds} exceeds the plan cap of "
                f"{plan.max_timeout_seconds} seconds."
            ),
            max_timeout=plan.max_timeout_seconds,
        )

    payload = request.input.model_dump()
    if request.metadata:
        payload["metadata"] = request.metadata
    payload_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    if payload_bytes > plan.max_payload_mb * 1024 * 1024:
        return problem_response(
            413,
            "Payload Too Large",
            f"Payload exceeds the plan limit of {plan.max_payload_mb} MB.",
        )

    # 6. Create Job + Outbox + JobEvent atomically (invariant I4)
    try:
        async with db.begin_nested():
            job = await repo.create(
                tenant_id=tenant_id,
                model_id=request.model,
                payload=payload,
                timeout_seconds=request.timeout_seconds,
                priority_weight=plan.priority_weight,
                idempotency_key=idempotency_key,
            )

            outbox_entry = _create_outbox_entry(job, plan.priority_weight)
            db.add(outbox_entry)

            job_event = _create_job_event(job)
            db.add(job_event)
    except IntegrityError:
        await db.rollback()
        if idempotency_key is not None:
            existing = await repo.find_by_idempotency_key(tenant_id, idempotency_key)
            if existing is not None:
                return _build_response(existing, status_code=200)
        raise

    return _build_response(job, status_code=202)


# ---------------------------------------------------------------------------
# GET /v1/jobs/{job_id}
# ---------------------------------------------------------------------------


def _job_to_detail(job: Job, queue_position: int | None = None) -> JobDetailResponse:
    """Convert a Job ORM row to a JobDetailResponse."""
    return JobDetailResponse(
        job_id=str(job.id),
        status=job.status.value,
        queue_position=queue_position if job.status == JobStatus.queued else None,
        result={"output": job.result_inline, "artifact_urls": []}
        if job.result_inline is not None
        else None,
        usage=job.usage,
        error=job.error,
        timestamps={
            "queued_at": job.queued_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        },
        expires_at=job.expires_at.isoformat() if job.expires_at else None,
    )


@router.get("/{job_id}")
async def get_job(
    job_id: uuid.UUID,
    tenant: Annotated[TenantIdentity, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(_get_db)],
) -> JSONResponse:
    """Retrieve a single job by ID.

    - Enforces tenant isolation: cross-tenant requests return 404 (AC-06).
    - When status is 'queued', includes estimated queue_position (AC-08).
    """
    tenant_id = uuid.UUID(tenant["tenant_id"])
    repo = JobRepository(db)

    job = await repo.get_by_id(job_id, tenant_id)
    if job is None:
        return _not_found()

    queue_position: int | None = None
    if job.status == JobStatus.queued:
        queue_position = await repo.get_queue_position(job_id, tenant_id)

    detail = _job_to_detail(job, queue_position)
    return JSONResponse(content=detail.model_dump())


# ---------------------------------------------------------------------------
# GET /v1/jobs
# ---------------------------------------------------------------------------


@router.get("", response_model=JobListResponse)
async def list_jobs(
    tenant: Annotated[TenantIdentity, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(_get_db)],
    status: str | None = None,
    created_after: datetime | None = None,
    cursor: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> JobListResponse:
    """List jobs for the authenticated tenant with optional filters and cursor pagination."""
    tenant_id = uuid.UUID(tenant["tenant_id"])
    repo = JobRepository(db)

    jobs = await repo.list_by_tenant(
        tenant_id,
        status=status,
        created_after=created_after,
        cursor=cursor,
        limit=limit,
    )

    items = [_job_to_detail(j) for j in jobs]
    next_cursor = str(jobs[-1].id) if len(jobs) == limit else None

    return JobListResponse(items=items, next_cursor=next_cursor)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _not_found() -> JSONResponse:
    return problem_response(
        404,
        "Job Not Found",
        "The requested job does not exist or belongs to a different tenant.",
    )
