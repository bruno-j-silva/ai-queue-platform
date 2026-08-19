"""API Key authentication logic.

Flow:
1. Compute SHA-256 of the raw bearer token.
2. Check Redis cache ("apikey:<hash>") — return immediately on hit.
3. On miss, query ``api_keys`` WHERE key_hash=<hash> AND status='active'.
4. Raise ``AuthenticationError`` when not found or revoked.
5. Populate the cache with TTL=60 s before returning.

Security notes:
- The raw key is never logged or stored.
- Only the SHA-256 digest is used for lookup.
"""

import hashlib
import json
from typing import TypedDict

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.api_key import ApiKey, ApiKeyStatus


class TenantIdentity(TypedDict):
    tenant_id: str
    api_key_id: str


CACHE_TTL_SECONDS: int = 60
_CACHE_PREFIX: str = "apikey:"


class AuthenticationError(Exception):
    """Raised when the provided API key is invalid or revoked."""


def _compute_hash(raw_key: str) -> str:
    """Return the hex-encoded SHA-256 digest of *raw_key*."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _cache_key(key_hash: str) -> str:
    return f"{_CACHE_PREFIX}{key_hash}"


async def authenticate(
    raw_key: str,
    db: AsyncSession,
    redis_client: aioredis.Redis,  # type: ignore[type-arg]
) -> TenantIdentity:
    """Authenticate a raw bearer token and return identity info.

    Args:
        raw_key: The raw bearer token provided by the client.
        db: An async SQLAlchemy session.
        redis_client: An async Redis client instance.

    Returns:
        A dict with ``tenant_id`` and ``api_key_id`` (both as strings).

    Raises:
        AuthenticationError: If the key is not found or has been revoked.
    """
    key_hash = _compute_hash(raw_key)
    cache_key = _cache_key(key_hash)

    # 1. Check Redis cache
    cached: bytes | None = await redis_client.get(cache_key)
    if cached is not None:
        data = json.loads(cached)
        return TenantIdentity(
            tenant_id=str(data["tenant_id"]),
            api_key_id=str(data["api_key_id"]),
        )

    # 2. Query the database — filter active keys directly in SQL
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.status == ApiKeyStatus.active)
    result = await db.execute(stmt)
    api_key: ApiKey | None = result.scalar_one_or_none()

    if api_key is None:
        raise AuthenticationError("Invalid or revoked API key.")

    # 3. Build payload and populate cache
    payload: TenantIdentity = {
        "tenant_id": str(api_key.tenant_id),
        "api_key_id": str(api_key.id),
    }
    await redis_client.set(cache_key, json.dumps(payload), ex=CACHE_TTL_SECONDS)

    return payload
