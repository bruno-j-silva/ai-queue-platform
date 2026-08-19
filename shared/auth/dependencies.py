"""FastAPI dependencies for API Key authentication.

Usage:
    from shared.auth.dependencies import get_current_tenant

    @router.post("/jobs")
    async def create_job(
        tenant: dict = Depends(get_current_tenant),
    ) -> ...:
        tenant_id = tenant["tenant_id"]
        ...
"""

from collections.abc import AsyncIterator

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth.api_key import AuthenticationError, TenantIdentity, authenticate
from shared.db.session import SessionLocal

security = HTTPBearer()


async def _get_db() -> AsyncIterator[AsyncSession]:
    """Provide one transactional session per request."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _get_redis() -> AsyncIterator[aioredis.Redis]:  # type: ignore[type-arg]
    """Provide a request-scoped Redis client and always close it."""
    import os

    client = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    try:
        yield client
    finally:
        await client.close()


async def get_current_tenant(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(_get_db),
    redis_client: aioredis.Redis = Depends(_get_redis),  # type: ignore[type-arg]
) -> TenantIdentity:
    """FastAPI dependency that validates the Bearer token and returns identity.

    Returns:
        ``{"tenant_id": str, "api_key_id": str}``

    Raises:
        HTTPException(401): When the token is missing, invalid, or revoked.
    """
    try:
        return await authenticate(credentials.credentials, db, redis_client)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
