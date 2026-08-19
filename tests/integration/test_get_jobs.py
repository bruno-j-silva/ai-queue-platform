"""
Integration tests for GET /v1/jobs and GET /v1/jobs/{job_id} — SPEC-001 ACs.

TDD RED phase: tests written before implementation. All must fail initially.

Uses:
- httpx.AsyncClient with the FastAPI app
- dependency_overrides to isolate auth and DB
- testcontainers.postgres for a real Postgres instance
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from shared.auth.api_key import TenantIdentity
from shared.auth.dependencies import _get_db, get_current_tenant
from shared.models import (  # noqa: F401 — registers all models in Base.metadata
    Job,
    ModelCatalog,
    Outbox,
    Plan,
    PlanModel,
    Tenant,
)
from shared.models.job import JobStatus
from shared.models.model_catalog import ModelBackend, ModelStatus
from shared.models.tenant import TenantStatus

# ---------------------------------------------------------------------------
# Module-scoped Postgres container + migration
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def postgres_url() -> dict[str, str]:
    """Spin up a real Postgres container once per module."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16") as pg:
        sync_url = pg.get_connection_url().replace("psycopg2", "psycopg")
        if "postgresql+psycopg://" not in sync_url:
            sync_url = sync_url.replace("postgresql://", "postgresql+psycopg://")
        async_url = sync_url
        yield {"sync": sync_url, "async": async_url}


@pytest.fixture(scope="module")
def migrated_db(postgres_url: dict[str, str]) -> dict[str, str]:
    """Run Alembic migrations once for the whole module."""
    original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = postgres_url["sync"]
    try:
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", postgres_url["sync"])
        command.upgrade(cfg, "head")
    finally:
        if original is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original
    return postgres_url


# ---------------------------------------------------------------------------
# Per-test session with rollback
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
async def async_engine(migrated_db: dict[str, str]):
    engine = create_async_engine(migrated_db["async"], echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def async_session(async_engine) -> AsyncIterator[AsyncSession]:
    """Provide a fresh AsyncSession rolled back after each test."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


# ---------------------------------------------------------------------------
# Domain seed fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def seed_plan(async_session: AsyncSession) -> Plan:
    plan = Plan(
        id=uuid.uuid4(),
        name="starter",
        priority_weight=10,
        max_timeout_seconds=300,
        result_ttl_days=7,
        max_payload_mb=10,
    )
    async_session.add(plan)
    await async_session.flush()
    return plan


@pytest.fixture()
async def seed_tenant(async_session: AsyncSession, seed_plan: Plan) -> Tenant:
    now = datetime.now(UTC)
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Tenant A",
        plan_id=seed_plan.id,
        status=TenantStatus.active,
        created_at=now,
        updated_at=now,
    )
    async_session.add(tenant)
    await async_session.flush()
    return tenant


@pytest.fixture()
async def seed_tenant_b(async_session: AsyncSession, seed_plan: Plan) -> Tenant:
    """A second tenant for cross-tenant isolation tests."""
    now = datetime.now(UTC)
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Tenant B",
        plan_id=seed_plan.id,
        status=TenantStatus.active,
        created_at=now,
        updated_at=now,
    )
    async_session.add(tenant)
    await async_session.flush()
    return tenant


@pytest.fixture()
async def seed_model(async_session: AsyncSession) -> ModelCatalog:
    model = ModelCatalog(
        id="test-model",
        backend=ModelBackend.ollama,
        backend_model_name="llama3",
        status=ModelStatus.active,
    )
    async_session.add(model)
    await async_session.flush()
    return model


@pytest.fixture()
async def seed_plan_model(
    async_session: AsyncSession, seed_plan: Plan, seed_model: ModelCatalog
) -> PlanModel:
    pm = PlanModel(plan_id=seed_plan.id, model_id=seed_model.id)
    async_session.add(pm)
    await async_session.flush()
    return pm


async def _create_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    model_id: str,
    status: JobStatus = JobStatus.queued,
) -> Job:
    """Helper to insert a Job directly into the DB for test setup."""
    job = Job(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        model_id=model_id,
        status=status,
        priority_weight=10,
        payload={"prompt": "test"},
        timeout_seconds=30,
        idempotency_key=None,
        cancel_requested=False,
        attempt=0,
        queued_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    return job


# ---------------------------------------------------------------------------
# App client factory with dependency overrides
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_client(
    async_session: AsyncSession,
    seed_tenant: Tenant,
):
    """
    Returns a builder that creates an AsyncClient with:
    - DB overridden to async_session
    - auth overridden to inject a fake TenantIdentity
    """
    from api.main import app

    async def _get_db_override() -> AsyncIterator[AsyncSession]:
        yield async_session

    def _build(tenant_id: uuid.UUID | None = None, authenticated: bool = True) -> AsyncClient:
        real_tenant_id = tenant_id or seed_tenant.id

        async def _auth_override() -> TenantIdentity:
            if not authenticated:
                from fastapi import HTTPException

                raise HTTPException(status_code=401, detail="Invalid or revoked API key.")
            return TenantIdentity(
                tenant_id=str(real_tenant_id),
                api_key_id=str(uuid.uuid4()),
            )

        overrides: dict[Any, Any] = {
            _get_db: _get_db_override,
            get_current_tenant: _auth_override,
        }
        app.dependency_overrides = overrides
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield _build
    app.dependency_overrides = {}


# ---------------------------------------------------------------------------
# AC-06: cross-tenant isolation — tenant A cannot see tenant B's jobs
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_spec001_ac06_cross_tenant_404(
    make_client,
    async_session: AsyncSession,
    seed_tenant: Tenant,
    seed_tenant_b: Tenant,
    seed_model: ModelCatalog,
    seed_plan_model: PlanModel,
) -> None:
    """Tenant A querying job owned by Tenant B → 404 (no cross-tenant leak)."""
    # Create a job belonging to Tenant B
    job_b = await _create_job(async_session, seed_tenant_b.id, seed_model.id)

    # Query it as Tenant A — must get 404, not 200 or 403
    async with make_client(tenant_id=seed_tenant.id) as client:
        response = await client.get(f"/v1/jobs/{job_b.id}")

    assert response.status_code == 404, response.text
    assert response.headers["content-type"].startswith("application/problem+json")


# ---------------------------------------------------------------------------
# AC-08: queue_position returned when job is queued
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_spec001_ac08_queue_position_estimate(
    make_client,
    async_session: AsyncSession,
    seed_tenant: Tenant,
    seed_model: ModelCatalog,
    seed_plan_model: PlanModel,
) -> None:
    """Job with status='queued' must include queue_position ≥ 0 in response."""
    job = await _create_job(async_session, seed_tenant.id, seed_model.id, JobStatus.queued)

    async with make_client(tenant_id=seed_tenant.id) as client:
        response = await client.get(f"/v1/jobs/{job.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert "queue_position" in body
    assert body["queue_position"] is not None
    assert body["queue_position"] >= 0


# ---------------------------------------------------------------------------
# Basic 200: tenant can fetch own job
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_get_job_returns_200_for_own_job(
    make_client,
    async_session: AsyncSession,
    seed_tenant: Tenant,
    seed_model: ModelCatalog,
    seed_plan_model: PlanModel,
) -> None:
    """Tenant fetches their own job → 200 with correct fields."""
    job = await _create_job(async_session, seed_tenant.id, seed_model.id)

    async with make_client(tenant_id=seed_tenant.id) as client:
        response = await client.get(f"/v1/jobs/{job.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] == str(job.id)
    assert body["status"] == job.status.value
    assert body["result"] is None
    assert body["usage"] is None
    assert body["error"] is None
    assert body["timestamps"]["queued_at"] == job.queued_at.isoformat()


# ---------------------------------------------------------------------------
# queue_position is None for non-queued jobs
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_get_job_no_queue_position_when_not_queued(
    make_client,
    async_session: AsyncSession,
    seed_tenant: Tenant,
    seed_model: ModelCatalog,
    seed_plan_model: PlanModel,
) -> None:
    """Job that is not 'queued' must NOT include queue_position (it should be None)."""
    job = await _create_job(async_session, seed_tenant.id, seed_model.id, JobStatus.running)

    async with make_client(tenant_id=seed_tenant.id) as client:
        response = await client.get(f"/v1/jobs/{job.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["queue_position"] is None


# ---------------------------------------------------------------------------
# GET /v1/jobs — list with status filter
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_list_jobs_filters_by_status(
    make_client,
    async_session: AsyncSession,
    seed_tenant: Tenant,
    seed_model: ModelCatalog,
    seed_plan_model: PlanModel,
) -> None:
    """GET /v1/jobs?status=queued returns only queued jobs for this tenant."""
    await _create_job(async_session, seed_tenant.id, seed_model.id, JobStatus.queued)
    await _create_job(async_session, seed_tenant.id, seed_model.id, JobStatus.queued)
    await _create_job(async_session, seed_tenant.id, seed_model.id, JobStatus.running)

    async with make_client(tenant_id=seed_tenant.id) as client:
        response = await client.get("/v1/jobs", params={"status": "queued"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert "items" in body
    items = body["items"]
    assert len(items) >= 2
    assert all(item["status"] == "queued" for item in items)


# ---------------------------------------------------------------------------
# GET /v1/jobs — cursor-based pagination
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_list_jobs_cursor_pagination(
    make_client,
    async_session: AsyncSession,
    seed_tenant: Tenant,
    seed_model: ModelCatalog,
    seed_plan_model: PlanModel,
) -> None:
    """next_cursor from first page can be used to fetch second page."""
    # Create 3 jobs so we can paginate with limit=2
    await _create_job(async_session, seed_tenant.id, seed_model.id)
    await _create_job(async_session, seed_tenant.id, seed_model.id)
    await _create_job(async_session, seed_tenant.id, seed_model.id)

    async with make_client(tenant_id=seed_tenant.id) as client:
        # First page: limit=2
        page1 = await client.get("/v1/jobs", params={"limit": 2})
        assert page1.status_code == 200, page1.text
        body1 = page1.json()
        assert len(body1["items"]) == 2
        next_cursor = body1.get("next_cursor")
        assert next_cursor is not None, "Expected next_cursor for more results"

        # Second page using cursor
        page2 = await client.get("/v1/jobs", params={"cursor": next_cursor, "limit": 2})
        assert page2.status_code == 200, page2.text
        body2 = page2.json()
        assert len(body2["items"]) >= 1

        # No overlap between pages
        ids_page1 = {item["job_id"] for item in body1["items"]}
        ids_page2 = {item["job_id"] for item in body2["items"]}
        assert ids_page1.isdisjoint(ids_page2), "Pages must not overlap"
