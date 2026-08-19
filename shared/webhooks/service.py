"""Transactional creation of webhook deliveries."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.job import Job
from shared.models.outbox import Outbox
from shared.models.webhook_delivery import WebhookDelivery, WebhookDeliveryStatus
from shared.models.webhook_endpoint import WebhookEndpoint, WebhookEndpointStatus


def snapshot_job(job: Job) -> dict[str, Any]:
    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "result": {"output": job.result_inline, "artifact_urls": []}
        if job.result_inline is not None
        else None,
        "usage": job.usage,
        "error": job.error,
        "timestamps": {
            "queued_at": job.queued_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        },
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
    }


async def create_terminal_delivery(db: AsyncSession, job: Job) -> WebhookDelivery | None:
    if job.webhook_endpoint_id is None:
        return None
    endpoint = (
        await db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == job.webhook_endpoint_id,
                WebhookEndpoint.tenant_id == job.tenant_id,
                WebhookEndpoint.status == WebhookEndpointStatus.active,
            )
        )
    ).scalar_one_or_none()
    if endpoint is None:
        return None

    delivery = WebhookDelivery(
        id=uuid.uuid4(),
        job_id=job.id,
        endpoint_id=endpoint.id,
        status=WebhookDeliveryStatus.pending,
        attempt=0,
        event=f"job.{job.status.value}",
        payload=snapshot_job(job),
        created_at=datetime.now(UTC),
    )
    db.add(delivery)
    db.add(
        Outbox(
            topic="webhooks.delivery",
            payload={"delivery_id": str(delivery.id), "expected_attempt": 1},
        )
    )
    await db.flush()
    return delivery
