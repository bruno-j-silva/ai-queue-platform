"""Tenant webhook endpoint management API."""

import asyncio
import os
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import problem_response
from shared.auth.api_key import TenantIdentity
from shared.auth.dependencies import _get_db, get_current_tenant
from shared.models.outbox import Outbox
from shared.models.webhook_delivery import WebhookDelivery, WebhookDeliveryStatus
from shared.repositories.webhook_repository import WebhookRepository
from shared.webhooks.secrets import encrypt_secret, generate_secret, hash_secret
from shared.webhooks.url_validation import UnsafeWebhookUrlError, validate_webhook_url

router = APIRouter(prefix="/v1/webhook-endpoints", tags=["webhook-endpoints"])


class WebhookEndpointCreateRequest(BaseModel):
    url: str


class WebhookEndpointResponse(BaseModel):
    id: str
    url: str
    status: str


class WebhookEndpointCreatedResponse(WebhookEndpointResponse):
    secret: str


def _allow_private_urls() -> bool:
    return os.environ.get("WEBHOOK_ALLOW_PRIVATE_URLS", "false").lower() == "true"


@router.post("", status_code=201, response_model=WebhookEndpointCreatedResponse)
async def create_webhook_endpoint(
    request: WebhookEndpointCreateRequest,
    tenant: Annotated[TenantIdentity, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(_get_db)],
) -> WebhookEndpointCreatedResponse | Response:
    try:
        url = await asyncio.to_thread(
            validate_webhook_url,
            request.url,
            allow_private=_allow_private_urls(),
        )
    except UnsafeWebhookUrlError as exc:
        return problem_response(422, "Unsafe Webhook URL", str(exc))

    secret = generate_secret()
    endpoint = await WebhookRepository(db).create(
        tenant_id=uuid.UUID(tenant["tenant_id"]),
        url=url,
        secret_hash=hash_secret(secret),
        secret_encrypted=encrypt_secret(secret, os.environ["WEBHOOK_ENCRYPTION_KEY"]),
    )
    return WebhookEndpointCreatedResponse(
        id=str(endpoint.id),
        url=endpoint.url,
        status=endpoint.status.value,
        secret=secret,
    )


@router.get("", response_model=list[WebhookEndpointResponse])
async def list_webhook_endpoints(
    tenant: Annotated[TenantIdentity, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(_get_db)],
) -> list[WebhookEndpointResponse]:
    endpoints = await WebhookRepository(db).list_for_tenant(uuid.UUID(tenant["tenant_id"]))
    return [
        WebhookEndpointResponse(id=str(item.id), url=item.url, status=item.status.value)
        for item in endpoints
    ]


@router.delete("/{endpoint_id}", status_code=204)
async def delete_webhook_endpoint(
    endpoint_id: uuid.UUID,
    tenant: Annotated[TenantIdentity, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(_get_db)],
) -> Response:
    disabled = await WebhookRepository(db).disable(
        endpoint_id,
        uuid.UUID(tenant["tenant_id"]),
    )
    if not disabled:
        return problem_response(404, "Not Found", "Webhook endpoint not found.")
    return Response(status_code=204)


@router.post("/{endpoint_id}/test", status_code=202, response_model=None)
async def test_webhook_endpoint(
    endpoint_id: uuid.UUID,
    tenant: Annotated[TenantIdentity, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(_get_db)],
) -> dict[str, str] | Response:
    endpoint = await WebhookRepository(db).get_for_tenant(
        endpoint_id,
        uuid.UUID(tenant["tenant_id"]),
        active_only=True,
    )
    if endpoint is None:
        return problem_response(404, "Not Found", "Webhook endpoint not found.")

    delivery = WebhookDelivery(
        id=uuid.uuid4(),
        job_id=None,
        endpoint_id=endpoint.id,
        status=WebhookDeliveryStatus.pending,
        attempt=0,
        event="webhook.test",
        payload={"endpoint_id": str(endpoint.id), "status": "test"},
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
    return {"delivery_id": str(delivery.id)}
