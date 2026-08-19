"""
AC-05: job concluído registra `usage` — SPEC-005.

TDD RED phase: teste escrito antes da implementação de workers/inference_task.py.
Usa FakeBackend para isolar a inferência real; testa apenas o fluxo do worker.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.models import (  # noqa: F401 — registra todos os modelos no Base.metadata
    Job,
    JobEvent,
    ModelCatalog,
    Plan,
    PlanModel,
    Tenant,
)
from shared.models.job import JobStatus
from shared.models.model_catalog import ModelBackend, ModelStatus
from shared.models.tenant import TenantStatus
from shared.models.webhook_delivery import WebhookDelivery, WebhookDeliveryStatus
from shared.models.webhook_endpoint import WebhookEndpoint, WebhookEndpointStatus

# ---------------------------------------------------------------------------
# Fixtures: Postgres container + migrations (module-scoped)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def postgres_url() -> dict[str, str]:
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16") as pg:
        sync_url = pg.get_connection_url().replace("psycopg2", "psycopg")
        if "postgresql+psycopg://" not in sync_url:
            sync_url = sync_url.replace("postgresql://", "postgresql+psycopg://")
        yield {"sync": sync_url, "async": sync_url}


@pytest.fixture(scope="module")
def migrated_db(postgres_url: dict[str, str]) -> dict[str, str]:
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
async def async_engine(migrated_db: dict[str, str]):
    engine = create_async_engine(migrated_db["async"], echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def async_session(async_engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


# ---------------------------------------------------------------------------
# Fixtures: dados de domínio mínimos
# ---------------------------------------------------------------------------


@pytest.fixture()
async def seed_data(async_session: AsyncSession) -> dict:
    now = datetime.now(UTC)

    plan = Plan(
        id=uuid.uuid4(),
        name="starter",
        priority_weight=10,
        max_timeout_seconds=300,
        result_ttl_days=7,
        max_payload_mb=10,
    )
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Test Tenant",
        plan_id=plan.id,
        status=TenantStatus.active,
        created_at=now,
        updated_at=now,
    )
    model = ModelCatalog(
        id="test-model",
        backend=ModelBackend.ollama,
        backend_model_name="llama3",
        status=ModelStatus.active,
    )

    async_session.add_all([plan, tenant, model])
    await async_session.flush()
    return {"plan": plan, "tenant": tenant, "model": model}


# ---------------------------------------------------------------------------
# AC-05: job concluído registra usage
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_spec005_ac05_usage_recorded(
    async_session: AsyncSession,
    seed_data: dict,
) -> None:
    """AC-05: após inferência bem-sucedida, job tem usage com tokens e backend."""
    from shared.backends.fake import FakeBackend
    from workers.inference_task import _process_job_async

    job = Job(
        id=uuid.uuid4(),
        tenant_id=seed_data["tenant"].id,
        model_id=seed_data["model"].id,
        status=JobStatus.queued,
        payload={"messages": [{"role": "user", "content": "olá"}]},
        timeout_seconds=30,
        priority_weight=10,
        attempt=0,
        cancel_requested=False,
        queued_at=datetime.now(UTC),
    )
    async_session.add(job)
    await async_session.flush()

    backend = FakeBackend(response_text="mundo")

    await _process_job_async(str(job.id), session=async_session, backend_override=backend)

    await async_session.refresh(job)

    assert job.status == JobStatus.succeeded, f"Expected succeeded, got {job.status}"
    assert job.usage is not None, "usage deve estar preenchido"
    assert "input_tokens" in job.usage
    assert "output_tokens" in job.usage
    assert "duration_ms" in job.usage
    assert "backend" in job.usage
    assert job.usage["model"] == seed_data["model"].backend_model_name
    assert job.usage["attempt"] == 1
    assert job.result_inline is not None, "result_inline deve estar preenchido"
    assert job.started_at is not None, "started_at deve estar preenchido"
    assert job.finished_at is not None, "finished_at deve estar preenchido"
    assert job.attempt == 1

    from sqlalchemy import select

    events = (
        (
            await async_session.execute(
                select(JobEvent).where(JobEvent.job_id == job.id).order_by(JobEvent.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(event.from_status, event.to_status) for event in events] == [
        (JobStatus.queued, JobStatus.running),
        (JobStatus.running, JobStatus.succeeded),
    ]


@pytest.mark.integration
async def test_spec005_ac05_failed_job_records_error(
    async_session: AsyncSession,
    seed_data: dict,
) -> None:
    """AC-05 variante: job com erro permanente registra error, não usage."""
    from shared.backends.fake import FakeBackend
    from workers.inference_task import _process_job_async

    job = Job(
        id=uuid.uuid4(),
        tenant_id=seed_data["tenant"].id,
        model_id=seed_data["model"].id,
        status=JobStatus.queued,
        payload={"messages": [{"role": "user", "content": "falha"}]},
        timeout_seconds=30,
        priority_weight=10,
        attempt=0,
        cancel_requested=False,
        queued_at=datetime.now(UTC),
    )
    async_session.add(job)
    await async_session.flush()

    backend = FakeBackend(permanent_error=True)

    await _process_job_async(str(job.id), session=async_session, backend_override=backend)

    await async_session.refresh(job)

    assert job.status == JobStatus.failed
    assert job.error is not None
    assert "code" in job.error
    assert job.error["code"] == "permanent"
    assert job.finished_at is not None


@pytest.mark.integration
async def test_spec005_ac05_nonexistent_job_is_ignored(
    async_session: AsyncSession,
    seed_data: dict,
) -> None:
    """Cobertura: job não encontrado no DB → retorna silenciosamente sem erro."""
    from workers.inference_task import _process_job_async

    nonexistent_id = str(uuid.uuid4())
    # Deve retornar sem exceção
    await _process_job_async(nonexistent_id, session=async_session)


@pytest.mark.integration
async def test_spec005_ac05_backend_resolved_from_catalog(
    async_session: AsyncSession,
    seed_data: dict,
) -> None:
    """Cobertura: sem backend_override, resolve backend do ModelCatalog via registry."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from shared.backends.protocol import InferenceResult
    from workers.inference_task import _process_job_async

    job = Job(
        id=uuid.uuid4(),
        tenant_id=seed_data["tenant"].id,
        model_id=seed_data["model"].id,
        status=JobStatus.queued,
        payload={"messages": [{"role": "user", "content": "via catalog"}]},
        timeout_seconds=30,
        priority_weight=10,
        attempt=0,
        cancel_requested=False,
        queued_at=datetime.now(UTC),
    )
    async_session.add(job)
    await async_session.flush()

    fake_result = InferenceResult(
        output=[{"type": "text", "text": "catalog response"}],
        usage={"input_tokens": 3, "output_tokens": 2, "duration_ms": 50, "backend": "fake"},
    )
    mock_backend_instance = AsyncMock()
    mock_backend_instance.generate = AsyncMock(return_value=fake_result)
    mock_backend_instance.abort = AsyncMock()
    mock_backend_cls = MagicMock(return_value=mock_backend_instance)

    with patch("shared.backends.resolve_backend_class", return_value=mock_backend_cls):
        await _process_job_async(str(job.id), session=async_session)

    await async_session.refresh(job)
    assert job.status == JobStatus.succeeded
    assert job.usage is not None


@pytest.mark.integration
async def test_spec003_ac01_terminal_state_creates_delivery_same_tx(
    async_session: AsyncSession,
    seed_data: dict,
) -> None:
    from sqlalchemy import select

    from shared.backends.fake import FakeBackend
    from shared.models.outbox import Outbox
    from shared.webhooks.secrets import encrypt_secret, generate_secret, hash_secret
    from workers.inference_task import _process_job_async

    secret = generate_secret()
    endpoint = WebhookEndpoint(
        id=uuid.uuid4(),
        tenant_id=seed_data["tenant"].id,
        url="https://8.8.8.8/callback",
        secret_hash=hash_secret(secret),
        secret_encrypted=encrypt_secret(secret, os.environ["WEBHOOK_ENCRYPTION_KEY"]),
        status=WebhookEndpointStatus.active,
    )
    job = Job(
        id=uuid.uuid4(),
        tenant_id=seed_data["tenant"].id,
        model_id=seed_data["model"].id,
        webhook_endpoint_id=endpoint.id,
        status=JobStatus.queued,
        payload={"messages": [{"role": "user", "content": "webhook"}]},
        timeout_seconds=30,
        priority_weight=10,
        attempt=0,
        cancel_requested=False,
        queued_at=datetime.now(UTC),
    )
    async_session.add(endpoint)
    await async_session.flush()
    async_session.add(job)
    await async_session.flush()

    await _process_job_async(str(job.id), session=async_session, backend_override=FakeBackend())

    delivery = (
        await async_session.execute(select(WebhookDelivery).where(WebhookDelivery.job_id == job.id))
    ).scalar_one()
    outbox = (
        await async_session.execute(
            select(Outbox).where(
                Outbox.topic == "webhooks.delivery",
                Outbox.payload["delivery_id"].astext == str(delivery.id),
            )
        )
    ).scalar_one()
    assert delivery.status == WebhookDeliveryStatus.pending
    assert delivery.event == "job.succeeded"
    assert delivery.payload["status"] == "succeeded"
    assert outbox.payload["expected_attempt"] == 1


async def _create_webhook_delivery(
    async_session: AsyncSession,
    seed_data: dict,
    *,
    attempt: int = 0,
) -> WebhookDelivery:
    from shared.webhooks.secrets import encrypt_secret, generate_secret, hash_secret

    secret = generate_secret()
    endpoint = WebhookEndpoint(
        id=uuid.uuid4(),
        tenant_id=seed_data["tenant"].id,
        url="https://8.8.8.8/callback",
        secret_hash=hash_secret(secret),
        secret_encrypted=encrypt_secret(secret, os.environ["WEBHOOK_ENCRYPTION_KEY"]),
        status=WebhookEndpointStatus.active,
    )
    delivery = WebhookDelivery(
        id=uuid.uuid4(),
        job_id=None,
        endpoint_id=endpoint.id,
        status=WebhookDeliveryStatus.pending,
        attempt=attempt,
        event="webhook.test",
        payload={"status": "test"},
        created_at=datetime.now(UTC),
    )
    async_session.add_all([endpoint, delivery])
    await async_session.flush()
    return delivery


@pytest.mark.integration
async def test_spec003_ac03_2xx_marks_delivered(
    async_session: AsyncSession,
    seed_data: dict,
) -> None:
    import httpx

    from workers.webhook_task import dispatch_delivery_async

    delivery = await _create_webhook_delivery(async_session, seed_data)
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(204)))
    await dispatch_delivery_async(
        str(delivery.id),
        1,
        session=async_session,
        client=client,
        jitter_factor=1.0,
    )
    await client.aclose()

    assert delivery.status == WebhookDeliveryStatus.delivered
    assert delivery.attempt == 1
    assert delivery.delivered_at is not None
    assert delivery.next_attempt_at is None


@pytest.mark.integration
async def test_spec003_ac04_retry_backoff_schedule(
    async_session: AsyncSession,
    seed_data: dict,
) -> None:
    import httpx

    from shared.clock import FakeClock
    from workers.webhook_task import dispatch_delivery_async

    delivery = await _create_webhook_delivery(async_session, seed_data)
    clock = FakeClock()
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    await dispatch_delivery_async(
        str(delivery.id),
        1,
        session=async_session,
        client=client,
        clock=clock,
        jitter_factor=1.0,
    )
    await client.aclose()

    assert delivery.status == WebhookDeliveryStatus.pending
    assert delivery.attempt == 1
    assert delivery.next_attempt_at == clock.now() + timedelta(seconds=60)
    assert delivery.last_response_code == 500


@pytest.mark.integration
async def test_spec003_ac05_exhausted_goes_to_dlq_with_metric(
    async_session: AsyncSession,
    seed_data: dict,
) -> None:
    import httpx
    from sqlalchemy import select

    from shared.metrics import webhook_dead_total
    from shared.models.outbox import Outbox
    from workers.webhook_task import dispatch_delivery_async

    delivery = await _create_webhook_delivery(async_session, seed_data, attempt=4)
    before = webhook_dead_total._value.get()
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    await dispatch_delivery_async(
        str(delivery.id),
        5,
        session=async_session,
        client=client,
        jitter_factor=1.0,
    )
    await client.aclose()

    dlq = (
        await async_session.execute(
            select(Outbox).where(
                Outbox.topic == "webhooks.dlq",
                Outbox.payload["delivery_id"].astext == str(delivery.id),
            )
        )
    ).scalar_one()
    assert delivery.status == WebhookDeliveryStatus.dead
    assert delivery.attempt == 5
    assert delivery.next_attempt_at is None
    assert dlq.payload["attempt"] == 5
    assert webhook_dead_total._value.get() == before + 1


@pytest.mark.integration
async def test_spec003_retry_poller_enqueues_due_delivery_once(
    async_session: AsyncSession,
    seed_data: dict,
) -> None:
    from sqlalchemy import select

    from shared.clock import FakeClock
    from shared.models.outbox import Outbox
    from workers.webhook_retry_poller import enqueue_due_deliveries

    delivery = await _create_webhook_delivery(async_session, seed_data, attempt=1)
    clock = FakeClock()
    delivery.next_attempt_at = clock.now() - timedelta(seconds=1)
    await async_session.flush()

    assert await enqueue_due_deliveries(async_session, clock=clock) == 1
    assert await enqueue_due_deliveries(async_session, clock=clock) == 0

    outbox = (
        await async_session.execute(
            select(Outbox).where(
                Outbox.topic == "webhooks.delivery",
                Outbox.payload["delivery_id"].astext == str(delivery.id),
            )
        )
    ).scalar_one()
    assert outbox.payload["expected_attempt"] == 2
    assert delivery.next_attempt_at is None
