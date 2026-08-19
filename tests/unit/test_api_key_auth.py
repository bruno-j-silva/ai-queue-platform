"""
Unit tests for API Key authentication.

TDD - RED phase: all tests written before implementation.
"""

import hashlib
import json
import uuid
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.auth.api_key import AuthenticationError, authenticate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_key_row(
    *,
    key_hash: str,
    tenant_id: uuid.UUID | None = None,
    api_key_id: uuid.UUID | None = None,
    status: str = "active",
) -> MagicMock:
    row = MagicMock()
    row.key_hash = key_hash
    row.tenant_id = tenant_id or uuid.uuid4()
    row.id = api_key_id or uuid.uuid4()
    row.status = status
    return row


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_key_returns_tenant_id() -> None:
    """A valid, active API key must return tenant_id and api_key_id."""
    raw_key = "test-key-abc123"
    key_hash = _sha256(raw_key)
    tenant_id = uuid.uuid4()
    api_key_id = uuid.uuid4()

    row = _make_api_key_row(key_hash=key_hash, tenant_id=tenant_id, api_key_id=api_key_id)

    # DB mock: returns the row on execute().scalar_one_or_none()
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = row
    db.execute.return_value = result_mock

    # Redis mock: cache miss, then successful set
    redis_client = AsyncMock()
    redis_client.get.return_value = None  # cache miss

    result = await authenticate(raw_key, db, redis_client)

    assert result["tenant_id"] == str(tenant_id)
    assert result["api_key_id"] == str(api_key_id)

    # Cache must be populated with TTL=60s
    redis_client.set.assert_called_once_with(
        f"apikey:{key_hash}",
        mock.ANY,
        ex=60,
    )


@pytest.mark.asyncio
async def test_invalid_key_raises_authentication_error() -> None:
    """A key whose hash is not found in DB must raise AuthenticationError."""
    raw_key = "nonexistent-key-xyz"

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None  # not found
    db.execute.return_value = result_mock

    redis_client = AsyncMock()
    redis_client.get.return_value = None  # cache miss

    with pytest.raises(AuthenticationError):
        await authenticate(raw_key, db, redis_client)


@pytest.mark.asyncio
async def test_revoked_key_raises_authentication_error() -> None:
    """A revoked API key must raise AuthenticationError.

    The SQL query filters ``status='active'`` directly, so the DB returns None
    for revoked keys — the mock simulates this by returning None.
    """
    raw_key = "revoked-key-abc"

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None  # filtered out by SQL
    db.execute.return_value = result_mock

    redis_client = AsyncMock()
    redis_client.get.return_value = None  # cache miss

    with pytest.raises(AuthenticationError):
        await authenticate(raw_key, db, redis_client)


@pytest.mark.asyncio
async def test_cache_hit_skips_db_lookup() -> None:
    """On a cache hit the DB must NOT be queried."""
    raw_key = "cached-key-abc"
    tenant_id = str(uuid.uuid4())
    api_key_id = str(uuid.uuid4())

    cached_payload = json.dumps({"tenant_id": tenant_id, "api_key_id": api_key_id})

    redis_client = AsyncMock()
    redis_client.get.return_value = cached_payload.encode()

    db = AsyncMock()  # must NOT be called

    result = await authenticate(raw_key, db, redis_client)

    assert result["tenant_id"] == tenant_id
    assert result["api_key_id"] == api_key_id
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_hash_is_sha256_of_raw_key() -> None:
    """The cache key used must be 'apikey:<sha256(raw_key)>'."""
    raw_key = "my-super-secret-key"
    expected_hash = _sha256(raw_key)
    expected_cache_key = f"apikey:{expected_hash}"

    tenant_id = uuid.uuid4()
    api_key_id = uuid.uuid4()
    row = _make_api_key_row(key_hash=expected_hash, tenant_id=tenant_id, api_key_id=api_key_id)

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = row
    db.execute.return_value = result_mock

    redis_client = AsyncMock()
    redis_client.get.return_value = None  # cache miss

    await authenticate(raw_key, db, redis_client)

    # Verify the Redis lookup used the correct SHA-256-based cache key
    redis_client.get.assert_called_once_with(expected_cache_key)
