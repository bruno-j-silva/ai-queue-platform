"""Outbox relay worker — ADR-006: Transactional Outbox / at-least-once delivery.

Polls the ``outbox`` table for pending records and publishes them to RabbitMQ.

Guarantees:
- ``FOR UPDATE SKIP LOCKED`` prevents double-processing across concurrent relay
  instances (Postgres only; SQLite ignores locking hints).
- ``published_at`` is only written *after* a successful broker publish.  If the
  publish raises the exception propagates and the caller (``run_relay_loop``)
  does not commit, leaving the row pending for the next poll cycle.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

import aio_pika
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS: float = 0.5
BATCH_SIZE: int = 100

# ---------------------------------------------------------------------------
# SQL fragments
# ---------------------------------------------------------------------------

_SELECT_PENDING_LOCKED = text(
    """
    SELECT id, topic, payload
    FROM outbox
    WHERE published_at IS NULL
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
    """
)

_SELECT_PENDING_PLAIN = text(
    """
    SELECT id, topic, payload
    FROM outbox
    WHERE published_at IS NULL
    LIMIT :batch_size
    """
)

_MARK_PUBLISHED = text(
    """
    UPDATE outbox
    SET published_at = :published_at
    WHERE id = :id
    """
)


# ---------------------------------------------------------------------------
# Core relay function
# ---------------------------------------------------------------------------


async def relay_once(
    db: AsyncSession,
    channel: aio_pika.abc.AbstractChannel,
) -> int:
    """Fetch pending outbox rows, publish to RabbitMQ, and mark as published.

    The caller is responsible for transaction lifecycle (begin / commit /
    rollback).  ``relay_once`` executes within whatever transaction context
    the session currently has.

    Args:
        db: An open async SQLAlchemy session.
        channel: An open aio-pika channel connected to RabbitMQ.

    Returns:
        The number of messages published in this batch (0 if nothing pending).

    Raises:
        Any exception raised by ``channel.default_exchange.publish`` — the
        caller must *not* commit in that case, leaving rows pending.
    """
    try:
        rows = (await db.execute(_SELECT_PENDING_LOCKED, {"batch_size": BATCH_SIZE})).fetchall()
    except Exception:
        # ``FOR UPDATE SKIP LOCKED`` is Postgres-specific; fall back to a
        # plain SELECT for dialects that do not support it (e.g. SQLite).
        rows = (await db.execute(_SELECT_PENDING_PLAIN, {"batch_size": BATCH_SIZE})).fetchall()

    if not rows:
        return 0

    published_at = datetime.now(tz=UTC)

    for row in rows:
        row_id: int = row[0]
        topic: str = row[1]
        raw_payload: Any = row[2]

        payload = raw_payload if isinstance(raw_payload, dict) else json.loads(raw_payload)
        headers: dict[str, Any] | None = None
        if topic == "inference.dispatch":
            task_id = str(uuid.uuid4())
            body = json.dumps(
                [
                    [payload["job_id"]],
                    {},
                    {"callbacks": None, "errbacks": None, "chain": None, "chord": None},
                ]
            ).encode()
            headers = {
                "lang": "py",
                "task": "workers.inference.process_job",
                "id": task_id,
                "root_id": task_id,
                "retries": 0,
            }
        else:
            body = json.dumps(payload).encode()

        message = aio_pika.Message(
            body=body,
            content_type="application/json",
            content_encoding="utf-8",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            headers=headers,
        )

        # Publish BEFORE marking; if this raises the caller must not commit.
        await channel.default_exchange.publish(
            message,
            routing_key=topic,
        )

        await db.execute(
            _MARK_PUBLISHED,
            {"published_at": published_at, "id": row_id},
        )

    return len(rows)


# ---------------------------------------------------------------------------
# Relay loop
# ---------------------------------------------------------------------------

DbFactory = Callable[[], Coroutine[Any, Any, AsyncSession]]


async def run_relay_loop(
    db_factory: DbFactory,
    rabbitmq_url: str,
) -> None:
    """Infinite loop: open a RabbitMQ connection, then call ``relay_once`` in
    a transaction every ``POLL_INTERVAL_SECONDS``.

    Args:
        db_factory: Async callable that returns a fresh ``AsyncSession``.
        rabbitmq_url: AMQP URL (e.g. ``amqp://guest:guest@localhost/``).

    The loop runs until cancelled (e.g. SIGTERM → ``asyncio.CancelledError``).
    """
    connection = await aio_pika.connect_robust(rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        logger.info("Outbox relay started (poll_interval=%.2fs)", POLL_INTERVAL_SECONDS)
        while True:
            db = await db_factory()
            try:
                async with db.begin():
                    count = await relay_once(db, channel)
                if count:
                    logger.debug("Relayed %d outbox message(s)", count)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("relay_once failed; will retry after poll interval")
            finally:
                await db.close()
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _main() -> None:  # pragma: no cover
    from shared.db.session import SessionLocal

    async def db_factory() -> AsyncSession:
        return SessionLocal()

    await run_relay_loop(db_factory, os.environ["RABBITMQ_URL"])


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())
