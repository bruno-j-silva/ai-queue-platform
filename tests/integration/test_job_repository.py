"""
Integration tests for JobRepository.
TDD RED phase — these tests define the expected behaviour before implementation.
All reads MUST enforce tenant_id filtering (invariant I5).
"""

import os
import uuid
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from shared.models import (  # noqa: F401 — registers all models in Base.metadata
    Job,
    ModelCatalog,
    Plan,
    Tenant,
)
from shared.models.model_catalog import ModelBackend, ModelStatus
from shared.models.tenant import TenantStatus
from shared.repositories.job_repository import JobRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def postgres_url():
    """Spin up a real Postgres container once per module."""
    with PostgresContainer("postgres:16") as pg:
        # testcontainers returns a psycopg2 URL; swap driver to psycopg (v3)
        sync_url = pg.get_connection_url().replace("psycopg2", "psycopg")
        # Ensure the URL starts with the correct async-capable driver prefix
        if "postgresql+psycopg://" in sync_url:
            async_url = sync_url
        else:
            async_url = sync_url.replace("postgresql://", "postgresql+psycopg://")
        yield {"sync": sync_url, "async": async_url}


@pytest.fixture(scope="module")
def migrated_db(postgres_url):
    """
    Run alembic migrations once for the whole module.
    Temporarily sets DATABASE_URL so alembic env.py (which reads that env var)
    uses the testcontainer URL instead of any real database.
    """
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


@pytest.fixture(scope="module")
async def async_engine(migrated_db):
    """Create a single engine for the whole module."""
    engine = create_async_engine(migrated_db["async"], echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def async_session(async_engine):
    """Provide a fresh AsyncSession that is rolled back after each test."""
    async_session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest.fixture()
async def seed_data(async_session: AsyncSession):
    """
    Inserts minimal prerequisite rows (Plan, Tenant, ModelCatalog) and
    returns them so tests can reference their IDs.
    """
    now = datetime.now(UTC)

    plan = Plan(
        id=uuid.uuid4(),
        name="starter",
        priority_weight=1,
        max_timeout_seconds=300,
        result_ttl_days=7,
        max_payload_mb=10,
    )
    tenant_a = Tenant(
        id=uuid.uuid4(),
        name="Tenant A",
        plan_id=plan.id,
        status=TenantStatus.active,
        created_at=now,
        updated_at=now,
    )
    tenant_b = Tenant(
        id=uuid.uuid4(),
        name="Tenant B",
        plan_id=plan.id,
        status=TenantStatus.active,
        created_at=now,
        updated_at=now,
    )
    model = ModelCatalog(
        id="gpt-test",
        backend=ModelBackend.ollama,
        backend_model_name="llama3",
        status=ModelStatus.active,
    )

    async_session.add_all([plan, tenant_a, tenant_b, model])
    await async_session.flush()

    return {"plan": plan, "tenant_a": tenant_a, "tenant_b": tenant_b, "model": model}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_create_job_persists_in_queued_status(
    async_session: AsyncSession, seed_data: dict
) -> None:
    """
    JobRepository.create() must persist a Job with status='queued'
    and the supplied field values without committing the transaction.
    """
    repo = JobRepository(async_session)
    tenant = seed_data["tenant_a"]
    model = seed_data["model"]

    job = await repo.create(
        tenant_id=tenant.id,
        model_id=model.id,
        payload={"prompt": "hello"},
        timeout_seconds=60,
        priority_weight=5,
    )

    # Verify the returned object before any commit
    assert job.id is not None
    assert job.tenant_id == tenant.id
    assert job.model_id == model.id
    assert job.status.value == "queued"
    assert job.payload == {"prompt": "hello"}
    assert job.timeout_seconds == 60
    assert job.priority_weight == 5
    assert job.queued_at is not None
    assert job.idempotency_key is None


@pytest.mark.integration
async def test_get_by_id_returns_job_for_correct_tenant(
    async_session: AsyncSession, seed_data: dict
) -> None:
    """
    get_by_id() must return the Job when tenant_id matches.
    """
    repo = JobRepository(async_session)
    tenant = seed_data["tenant_a"]
    model = seed_data["model"]

    created = await repo.create(
        tenant_id=tenant.id,
        model_id=model.id,
        payload={"prompt": "test"},
        timeout_seconds=30,
        priority_weight=1,
    )
    await async_session.flush()

    found = await repo.get_by_id(created.id, tenant.id)

    assert found is not None
    assert found.id == created.id
    assert found.tenant_id == tenant.id


@pytest.mark.integration
async def test_get_by_id_returns_none_for_wrong_tenant(
    async_session: AsyncSession, seed_data: dict
) -> None:
    """
    I5 — tenant isolation: get_by_id() must return None when tenant_id
    does NOT match the job's actual tenant, even if the job_id exists.
    """
    repo = JobRepository(async_session)
    tenant_a = seed_data["tenant_a"]
    tenant_b = seed_data["tenant_b"]
    model = seed_data["model"]

    created = await repo.create(
        tenant_id=tenant_a.id,
        model_id=model.id,
        payload={"prompt": "secret"},
        timeout_seconds=30,
        priority_weight=1,
    )
    await async_session.flush()

    # Querying with a DIFFERENT tenant_id must return None
    result = await repo.get_by_id(created.id, tenant_b.id)

    assert result is None, (
        "I5 violated: get_by_id returned a job that belongs to a different tenant"
    )


@pytest.mark.integration
async def test_list_by_tenant_filters_by_status(
    async_session: AsyncSession, seed_data: dict
) -> None:
    """
    list_by_tenant() with status='queued' must return only the queued jobs
    that belong to tenant_a, not those of tenant_b.
    """
    repo = JobRepository(async_session)
    tenant_a = seed_data["tenant_a"]
    tenant_b = seed_data["tenant_b"]
    model = seed_data["model"]

    # Two jobs for tenant_a
    await repo.create(
        tenant_id=tenant_a.id,
        model_id=model.id,
        payload={"n": 1},
        timeout_seconds=30,
        priority_weight=1,
    )
    await repo.create(
        tenant_id=tenant_a.id,
        model_id=model.id,
        payload={"n": 2},
        timeout_seconds=30,
        priority_weight=1,
    )
    # One job for tenant_b — must NOT appear in tenant_a's list
    await repo.create(
        tenant_id=tenant_b.id,
        model_id=model.id,
        payload={"n": 3},
        timeout_seconds=30,
        priority_weight=1,
    )
    await async_session.flush()

    results = await repo.list_by_tenant(tenant_a.id, status="queued")

    assert len(results) >= 2
    assert all(j.tenant_id == tenant_a.id for j in results)
    assert all(j.status.value == "queued" for j in results)


@pytest.mark.integration
async def test_get_queue_position_returns_position(
    async_session: AsyncSession, seed_data: dict
) -> None:
    """
    get_queue_position() must return the count of queued jobs enqueued
    strictly before the given job (i.e., 0-based position).
    A job enqueued first should have a lower position than one enqueued later.
    """
    repo = JobRepository(async_session)
    tenant = seed_data["tenant_a"]
    model = seed_data["model"]

    first = await repo.create(
        tenant_id=tenant.id,
        model_id=model.id,
        payload={"order": "first"},
        timeout_seconds=30,
        priority_weight=1,
    )
    await async_session.flush()

    second = await repo.create(
        tenant_id=tenant.id,
        model_id=model.id,
        payload={"order": "second"},
        timeout_seconds=30,
        priority_weight=1,
    )
    await async_session.flush()

    pos_first = await repo.get_queue_position(first.id, tenant.id)
    pos_second = await repo.get_queue_position(second.id, tenant.id)

    assert pos_first is not None
    assert pos_second is not None
    assert pos_first < pos_second, (
        f"Expected first job position ({pos_first}) < second job position ({pos_second})"
    )


@pytest.mark.integration
async def test_find_by_idempotency_key_returns_existing_job(
    async_session: AsyncSession, seed_data: dict
) -> None:
    """
    find_by_idempotency_key() must return the existing Job when the
    (tenant_id, idempotency_key) pair matches, and None otherwise.
    """
    repo = JobRepository(async_session)
    tenant_a = seed_data["tenant_a"]
    tenant_b = seed_data["tenant_b"]
    model = seed_data["model"]
    key = "idem-key-abc123"

    created = await repo.create(
        tenant_id=tenant_a.id,
        model_id=model.id,
        payload={"prompt": "idempotent"},
        timeout_seconds=30,
        priority_weight=1,
        idempotency_key=key,
    )
    await async_session.flush()

    # Same tenant + same key => must find it
    found = await repo.find_by_idempotency_key(tenant_a.id, key)
    assert found is not None
    assert found.id == created.id
    assert found.idempotency_key == key

    # Different tenant + same key => must return None (I5)
    not_found = await repo.find_by_idempotency_key(tenant_b.id, key)
    assert not_found is None, "I5 violated: find_by_idempotency_key leaked job to wrong tenant"

    # Same tenant + unknown key => must return None
    missing = await repo.find_by_idempotency_key(tenant_a.id, "nonexistent-key")
    assert missing is None
