"""Poll scheduled webhook retries and enqueue them transactionally."""

import asyncio
import logging
from collections.abc import Callable, Coroutine

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.clock import Clock, SystemClock
from shared.models.outbox import Outbox
from shared.models.webhook_delivery import WebhookDelivery, WebhookDeliveryStatus

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 0.5
BATCH_SIZE = 100


async def enqueue_due_deliveries(
    db: AsyncSession,
    *,
    clock: Clock | None = None,
) -> int:
    now = (clock or SystemClock()).now()
    deliveries = (
        (
            await db.execute(
                select(WebhookDelivery)
                .where(
                    WebhookDelivery.status == WebhookDeliveryStatus.pending,
                    WebhookDelivery.next_attempt_at.is_not(None),
                    WebhookDelivery.next_attempt_at <= now,
                )
                .order_by(WebhookDelivery.next_attempt_at)
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for delivery in deliveries:
        db.add(
            Outbox(
                topic="webhooks.delivery",
                payload={
                    "delivery_id": str(delivery.id),
                    "expected_attempt": delivery.attempt + 1,
                },
            )
        )
        delivery.next_attempt_at = None
    await db.flush()
    return len(deliveries)


DbFactory = Callable[[], Coroutine[object, object, AsyncSession]]


async def run_retry_poller(db_factory: DbFactory) -> None:  # pragma: no cover
    while True:
        db = await db_factory()
        try:
            async with db.begin():
                count = await enqueue_due_deliveries(db)
            if count:
                logger.debug("Enqueued %d webhook retries", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Webhook retry poll failed")
        finally:
            await db.close()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _main() -> None:  # pragma: no cover
    from shared.db.session import SessionLocal

    async def db_factory() -> AsyncSession:
        return SessionLocal()

    await run_retry_poller(db_factory)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())
