"""Tenant-scoped persistence for webhook endpoints."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.webhook_endpoint import WebhookEndpoint, WebhookEndpointStatus


class WebhookRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        url: str,
        secret_hash: str,
        secret_encrypted: str,
    ) -> WebhookEndpoint:
        endpoint = WebhookEndpoint(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            url=url,
            secret_hash=secret_hash,
            secret_encrypted=secret_encrypted,
            status=WebhookEndpointStatus.active,
        )
        self._db.add(endpoint)
        await self._db.flush()
        return endpoint

    async def list_for_tenant(self, tenant_id: uuid.UUID) -> list[WebhookEndpoint]:
        result = await self._db.execute(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.tenant_id == tenant_id)
            .order_by(WebhookEndpoint.id)
        )
        return list(result.scalars().all())

    async def get_for_tenant(
        self,
        endpoint_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        active_only: bool = False,
    ) -> WebhookEndpoint | None:
        stmt = select(WebhookEndpoint).where(
            WebhookEndpoint.id == endpoint_id,
            WebhookEndpoint.tenant_id == tenant_id,
        )
        if active_only:
            stmt = stmt.where(WebhookEndpoint.status == WebhookEndpointStatus.active)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def disable(self, endpoint_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        endpoint = await self.get_for_tenant(endpoint_id, tenant_id)
        if endpoint is None:
            return False
        endpoint.status = WebhookEndpointStatus.disabled
        await self._db.flush()
        return True
