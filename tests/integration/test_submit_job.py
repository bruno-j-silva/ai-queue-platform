"""
Integration tests for POST /v1/jobs — SPEC-001 Acceptance Criteria.

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

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
from shared.models.model_catalog import ModelBackend, ModelStatus
from shared.models.tenant import TenantStatus
from shared.models.webhook_delivery import WebhookDelivery, WebhookDeliveryStatus
from shared.models.webhook_endpoint import WebhookEndpoint, WebhookEndpointStatus

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
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


# ---------------------------------------------------------------------------
# Domain seed fixtures (no hardcoding of IDs)
# ---------------------------------------------------------------------------


@pytest.fixture()
async def seed_plan(async_session: AsyncSession) -> Plan:
    """Insert a Plan that allows model 'test-model' with max_timeout=300."""
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
    """Insert an active Tenant linked to seed_plan."""
    now = datetime.now(UTC)
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Test Tenant",
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
    """Insert a ModelCatalog entry."""
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
    """Link model to plan."""
    pm = PlanModel(plan_id=seed_plan.id, model_id=seed_model.id)
    async_session.add(pm)
    await async_session.flush()
    return pm


# ---------------------------------------------------------------------------
# App client factory with dependency overrides
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_client(
    async_session: AsyncSession,
    seed_tenant: Tenant,
):
    """
    Returns a context-manager factory that builds an AsyncClient with:
    - DB overridden to async_session
    - auth overridden to inject a fake TenantIdentity
    """
    from api.main import app  # imported here so DATABASE_URL is already set

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

        overrides = {_get_db: _get_db_override}
        if authenticated:
            overrides[get_current_tenant] = _auth_override  # type: ignore[assignment]
        else:
            overrides[get_current_tenant] = _auth_override  # type: ignore[assignment]

        app.dependency_overrides = overrides
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return _build


# ---------------------------------------------------------------------------
# AC-01: valid submission → 202, job persisted, outbox created in same tx
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_spec001_ac01_valid_submit_returns_202_and_persists(
    make_client,
    seed_tenant: Tenant,
    seed_model: ModelCatalog,
    seed_plan_model: PlanModel,
    async_session: AsyncSession,
) -> None:
    """Valid payload → 202, job status='queued', outbox entry created atomically."""
    from sqlalchemy import select

    async with make_client() as client:
        response = await client.post(
            "/v1/jobs",
            json={
                "model": seed_model.id,
                "input": {"messages": [{"role": "user", "content": "Hello"}]},
                "timeout_seconds": 30,
            },
        )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert "job_id" in body
    assert "created_at" in body

    # Verify job persisted in DB
    job_id = uuid.UUID(body["job_id"])
    result = await async_session.execute(
        select(Job).where(Job.id == job_id, Job.tenant_id == seed_tenant.id)
    )
    job = result.scalar_one_or_none()
    assert job is not None
    assert job.status.value == "queued"

    # Verify outbox entry created in same transaction
    outbox_result = await async_session.execute(
        select(Outbox).where(Outbox.topic == "inference.dispatch")
    )
    outbox_entries = outbox_result.scalars().all()
    assert len(outbox_entries) >= 1
    matching = [e for e in outbox_entries if e.payload.get("job_id") == str(job_id)]
    assert len(matching) == 1
    assert matching[0].payload["model_id"] == seed_model.id
    assert matching[0].payload["tenant_id"] == str(seed_tenant.id)


# ---------------------------------------------------------------------------
# AC-03a: invalid model_id → 422 with problem+json
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_spec001_ac03_invalid_model_422(
    make_client,
    seed_plan_model: PlanModel,
) -> None:
    """model_id not in catalog → 422 problem+json with title about model."""
    async with make_client() as client:
        response = await client.post(
            "/v1/jobs",
            json={
                "model": "nonexistent-model",
                "input": {"messages": [{"role": "user", "content": "Hello"}]},
                "timeout_seconds": 30,
            },
        )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert "model" in body.get("detail", "").lower() or "model" in body.get("title", "").lower()


# ---------------------------------------------------------------------------
# AC-03b: model not in tenant's plan → 422
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_spec001_ac03_model_not_in_plan_422(
    make_client,
    async_session: AsyncSession,
    seed_plan: Plan,
    seed_model: ModelCatalog,
) -> None:
    """model_id exists in catalog but NOT in tenant's plan → 422."""
    # Intentionally do NOT create seed_plan_model so model is not linked to plan
    async with make_client() as client:
        response = await client.post(
            "/v1/jobs",
            json={
                "model": seed_model.id,
                "input": {"messages": [{"role": "user", "content": "Hello"}]},
                "timeout_seconds": 30,
            },
        )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert "plan" in body.get("detail", "").lower() or "model" in body.get("detail", "").lower()


# ---------------------------------------------------------------------------
# AC-04: no/invalid auth token → 401
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_spec001_ac04_invalid_key_401(
    make_client,
    seed_model: ModelCatalog,
    seed_plan_model: PlanModel,
) -> None:
    """Missing/invalid Bearer token → 401."""
    async with make_client(authenticated=False) as client:
        response = await client.post(
            "/v1/jobs",
            json={
                "model": seed_model.id,
                "input": {"messages": [{"role": "user", "content": "Hello"}]},
                "timeout_seconds": 30,
            },
        )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# AC-05: idempotency — repeated key returns original job
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_spec001_ac05_idempotency_returns_original(
    make_client,
    seed_model: ModelCatalog,
    seed_plan_model: PlanModel,
    async_session: AsyncSession,
    seed_tenant: Tenant,
) -> None:
    """Same (tenant_id, idempotency_key) twice → second call returns original job, no duplicate."""
    from sqlalchemy import select

    idem_key = f"idem-{uuid.uuid4()}"
    payload = {
        "model": seed_model.id,
        "input": {"messages": [{"role": "user", "content": "idempotent"}]},
        "timeout_seconds": 30,
    }

    async with make_client() as client:
        headers = {"Idempotency-Key": idem_key}
        first_response = await client.post("/v1/jobs", json=payload, headers=headers)
        second_response = await client.post("/v1/jobs", json=payload, headers=headers)

    assert first_response.status_code == 202
    assert second_response.status_code == 200

    first_body = first_response.json()
    second_body = second_response.json()

    # Both must return the same job_id
    assert first_body["job_id"] == second_body["job_id"]

    # Only one job must exist in DB with this idempotency_key
    result = await async_session.execute(
        select(Job).where(
            Job.tenant_id == seed_tenant.id,
            Job.idempotency_key == idem_key,
        )
    )
    jobs = result.scalars().all()
    assert len(jobs) == 1


# ---------------------------------------------------------------------------
# AC-07: timeout exceeds plan cap → 422 with max_timeout in detail
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_spec001_ac07_timeout_above_plan_cap_422(
    make_client,
    seed_model: ModelCatalog,
    seed_plan_model: PlanModel,
    seed_plan: Plan,
) -> None:
    """timeout_seconds > plan.max_timeout_seconds → 422 with max_timeout in body."""
    over_limit = seed_plan.max_timeout_seconds + 1

    async with make_client() as client:
        response = await client.post(
            "/v1/jobs",
            json={
                "model": seed_model.id,
                "input": {"messages": [{"role": "user", "content": "Hello"}]},
                "timeout_seconds": over_limit,
            },
        )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    # detail must mention the cap value
    detail = body.get("detail", "")
    assert str(seed_plan.max_timeout_seconds) in detail or "timeout" in detail.lower()


@pytest.mark.integration
async def test_spec003_submission_persists_owned_webhook_endpoint(
    make_client,
    async_session: AsyncSession,
    seed_tenant: Tenant,
    seed_model: ModelCatalog,
    seed_plan_model: PlanModel,
) -> None:
    endpoint = WebhookEndpoint(
        id=uuid.uuid4(),
        tenant_id=seed_tenant.id,
        url="https://8.8.8.8/callback",
        secret_hash="hash",
        secret_encrypted="encrypted",
        status=WebhookEndpointStatus.active,
    )
    async_session.add(endpoint)
    await async_session.flush()

    async with make_client() as client:
        response = await client.post(
            "/v1/jobs",
            json={
                "model": seed_model.id,
                "input": {"messages": [{"role": "user", "content": "Hello"}]},
                "timeout_seconds": 30,
                "webhook_endpoint_id": str(endpoint.id),
            },
        )

    assert response.status_code == 202, response.text
    job = await async_session.get(Job, uuid.UUID(response.json()["job_id"]))
    assert job is not None
    assert job.webhook_endpoint_id == endpoint.id


@pytest.mark.integration
async def test_webhook_endpoint_create_list_delete_hides_secret(
    make_client,
    seed_tenant: Tenant,
) -> None:
    async with make_client() as client:
        created = await client.post(
            "/v1/webhook-endpoints",
            json={"url": "https://8.8.8.8/callback"},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["secret"].startswith("whsec_")

        listed = await client.get("/v1/webhook-endpoints")
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == body["id"]
        assert "secret" not in listed.json()[0]
        assert "secret_hash" not in listed.json()[0]
        assert "secret_encrypted" not in listed.json()[0]

        deleted = await client.delete(f"/v1/webhook-endpoints/{body['id']}")
        assert deleted.status_code == 204


@pytest.mark.integration
async def test_webhook_endpoint_test_creates_delivery(
    make_client,
    async_session: AsyncSession,
) -> None:
    from sqlalchemy import select

    from shared.models.outbox import Outbox

    async with make_client() as client:
        created = await client.post(
            "/v1/webhook-endpoints",
            json={"url": "https://8.8.8.8/callback"},
        )
        endpoint_id = created.json()["id"]
        response = await client.post(f"/v1/webhook-endpoints/{endpoint_id}/test")

    assert response.status_code == 202, response.text
    delivery_id = uuid.UUID(response.json()["delivery_id"])
    delivery = await async_session.get(WebhookDelivery, delivery_id)
    assert delivery is not None
    assert delivery.event == "webhook.test"
    outbox = (
        await async_session.execute(
            select(Outbox).where(
                Outbox.topic == "webhooks.delivery",
                Outbox.payload["delivery_id"].astext == str(delivery_id),
            )
        )
    ).scalar_one()
    assert outbox.payload["expected_attempt"] == 1


@pytest.mark.integration
async def test_spec003_ac06_admin_redeliver_from_dlq(
    make_client,
    async_session: AsyncSession,
    seed_tenant: Tenant,
) -> None:
    from sqlalchemy import select

    from shared.models.outbox import Outbox

    endpoint = WebhookEndpoint(
        id=uuid.uuid4(),
        tenant_id=seed_tenant.id,
        url="https://8.8.8.8/callback",
        secret_hash="hash",
        secret_encrypted="encrypted",
        status=WebhookEndpointStatus.active,
    )
    delivery = WebhookDelivery(
        id=uuid.uuid4(),
        job_id=None,
        endpoint_id=endpoint.id,
        status=WebhookDeliveryStatus.dead,
        attempt=5,
        event="webhook.test",
        payload={"status": "test"},
        created_at=datetime.now(UTC),
    )
    async_session.add_all([endpoint, delivery])
    await async_session.flush()

    async with make_client() as client:
        unauthorized = await client.post(
            f"/admin/v1/dlq/webhooks/{delivery.id}/redeliver",
        )
        response = await client.post(
            f"/admin/v1/dlq/webhooks/{delivery.id}/redeliver",
            headers={"X-Admin-Token": "test-admin-token"},
        )

    assert unauthorized.status_code == 401
    assert response.status_code == 202, response.text
    assert response.json() == {"delivery_id": str(delivery.id), "expected_attempt": 6}
    assert delivery.status == WebhookDeliveryStatus.pending
    outbox = (
        await async_session.execute(
            select(Outbox).where(
                Outbox.topic == "webhooks.delivery",
                Outbox.payload["delivery_id"].astext == str(delivery.id),
            )
        )
    ).scalar_one()
    assert outbox.payload["expected_attempt"] == 6


@pytest.mark.integration
async def test_webhook_repository_list_and_disable(
    async_session: AsyncSession,
    seed_tenant: Tenant,
) -> None:
    from shared.repositories.webhook_repository import WebhookRepository

    tenant_id = seed_tenant.id
    repo = WebhookRepository(async_session)

    ep1 = await repo.create(
        tenant_id=tenant_id,
        url="https://example.com/1",
        secret_hash="h1",
        secret_encrypted="e1",
    )
    ep2 = await repo.create(
        tenant_id=tenant_id,
        url="https://example.com/2",
        secret_hash="h2",
        secret_encrypted="e2",
    )

    listed = await repo.list_for_tenant(tenant_id)
    assert {e.id for e in listed} == {ep1.id, ep2.id}

    found = await repo.get_for_tenant(ep1.id, tenant_id, active_only=True)
    assert found is not None

    other_tenant = uuid.uuid4()
    assert await repo.get_for_tenant(ep1.id, other_tenant) is None

    assert await repo.disable(ep1.id, tenant_id) is True
    assert await repo.get_for_tenant(ep1.id, tenant_id, active_only=True) is None
    assert await repo.get_for_tenant(ep1.id, tenant_id, active_only=False) is not None

    assert await repo.disable(uuid.uuid4(), tenant_id) is False


@pytest.mark.integration
async def test_admin_dlq_list_returns_dead_deliveries(
    async_session: AsyncSession,
    seed_tenant: Tenant,
) -> None:
    from api.routes.admin_webhooks import list_dead_webhooks
    from shared.models.webhook_endpoint import WebhookEndpointStatus

    endpoint = WebhookEndpoint(
        id=uuid.uuid4(),
        tenant_id=seed_tenant.id,
        url="https://example.com/cb",
        secret_hash="h",
        secret_encrypted="e",
        status=WebhookEndpointStatus.active,
    )
    dead_delivery = WebhookDelivery(
        id=uuid.uuid4(),
        job_id=None,
        endpoint_id=endpoint.id,
        status=WebhookDeliveryStatus.dead,
        attempt=5,
        event="webhook.test",
        payload={"k": "v"},
        last_response_code=503,
        last_error="HTTP 503",
        created_at=datetime.now(UTC),
    )
    pending_delivery = WebhookDelivery(
        id=uuid.uuid4(),
        job_id=None,
        endpoint_id=endpoint.id,
        status=WebhookDeliveryStatus.pending,
        attempt=1,
        event="webhook.test",
        payload={"k": "v"},
        created_at=datetime.now(UTC),
    )
    async_session.add_all([endpoint, dead_delivery, pending_delivery])
    await async_session.flush()

    result = await list_dead_webhooks(db=async_session)
    assert len(result) == 1
    assert result[0]["delivery_id"] == str(dead_delivery.id)
    assert result[0]["attempt"] == 5
    assert result[0]["last_response_code"] == 503
    assert result[0]["last_error"] == "HTTP 503"
