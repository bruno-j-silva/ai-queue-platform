"""Celery task: process a single inference job (SPEC-005)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from celery import Task

from shared.backends.protocol import CancelToken, InferenceBackend, InferenceRequest
from shared.domain.inference_runner import run_inference
from shared.domain.state_machine import JobEvent as StateMachineEvent
from shared.domain.state_machine import transition
from shared.models.job import Job, JobStatus
from shared.models.job_event import JobEvent
from workers.celery_app import app

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@app.task(
    bind=True,
    name="workers.inference.process_job",
    acks_late=True,
    reject_on_worker_lost=True,
)  # type: ignore[untyped-decorator]
def process_job(self: Task, job_id: str) -> None:
    """Entry point para o Celery worker. Consome mensagens de inference.dispatch."""
    asyncio.run(_run_with_new_session(job_id))  # pragma: no cover


async def _run_with_new_session(job_id: str) -> None:  # pragma: no cover
    """Cria sessão própria e gerencia a transação em produção."""
    import os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with session.begin():
                await _process_job_async(job_id, session=session)
    finally:
        await engine.dispose()


async def _process_job_async(
    job_id: str,
    *,
    session: AsyncSession,
    backend_override: InferenceBackend | None = None,
) -> None:
    """Lógica principal — injetável para testes sem overhead do Celery.

    Usa flush() apenas; quem chama gerencia o commit/rollback.

    Estados aceitos:
    - queued: processamento normal (tentativa 1)
    - running: reentrega por crash do worker (tentativa N+1)
    - succeeded / failed / cancelled: ignorado silenciosamente (idempotência)
    """
    from sqlalchemy import select

    from shared.backends import resolve_backend_class
    from shared.models.model_catalog import ModelCatalog

    job_uuid = uuid.UUID(job_id)

    stmt = select(Job).where(Job.id == job_uuid).with_for_update()
    result = await session.execute(stmt)
    job: Job | None = result.scalar_one_or_none()

    if job is None:
        logger.warning("Job %s não encontrado, ignorando", job_id)
        return

    if job.status in (
        JobStatus.succeeded,
        JobStatus.failed,
        JobStatus.cancelled,
        JobStatus.expired,
    ):
        logger.info("Job %s já está em estado terminal (%s), ignorando", job_id, job.status)
        return

    if job.status == JobStatus.queued:
        start_status = job.status
        job.status = transition(job.status, StateMachineEvent.START)
        session.add(
            JobEvent(
                job_id=job.id,
                from_status=start_status,
                to_status=job.status,
                detail={"origin": "worker"},
                created_at=datetime.now(UTC),
            )
        )
    job.started_at = datetime.now(UTC)
    job.attempt += 1
    await session.flush()

    logger.info("Job %s iniciando tentativa %d", job_id, job.attempt)

    # Resolver backend
    model_stmt = select(ModelCatalog).where(ModelCatalog.id == job.model_id)
    model_result = await session.execute(model_stmt)
    model = model_result.scalar_one()

    if backend_override is not None:
        backend: InferenceBackend = backend_override
    else:
        import os

        if os.environ.get("BACKEND_MODE") == "fake":
            from shared.backends.fake import FakeBackend

            backend = FakeBackend()
        else:
            backend_cls = resolve_backend_class(model.backend)
            backend = backend_cls(base_url=os.environ.get("OLLAMA_URL", "http://ollama:11434"))

    # Construir request a partir do payload do job
    payload = job.payload or {}
    messages = payload.get(
        "messages",
        [{"role": "user", "content": payload.get("prompt", "")}],
    )
    request = InferenceRequest(
        job_id=str(job.id),
        model_id=model.backend_model_name,
        messages=messages,
        params=payload.get("params", {}),
        timeout_seconds=job.timeout_seconds,
        attempt=job.attempt,
    )

    cancel_token = CancelToken()
    run_result = await run_inference(backend, request, cancel_token)

    now = datetime.now(UTC)
    previous_status: JobStatus = JobStatus.running
    if run_result.succeeded:
        inference_result = run_result.result
        assert inference_result is not None
        job.status = transition(job.status, StateMachineEvent.COMPLETE)
        job.result_inline = inference_result.output
        job.usage = {
            **inference_result.usage,
            "model": model.backend_model_name,
            "attempt": run_result.attempt,
        }
        job.finished_at = now
        logger.info("Job %s concluído com sucesso na tentativa %d", job_id, run_result.attempt)
    else:
        job.status = transition(job.status, StateMachineEvent.FAIL)
        job.error = {
            "code": run_result.error_code,
            "message": run_result.error_message,
            "attempt": run_result.attempt,
        }
        job.finished_at = now
        logger.warning(
            "Job %s falhou (code=%s) na tentativa %d",
            job_id,
            run_result.error_code,
            run_result.attempt,
        )

    session.add(
        JobEvent(
            job_id=job.id,
            from_status=previous_status,
            to_status=job.status,
            detail={"origin": "worker", "attempt": run_result.attempt},
            created_at=now,
        )
    )

    await session.flush()
