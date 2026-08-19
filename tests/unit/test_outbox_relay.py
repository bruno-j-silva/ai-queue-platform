"""Unit tests for workers/outbox_relay.py — TDD RED phase written first.

Strategy:
- SQLite in-memory DB (via aiosqlite) for the storage layer.
  relay_once uses raw SQL (FOR UPDATE SKIP LOCKED is stripped by SQLite;
  locking is handled at the dialect level in production).
- AsyncMock for the aio_pika channel — no real RabbitMQ needed.

The outbox table in SQLite stores payload as TEXT (JSON string) because
SQLite has no native JSONB.  relay_once reads payload via raw SQL rows and
treats the value as an opaque JSON string, so it works with both dialects.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Lightweight SQLite schema (created with raw DDL, no ORM metadata import)
# ---------------------------------------------------------------------------

_CREATE_OUTBOX_SQL = """
CREATE TABLE IF NOT EXISTS outbox (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    topic      TEXT    NOT NULL,
    payload    TEXT    NOT NULL,
    published_at DATETIME
)
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite async session with the outbox table."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_OUTBOX_SQL))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _make_channel() -> AsyncMock:
    """Build a minimal mock that mimics aio_pika channel/exchange."""
    channel = AsyncMock()
    exchange = AsyncMock()
    channel.default_exchange = exchange
    exchange.publish = AsyncMock()
    return channel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_outbox(
    session: AsyncSession,
    topic: str,
    payload: dict,
    published_at: datetime | None = None,
) -> int:
    """Insert a raw outbox row and return its id."""
    result = await session.execute(
        text(
            "INSERT INTO outbox (topic, payload, published_at) "
            "VALUES (:topic, :payload, :published_at)"
        ),
        {
            "topic": topic,
            "payload": json.dumps(payload),
            "published_at": published_at,
        },
    )
    await session.commit()
    return result.lastrowid  # type: ignore[return-value]


async def _fetch_published_at(session: AsyncSession, row_id: int) -> datetime | None:
    row = await session.execute(
        text("SELECT published_at FROM outbox WHERE id = :id"), {"id": row_id}
    )
    return row.scalar_one()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relay_once_publishes_pending_messages(db_session: AsyncSession) -> None:
    """Records with published_at=None are published to RabbitMQ."""
    from workers.outbox_relay import relay_once

    await _insert_outbox(db_session, "inference.dispatch", {"job_id": "abc"})
    await _insert_outbox(db_session, "webhooks.delivery", {"url": "https://example.com"})

    channel = _make_channel()
    count = await relay_once(db_session, channel)

    assert count == 2
    assert channel.default_exchange.publish.await_count == 2


@pytest.mark.asyncio
async def test_relay_once_skips_already_published(db_session: AsyncSession) -> None:
    """Records with published_at already set are not published again."""
    from workers.outbox_relay import relay_once

    already = datetime(2025, 1, 1, 12, 0, 0)
    await _insert_outbox(
        db_session,
        "inference.dispatch",
        {"job_id": "old"},
        published_at=already,
    )

    channel = _make_channel()
    count = await relay_once(db_session, channel)

    assert count == 0
    channel.default_exchange.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_relay_once_returns_count_of_published(db_session: AsyncSession) -> None:
    """relay_once returns the exact number of messages published."""
    from workers.outbox_relay import relay_once

    for i in range(5):
        await _insert_outbox(db_session, "inference.dispatch", {"job_id": str(i)})

    channel = _make_channel()
    count = await relay_once(db_session, channel)

    assert count == 5


@pytest.mark.asyncio
async def test_relay_once_marks_published_at_after_publish(db_session: AsyncSession) -> None:
    """published_at is set on the row after successful RabbitMQ publish."""
    from workers.outbox_relay import relay_once

    row_id = await _insert_outbox(db_session, "inference.dispatch", {"job_id": "xyz"})
    assert await _fetch_published_at(db_session, row_id) is None

    channel = _make_channel()
    # relay_once runs inside the session's autobegun transaction.
    # Commit explicitly so the UPDATE becomes visible to subsequent queries.
    await relay_once(db_session, channel)
    await db_session.commit()

    assert await _fetch_published_at(db_session, row_id) is not None


@pytest.mark.asyncio
async def test_relay_once_publishes_correct_payload(db_session: AsyncSession) -> None:
    """Inference outbox entries are encoded with the Celery task protocol."""
    import aio_pika

    from workers.outbox_relay import relay_once

    payload = {"job_id": "test-123", "model": "gpt-4"}
    await _insert_outbox(db_session, "inference.dispatch", payload)

    channel = _make_channel()
    await relay_once(db_session, channel)

    assert channel.default_exchange.publish.await_count == 1
    publish_call = channel.default_exchange.publish.await_args
    message: aio_pika.Message = publish_call.args[0]
    routing_key: str = publish_call.kwargs["routing_key"]

    body = json.loads(message.body)
    assert body[0] == [payload["job_id"]]
    assert body[1] == {}
    assert message.headers["task"] == "workers.inference.process_job"
    assert message.headers["id"]
    assert routing_key == "inference.dispatch"


@pytest.mark.asyncio
async def test_relay_once_does_not_mark_published_at_if_publish_fails(
    db_session: AsyncSession,
) -> None:
    """If publishing raises, the row remains pending (published_at stays None)."""
    from workers.outbox_relay import relay_once

    row_id = await _insert_outbox(db_session, "inference.dispatch", {"job_id": "fail-me"})

    channel = _make_channel()
    channel.default_exchange.publish.side_effect = Exception("RabbitMQ down")

    with pytest.raises(Exception, match="RabbitMQ down"):
        await relay_once(db_session, channel)

    assert await _fetch_published_at(db_session, row_id) is None


@pytest.mark.asyncio
async def test_relay_loop_calls_relay_once_repeatedly() -> None:
    """run_relay_loop calls relay_once at least twice before being cancelled."""
    from workers.outbox_relay import POLL_INTERVAL_SECONDS, run_relay_loop

    call_count = 0

    async def fake_relay_once(db: AsyncSession, channel: object) -> int:
        nonlocal call_count
        call_count += 1
        return 0

    # Build a fake session whose async context manager (begin()) is a no-op.
    def _make_fake_session() -> AsyncMock:
        session = AsyncMock(spec=AsyncSession)
        begin_ctx = AsyncMock()
        begin_ctx.__aenter__ = AsyncMock(return_value=None)
        begin_ctx.__aexit__ = AsyncMock(return_value=False)
        session.begin.return_value = begin_ctx
        return session

    async def fake_db_factory() -> AsyncSession:
        return _make_fake_session()  # type: ignore[return-value]

    # Mock the RabbitMQ connection so no network call is made.
    mock_connection = AsyncMock()
    mock_channel = AsyncMock()
    mock_connection.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_connection.__aexit__ = AsyncMock(return_value=False)
    mock_connection.channel = AsyncMock(return_value=mock_channel)

    with (
        patch("workers.outbox_relay.relay_once", side_effect=fake_relay_once),
        patch("aio_pika.connect_robust", return_value=mock_connection),
    ):
        task = asyncio.create_task(run_relay_loop(fake_db_factory, "amqp://fake-url"))
        await asyncio.sleep(POLL_INTERVAL_SECONDS * 2.5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert call_count >= 2
