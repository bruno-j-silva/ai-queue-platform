"""
AC-06: worker crash → redelivery e reprocesso (acks_late) — SPEC-005.

TDD RED phase: valida dois comportamentos:
1. Estrutural: process_job tem acks_late=True e reject_on_worker_lost=True.
2. Comportamental: job em estado 'running' (worker anterior morreu) é
   reprocessado corretamente quando a mensagem é reenviada ao próximo worker.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.models import (  # noqa: F401
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
# AC-06 estrutural: configuração de acks_late
# ---------------------------------------------------------------------------


def test_spec005_ac06_acks_late_configured() -> None:
    """AC-06 estrutural: process_job deve ter acks_late=True e reject_on_worker_lost=True."""
    from workers.inference_task import process_job

    assert process_job.acks_late is True, (
        "acks_late deve ser True para garantir entrega-pelo-menos-uma-vez"
    )
    assert process_job.reject_on_worker_lost is True, (
        "reject_on_worker_lost deve ser True para recolocar mensagem na fila quando worker morre"
    )


# ---------------------------------------------------------------------------
# AC-06 comportamental: job em 'running' é reprocessado (redelivery)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_spec005_ac06_running_job_reprocessed_on_redelivery(
    async_session: AsyncSession,
    seed_data: dict,
) -> None:
    """AC-06: job em estado 'running' (worker anterior morreu após transição)
    é processado com sucesso quando a mensagem é reenviada ao próximo worker."""
    from shared.backends.fake import FakeBackend
    from workers.inference_task import _process_job_async

    # Arrange: job já em 'running' (worker anterior morreu após transicionar estado)
    job = Job(
        id=uuid.uuid4(),
        tenant_id=seed_data["tenant"].id,
        model_id=seed_data["model"].id,
        status=JobStatus.running,
        payload={"messages": [{"role": "user", "content": "retry me"}]},
        timeout_seconds=30,
        priority_weight=10,
        attempt=1,  # primeira tentativa foi iniciada
        cancel_requested=False,
        queued_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
    )
    async_session.add(job)
    await async_session.flush()

    backend = FakeBackend(response_text="recovered")

    # Act: task recebe job em 'running' → deve reprocessar (segunda tentativa)
    await _process_job_async(str(job.id), session=async_session, backend_override=backend)

    await async_session.refresh(job)

    assert job.status == JobStatus.succeeded, f"Expected succeeded, got {job.status}"
    assert job.attempt == 2, f"Expected attempt=2 (segundo processamento), got {job.attempt}"
    assert job.usage is not None
    assert job.finished_at is not None


@pytest.mark.integration
async def test_spec005_ac06_terminal_job_skipped_on_redelivery(
    async_session: AsyncSession,
    seed_data: dict,
) -> None:
    """AC-06 idempotência: job já terminal (succeeded/failed) é ignorado silenciosamente
    se a mensagem for entregue novamente (não duplica processamento)."""
    from shared.backends.fake import FakeBackend
    from workers.inference_task import _process_job_async

    now = datetime.now(UTC)
    job = Job(
        id=uuid.uuid4(),
        tenant_id=seed_data["tenant"].id,
        model_id=seed_data["model"].id,
        status=JobStatus.succeeded,
        payload={"messages": [{"role": "user", "content": "already done"}]},
        timeout_seconds=30,
        priority_weight=10,
        attempt=1,
        cancel_requested=False,
        queued_at=now,
        started_at=now,
        finished_at=now,
        result_inline=[{"type": "text", "text": "original result"}],
        usage={"input_tokens": 5, "output_tokens": 3, "duration_ms": 100, "backend": "fake"},
    )
    async_session.add(job)
    await async_session.flush()

    original_result = job.result_inline
    backend = FakeBackend(response_text="should not appear")

    # Act: task recebe job já terminal → deve ignorar sem alterar estado
    await _process_job_async(str(job.id), session=async_session, backend_override=backend)

    await async_session.refresh(job)

    assert job.status == JobStatus.succeeded, "status não deve mudar"
    assert job.attempt == 1, "attempt não deve incrementar"
    assert job.result_inline == original_result, "result_inline não deve ser sobrescrito"
