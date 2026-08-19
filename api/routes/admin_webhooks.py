"""Operator API for webhook DLQ inspection and redelivery."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import problem_response
from shared.auth.admin import require_admin_token
from shared.auth.dependencies import _get_db
from shared.models.outbox import Outbox
from shared.models.webhook_delivery import WebhookDelivery, WebhookDeliveryStatus

router = APIRouter(
    prefix="/admin/v1/dlq/webhooks",
    tags=["admin-webhooks"],
    dependencies=[Depends(require_admin_token)],
)


@router.get("")
async def list_dead_webhooks(
    db: Annotated[AsyncSession, Depends(_get_db)],
) -> list[dict[str, object]]:
    deliveries = (
        (
            await db.execute(
                select(WebhookDelivery)
                .where(WebhookDelivery.status == WebhookDeliveryStatus.dead)
                .order_by(WebhookDelivery.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "delivery_id": str(item.id),
            "attempt": item.attempt,
            "last_response_code": item.last_response_code,
            "last_error": item.last_error,
        }
        for item in deliveries
    ]


@router.post("/{delivery_id}/redeliver", status_code=202, response_model=None)
async def redeliver_webhook(
    delivery_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(_get_db)],
) -> dict[str, object] | object:
    delivery = (
        await db.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.id == delivery_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if delivery is None:
        return problem_response(404, "Not Found", "Webhook delivery not found.")
    if delivery.status != WebhookDeliveryStatus.dead:
        return problem_response(409, "Not Dead", "Only dead deliveries can be redelivered.")

    expected_attempt = delivery.attempt + 1
    delivery.status = WebhookDeliveryStatus.pending
    delivery.next_attempt_at = None
    db.add(
        Outbox(
            topic="webhooks.delivery",
            payload={
                "delivery_id": str(delivery.id),
                "expected_attempt": expected_attempt,
            },
        )
    )
    await db.flush()
    return {"delivery_id": str(delivery.id), "expected_attempt": expected_attempt}
