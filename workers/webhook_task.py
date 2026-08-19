"""Celery webhook dispatcher for SPEC-003."""

import asyncio
import logging
import os
import random
import uuid
from datetime import timedelta

import httpx
from celery import Task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.clock import Clock, SystemClock
from shared.metrics import webhook_dead_total, webhook_delivery_total
from shared.models.outbox import Outbox
from shared.models.webhook_delivery import WebhookDelivery, WebhookDeliveryStatus
from shared.models.webhook_endpoint import WebhookEndpoint
from shared.webhooks.delivery import (
    MAX_ATTEMPTS,
    build_webhook_payload,
    canonical_json,
    retry_delay_seconds,
)
from shared.webhooks.secrets import decrypt_secret
from shared.webhooks.signing import build_headers, sign_payload
from shared.webhooks.url_validation import UnsafeWebhookUrlError, validate_webhook_url
from workers.celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    bind=True,
    name="workers.webhooks.dispatch",
    acks_late=True,
    reject_on_worker_lost=True,
)  # type: ignore[untyped-decorator]
def dispatch_webhook(self: Task, delivery_id: str, expected_attempt: int) -> None:
    asyncio.run(_run_with_new_session(delivery_id, expected_attempt))  # pragma: no cover


async def _run_with_new_session(delivery_id: str, expected_attempt: int) -> None:  # pragma: no cover
    from shared.db.session import SessionLocal

    async with SessionLocal() as session, session.begin():
        await dispatch_delivery_async(
            delivery_id,
            expected_attempt,
            session=session,
        )


async def dispatch_delivery_async(
    delivery_id: str,
    expected_attempt: int,
    *,
    session: AsyncSession,
    client: httpx.AsyncClient | None = None,
    clock: Clock | None = None,
    jitter_factor: float | None = None,
) -> None:
    current_clock = clock or SystemClock()
    result = await session.execute(
        select(WebhookDelivery, WebhookEndpoint)
        .join(WebhookEndpoint, WebhookEndpoint.id == WebhookDelivery.endpoint_id)
        .where(WebhookDelivery.id == uuid.UUID(delivery_id))
        .with_for_update()
    )
    row = result.one_or_none()
    if row is None:
        logger.warning("Webhook delivery %s not found", delivery_id)
        return
    delivery, endpoint = row
    if delivery.status in (WebhookDeliveryStatus.delivered, WebhookDeliveryStatus.dead):
        return
    if expected_attempt != delivery.attempt + 1:
        logger.info("Ignoring stale webhook attempt for delivery %s", delivery_id)
        return

    now = current_clock.now()
    delivery.status = WebhookDeliveryStatus.delivering
    delivery.attempt = expected_attempt
    delivery.last_attempt_at = now
    delivery.next_attempt_at = None

    payload = build_webhook_payload(
        str(delivery.id),
        delivery.event,
        expected_attempt,
        delivery.payload,
    )
    body = canonical_json(payload)
    secret = decrypt_secret(endpoint.secret_encrypted or "", os.environ["WEBHOOK_ENCRYPTION_KEY"])
    timestamp = int(now.timestamp())
    signature = sign_payload(secret, timestamp, body)
    headers = build_headers(str(delivery.id), expected_attempt, timestamp, signature)

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=False)
    response_code: int | None = None
    error_message: str | None = None
    try:
        validate_webhook_url(
            endpoint.url,
            allow_private=os.environ.get("WEBHOOK_ALLOW_PRIVATE_URLS", "false").lower() == "true",
        )
        response = await http_client.post(endpoint.url, content=body, headers=headers, timeout=10.0)
        response_code = response.status_code
        if not 200 <= response.status_code < 300:
            error_message = f"HTTP {response.status_code}"
    except (httpx.HTTPError, UnsafeWebhookUrlError) as exc:
        error_message = type(exc).__name__
    finally:
        if owns_client:
            await http_client.aclose()

    delivery.last_response_code = response_code
    delivery.last_error = error_message
    if error_message is None:
        delivery.status = WebhookDeliveryStatus.delivered
        delivery.delivered_at = now
        webhook_delivery_total.labels(status="delivered").inc()
    elif expected_attempt >= MAX_ATTEMPTS:
        delivery.status = WebhookDeliveryStatus.dead
        session.add(
            Outbox(
                topic="webhooks.dlq",
                payload={"delivery_id": str(delivery.id), "attempt": expected_attempt},
            )
        )
        webhook_delivery_total.labels(status="dead").inc()
        webhook_dead_total.inc()
    else:
        delivery.status = WebhookDeliveryStatus.pending
        factor = jitter_factor if jitter_factor is not None else random.uniform(0.8, 1.2)
        retry_scale = float(os.environ.get("WEBHOOK_RETRY_SCALE", "1"))
        delivery.next_attempt_at = now + timedelta(
            seconds=retry_delay_seconds(expected_attempt, jitter_factor=factor) * retry_scale
        )
        webhook_delivery_total.labels(status="retry").inc()
    await session.flush()
